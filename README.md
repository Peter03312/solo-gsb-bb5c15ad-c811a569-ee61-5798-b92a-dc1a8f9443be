# 素材发行授权核验 API

面向内容团队的素材发行授权核验服务：登记素材与授权（地区、渠道、带时区的左闭右开时段、可发行次数），对发行申请做整体核验——每个素材都命中匹配且有余量的授权时才整体通过并占用次数，否则逐项列明原因且不扣任何次数。已通过的申请可查询、可撤销一次并释放占用；授权可停用，停用仅影响新申请。

- 技术栈：Python 3.12 · FastAPI · SQLAlchemy 2 · PostgreSQL 16
- 并发安全：授权行级锁（`SELECT ... FOR UPDATE`，统一按编号升序加锁）+ 数据库约束兜底，并发申请不会超发

## 一键启动

```bash
docker compose up --build
```

启动后：

| 地址 | 说明 |
| --- | --- |
| http://localhost:8000 | API 服务 |
| http://localhost:8000/docs | Swagger 交互文档 |
| http://localhost:8000/health | 健康检查 |
| localhost:5432 | PostgreSQL（用户/密码 `postgres`，库 `licensing`） |

应用启动时自动等待数据库就绪并建表（幂等），无需手工初始化。

常用命令：

```bash
docker compose up --build      # 构建并启动
docker compose up -d           # 后台运行
docker compose logs -f app     # 查看应用日志
docker compose down            # 停止
docker compose down -v         # 停止并清空数据
./scripts/smoke.sh             # 端到端冒烟测试（含并发不超发验证，需服务已启动）
```

## 配置

应用通过环境变量配置（Compose 中已注入，本地开发可自行导出或写入 `.env`）：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/licensing` | 数据库连接串 |
| `DB_CONNECT_RETRIES` | `30` | 启动时等待数据库的重试次数 |
| `DB_CONNECT_RETRY_DELAY` | `1.0` | 重试间隔（秒） |

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/materials` | 登记素材（名称唯一） |
| GET | `/materials`、`/materials/{id}` | 查询素材 |
| POST | `/authorizations` | 登记授权 |
| GET | `/authorizations`、`/authorizations/{id}` | 查询授权（列表支持 `material_id`/`region`/`channel` 过滤） |
| POST | `/authorizations/{id}/disable` | 停用授权（仅影响新申请） |
| POST | `/distribution-requests` | 提交发行申请（整体核验并占用次数） |
| GET | `/distribution-requests/{id}` | 查询发行申请 |
| POST | `/distribution-requests/{id}/revoke` | 撤销发行申请（仅一次，释放占用） |

## 调用示例

以下假设服务运行在 `http://localhost:8000`。

### 1. 登记素材

```bash
curl -X POST http://localhost:8000/materials \
  -H 'Content-Type: application/json' \
  -d '{"name": "宣传片A"}'
```

```json
{"id": 1, "name": "宣传片A", "created_at": "2026-10-04T10:00:00.000000Z"}
```

### 2. 登记授权

时段为带时区的左闭右开区间 `[start_at, end_at)`：`start_at` 时刻可发行，`end_at` 时刻起不可发行。

```bash
curl -X POST http://localhost:8000/authorizations \
  -H 'Content-Type: application/json' \
  -d '{
    "material_id": 1,
    "region": "CN",
    "channel": "web",
    "start_at": "2026-01-01T00:00:00+08:00",
    "end_at": "2026-07-01T00:00:00+08:00",
    "max_count": 2
  }'
```

```json
{
  "id": 1, "material_id": 1, "region": "CN", "channel": "web",
  "start_at": "2026-01-01T00:00:00+08:00", "end_at": "2026-07-01T00:00:00+08:00",
  "max_count": 2, "used_count": 0, "disabled": false,
  "created_at": "2026-10-04T10:00:00.000000Z"
}
```

### 3. 提交发行申请

一次申请可携带多个素材；**全部**素材都有匹配（地区、渠道、时刻落在左闭右开时段内）且未停用、有余量的授权时才整体通过，否则一个不通过、整体不扣次。同一素材存在多份重叠授权时，按“到期时间升序、编号升序”选择第一个有余量的。

```bash
curl -X POST http://localhost:8000/distribution-requests \
  -H 'Content-Type: application/json' \
  -d '{
    "material_ids": [1, 2],
    "region": "CN",
    "channel": "web",
    "requested_at": "2026-03-01T12:00:00+08:00"
  }'
```

