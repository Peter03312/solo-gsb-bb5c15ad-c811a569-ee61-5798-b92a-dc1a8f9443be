#!/usr/bin/env bash
# 端到端冒烟测试：需先通过 docker compose up 启动服务。
# 用法: ./scripts/smoke.sh [BASE_URL]
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
PASS=0
FAIL=0

check() { # check <描述> <期望> <实际>
  if [[ "$2" == "$3" ]]; then
    echo "PASS: $1"; PASS=$((PASS+1))
  else
    echo "FAIL: $1 (期望 [$2], 实际 [$3])"; FAIL=$((FAIL+1))
  fi
}

# 执行请求：HTTP 状态码写入标准输出，响应体写入 $TMP_DIR/body.json
code() { curl -s -o "$TMP_DIR/body.json" -w "%{http_code}\n" "$@"; }

# 从最近一次响应体中提取整数字段
json_field() { sed -n "s/.*\"$1\":\([0-9][0-9]*\).*/\1/p" "$TMP_DIR/body.json" | head -1; }

echo "== 健康检查 =="
check "GET /health" "200" "$(code "$BASE_URL/health")"

echo "== 登记素材 =="
check "创建素材1" "201" "$(code -X POST "$BASE_URL/materials" -H 'Content-Type: application/json' -d '{"name":"宣传片A"}')"
check "创建素材2" "201" "$(code -X POST "$BASE_URL/materials" -H 'Content-Type: application/json' -d '{"name":"海报B"}')"
check "重复素材名报错" "409" "$(code -X POST "$BASE_URL/materials" -H 'Content-Type: application/json' -d '{"name":"宣传片A"}')"

echo "== 登记授权 =="
# 素材1 两份重叠授权：授权1 到期早(2次)、授权2 到期晚(3次)；素材2 一份(1次)
check "授权1(素材1,2次,早到期)" "201" "$(code -X POST "$BASE_URL/authorizations" -H 'Content-Type: application/json' -d '{"material_id":1,"region":"CN","channel":"web","start_at":"2026-01-01T00:00:00+08:00","end_at":"2026-07-01T00:00:00+08:00","max_count":2}')"
check "授权2(素材1,3次,晚到期)" "201" "$(code -X POST "$BASE_URL/authorizations" -H 'Content-Type: application/json' -d '{"material_id":1,"region":"CN","channel":"web","start_at":"2026-01-01T00:00:00+08:00","end_at":"2027-01-01T00:00:00+08:00","max_count":3}')"
check "授权3(素材2,1次)" "201" "$(code -X POST "$BASE_URL/authorizations" -H 'Content-Type: application/json' -d '{"material_id":2,"region":"CN","channel":"web","start_at":"2026-01-01T00:00:00+08:00","end_at":"2027-01-01T00:00:00+08:00","max_count":1}')"
check "未知素材编号报错" "404" "$(code -X POST "$BASE_URL/authorizations" -H 'Content-Type: application/json' -d '{"material_id":999,"region":"CN","channel":"web","start_at":"2026-01-01T00:00:00+08:00","end_at":"2027-01-01T00:00:00+08:00","max_count":1}')"
check "非法时段报错" "422" "$(code -X POST "$BASE_URL/authorizations" -H 'Content-Type: application/json' -d '{"material_id":1,"region":"CN","channel":"web","start_at":"2027-01-01T00:00:00+08:00","end_at":"2026-01-01T00:00:00+08:00","max_count":1}')"

echo "== 发行申请 =="
check "重复素材报错" "422" "$(code -X POST "$BASE_URL/distribution-requests" -H 'Content-Type: application/json' -d '{"material_ids":[1,1],"region":"CN","channel":"web","requested_at":"2026-03-01T12:00:00+08:00"}')"
check "渠道不匹配整体失败" "409" "$(code -X POST "$BASE_URL/distribution-requests" -H 'Content-Type: application/json' -d '{"material_ids":[1,2],"region":"CN","channel":"tv","requested_at":"2026-03-01T12:00:00+08:00"}')"
check "两素材整体通过" "201" "$(code -X POST "$BASE_URL/distribution-requests" -H 'Content-Type: application/json' -d '{"material_ids":[1,2],"region":"CN","channel":"web","requested_at":"2026-03-01T12:00:00+08:00"}')"
# 重叠授权按到期时间升序，素材1 应选中授权1
check "选中到期更早的授权1" "1" "$(sed -n 's/.*"authorization":{"id":\([0-9][0-9]*\).*/\1/p' "$TMP_DIR/body.json" | head -1)"
check "素材2次数用尽后整体失败" "409" "$(code -X POST "$BASE_URL/distribution-requests" -H 'Content-Type: application/json' -d '{"material_ids":[1,2],"region":"CN","channel":"web","requested_at":"2026-03-01T12:00:00+08:00"}')"
code "$BASE_URL/authorizations/1" > /dev/null
check "失败不扣次(授权1 used=1)" "1" "$(json_field used_count)"

echo "== 查询与撤销 =="
check "查询申请1" "200" "$(code "$BASE_URL/distribution-requests/1")"
check "未知申请编号报错" "404" "$(code "$BASE_URL/distribution-requests/999")"
check "撤销申请1" "200" "$(code -X POST "$BASE_URL/distribution-requests/1/revoke")"
check "重复撤销报错" "409" "$(code -X POST "$BASE_URL/distribution-requests/1/revoke")"
code "$BASE_URL/authorizations/1" > /dev/null
check "撤销后授权1释放(used=0)" "0" "$(json_field used_count)"

echo "== 停用 =="
check "停用授权2" "200" "$(code -X POST "$BASE_URL/authorizations/2/disable")"
check "停用后新申请失败" "409" "$(code -X POST "$BASE_URL/distribution-requests" -H 'Content-Type: application/json' -d '{"material_ids":[1],"region":"CN","channel":"web","requested_at":"2026-08-01T12:00:00+08:00"}')"
check "已撤销申请仍可查" "200" "$(code "$BASE_URL/distribution-requests/1")"

echo "== 并发不超发（授权1 余量 2，并发 10 个申请）=="
for i in $(seq 1 10); do
  code -X POST "$BASE_URL/distribution-requests" -H 'Content-Type: application/json' \
    -d '{"material_ids":[1],"region":"CN","channel":"web","requested_at":"2026-03-01T12:00:00+08:00"}' \
    > "$TMP_DIR/code_$i" &
done
wait
APPROVED=$(cat "$TMP_DIR"/code_* | grep -c '^201$' || true)
check "恰好 2 个通过" "2" "$APPROVED"
code "$BASE_URL/authorizations/1" > /dev/null
check "授权1 最终 used=2" "2" "$(json_field used_count)"

echo
echo "通过 $PASS 项，失败 $FAIL 项"
[[ "$FAIL" == "0" ]]
