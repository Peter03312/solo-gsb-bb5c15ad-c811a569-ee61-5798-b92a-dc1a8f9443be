"""发行申请：整体核验并占用次数、查询、撤销。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import api_error
from ..models import (Authorization, DistributionRequest,
                      DistributionRequestItem, Material)
from ..schemas import DistributionRequestCreate, DistributionRequestOut

router = APIRouter(prefix="/distribution-requests", tags=["发行申请"])


@router.post("", response_model=DistributionRequestOut, status_code=201, summary="提交发行申请")
def create_distribution_request(
    payload: DistributionRequestCreate, db: Session = Depends(get_db)
):
    """每个素材须存在匹配（地区/渠道/左闭右开时段）且未停用、有余量的授权；

    全部满足才整体通过并占用次数，否则不扣任何次数并逐项列明原因。
    重叠授权按“到期时间升序、编号升序”选择第一个有余量的。
    """
    material_ids = payload.material_ids

    # 0) 素材编号必须全部已知
    existing = set(db.scalars(select(Material.id).where(Material.id.in_(material_ids))).all())
    missing = [mid for mid in material_ids if mid not in existing]
    if missing:
        raise api_error(404, "MATERIAL_NOT_FOUND", f"未知素材编号: {missing}")

    # 1) 扫描各素材的候选授权编号（未加锁，仅确定匹配集合与选择顺序）
    candidate_ids_by_material: dict[int, list[int]] = {}
    all_candidate_ids: set[int] = set()
    for mid in material_ids:
        rows = db.scalars(
            select(Authorization.id)
            .where(
                Authorization.material_id == mid,
                Authorization.region == payload.region,
                Authorization.channel == payload.channel,
                Authorization.start_at <= payload.requested_at,
                Authorization.end_at > payload.requested_at,  # 左闭右开
            )
            .order_by(Authorization.end_at.asc(), Authorization.id.asc())
        ).all()
        candidate_ids_by_material[mid] = list(rows)
        all_candidate_ids.update(rows)

    # 2) 按编号升序一次性锁定全部候选授权行（统一的加锁顺序，避免并发死锁与超发）
    locked: dict[int, Authorization] = {}
    if all_candidate_ids:
        locked_rows = db.scalars(
            select(Authorization)
            .where(Authorization.id.in_(all_candidate_ids))
            .order_by(Authorization.id.asc())
            .with_for_update()
        ).all()
        locked = {row.id: row for row in locked_rows}

    # 3) 逐素材按“到期时间、编号升序”取第一个（加锁后复核）未停用且有余量的授权
    chosen: dict[int, Authorization] = {}
    reasons: list[dict] = []
    for mid in material_ids:
        pick: Authorization | None = None
        matched = False
        for aid in candidate_ids_by_material[mid]:
            row = locked.get(aid)
            if row is None or row.disabled:
                continue
            matched = True
            if row.used_count < row.max_count:
                pick = row
                break
        if pick is None:
            reasons.append(
                {
                    "material_id": mid,
                    "reason": "匹配授权的可发行次数已用尽"
                    if matched
                    else "无匹配授权（地区/渠道/时段不匹配或授权已停用）",
                }
            )
        else:
            chosen[mid] = pick

    # 4) 任一素材无可用授权则整体失败，回滚，不扣任何次数
    if reasons:
        db.rollback()
        raise api_error(
            409,
            "AUTHORIZATION_UNAVAILABLE",
            "部分素材无可用授权，本次申请未通过，未占用任何次数",
            reasons=reasons,
        )

    # 5) 占用次数并登记申请（持有行锁直至提交，并发不会超额）
    request = DistributionRequest(
        region=payload.region,
        channel=payload.channel,
        requested_at=payload.requested_at,
        status="approved",
    )
    for mid in material_ids:
        authorization = chosen[mid]
        authorization.used_count += 1
        request.items.append(
            DistributionRequestItem(material_id=mid, authorization=authorization)
        )
    db.add(request)
    db.commit()
    return request


@router.get("/{request_id}", response_model=DistributionRequestOut, summary="查询发行申请")
def get_distribution_request(request_id: int, db: Session = Depends(get_db)):
    request = db.get(DistributionRequest, request_id)
    if request is None:
        raise api_error(404, "REQUEST_NOT_FOUND", f"未知发行申请编号: {request_id}")
    return request


@router.post("/{request_id}/revoke", response_model=DistributionRequestOut, summary="撤销发行申请（仅一次，释放占用）")
def revoke_distribution_request(request_id: int, db: Session = Depends(get_db)):
    request = db.scalar(
        select(DistributionRequest)
        .where(DistributionRequest.id == request_id)
        .with_for_update()
    )
    if request is None:
        raise api_error(404, "REQUEST_NOT_FOUND", f"未知发行申请编号: {request_id}")
    if request.status == "revoked":
        raise api_error(409, "ALREADY_REVOKED", f"发行申请 {request_id} 已撤销，不能重复撤销")

    # 释放各明细占用的次数（同样按编号升序加锁）
    auth_ids = sorted({item.authorization_id for item in request.items})
    if auth_ids:
        authorizations = db.scalars(
            select(Authorization)
            .where(Authorization.id.in_(auth_ids))
            .order_by(Authorization.id.asc())
            .with_for_update()
        ).all()
        for authorization in authorizations:
            if authorization.used_count > 0:
                authorization.used_count -= 1

    request.status = "revoked"
    request.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return request