通过（201）时返回各项占用的授权：

```json
{
  "id": 1,
  "region": "CN",
  "channel": "web",
  "requested_at": "2026-03-01T12:00:00+08:00",
  "status": "approved",
  "created_at": "2026-10-04T10:00:00.000000Z",
  "revoked_at": null,
  "items": [
    {
      "material_id": 1,
      "authorization": {
        "id": 1, "material_id": 1, "region": "CN", "channel": "web",
        "start_at": "2026-01-01T00:00:00+08:00", "end_at": "2026-07-01T00:00:00+08:00",
        "max_count": 2, "used_count": 1, "disabled": false,
        "created_at": "2026-10-04T09:00:00.000000Z"
      }
    },
    {
      "material_id": 2,
      "authorization": {
        "id": 3, "material_id": 2, "region": "CN", "channel": "web",
        "start_at": "2026-01-01T00:00:00+08:00", "end_at": "2027-01-01T00:00:00+08:00",
        "max_count": 1, "used_count": 1, "disabled": false,
        "created_at": "2026-10-04T09:00:00.000000Z"
      }
    }
  ]
}
```

失败（409）时逐项列明原因，且不占用任何次数：

```json
{
  "detail": {
    "code": "AUTHORIZATION_UNAVAILABLE",
    "message": "部分素材无可用授权，本次申请未通过，未占用任何次数",
    "reasons": [
      {"material_id": 2, "reason": "匹配授权的可发行次数已用尽"},
      {"material_id": 3, "reason": "无匹配授权（地区/渠道/时段不匹配或授权已停用）"}
    ]
  }
}
```

### 4. 查询 / 撤销申请

```bash
curl http://localhost:8000/distribution-requests/1
curl -X POST http://localhost:8000/distribution-requests/1/revoke
```

撤销成功后 `status` 变为 `revoked`，各项授权占用的次数被释放；重复撤销返回 409。

### 5. 停用授权

```bash
curl -X POST http://localhost:8000/authorizations/1/disable
```

停用后该授权不再参与新申请的匹配；此前已通过的申请不受影响，仍可查询、撤销。

## 错误约定

业务错误的响应体统一为 `{"detail": {"code": "...", "message": "..."}}`：

| 场景 | 状态码 | code |
| --- | --- | --- |
| 未知素材/授权/申请编号 | 404 | `MATERIAL_NOT_FOUND` / `AUTHORIZATION_NOT_FOUND` / `REQUEST_NOT_FOUND` |
| 素材名称重复 | 409 | `MATERIAL_EXISTS` |
| 申请中存在无可用授权的素材 | 409 | `AUTHORIZATION_UNAVAILABLE`（附 `reasons` 明细） |
| 重复撤销 | 409 | `ALREADY_REVOKED` |
| 重复素材、非法时段（`end_at <= start_at`）、时间缺时区等入参问题 | 422 | FastAPI 校验错误 |

## 设计要点

- **整体通过、不部分扣次**：申请在单个事务内完成“锁定 → 逐素材选择 → 占用”，任一素材失败即回滚。
- **重叠授权选择**：候选授权按 `end_at ASC, id ASC` 排序，取加锁后复核仍有效（未停用、次数未满）的第一份。
- **并发不超发**：全部候选授权按编号升序一次性 `FOR UPDATE` 加锁（统一顺序避免死锁），在锁内复核余量并扣减；数据库另有 `used_count <= max_count` 约束兜底。
- **左闭右开时段**：匹配条件为 `start_at <= requested_at < end_at`，时间统一以 `timestamptz` 存储，入参必须带时区。

## 本地开发（不用 Docker 跑应用时）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d db          # 只起数据库
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/licensing'
uvicorn app.main:app --reload --port 8000
```

## 目录结构

```
app/
  main.py                        # 应用入口、路由注册、启动建表
  config.py                      # 环境变量配置
  database.py                    # 引擎/会话/初始化重试
  models.py                      # 素材、授权、发行申请、申请明细
  schemas.py                     # 请求/响应模型与校验（重复素材、非法时段等）
  routers/
    materials.py                 # 素材登记与查询
    authorizations.py            # 授权登记、查询、停用
    distribution_requests.py     # 发行申请：整体核验占用、查询、撤销
scripts/smoke.sh                 # 端到端冒烟测试
Dockerfile / docker-compose.yml  # 一键启动
```
