"""授权登记、查询与停用。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import api_error
from ..models import Authorization, Material
from ..schemas import AuthorizationCreate, AuthorizationOut

router = APIRouter(prefix="/authorizations", tags=["授权"])


@router.post("", response_model=AuthorizationOut, status_code=201, summary="登记授权")
def create_authorization(payload: AuthorizationCreate, db: Session = Depends(get_db)):
    material = db.get(Material, payload.material_id)
    if material is None:
        raise api_error(404, "MATERIAL_NOT_FOUND", f"未知素材编号: {payload.material_id}")
    authorization = Authorization(**payload.model_dump())
    db.add(authorization)
    db.commit()
    return authorization


@router.get("", response_model=list[AuthorizationOut], summary="授权列表（可按素材/地区/渠道过滤）")
def list_authorizations(
    material_id: int | None = Query(default=None),
    region: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(Authorization).order_by(Authorization.id)
    if material_id is not None:
        stmt = stmt.where(Authorization.material_id == material_id)
    if region is not None:
        stmt = stmt.where(Authorization.region == region)
    if channel is not None:
        stmt = stmt.where(Authorization.channel == channel)
    return db.scalars(stmt).all()


@router.get("/{authorization_id}", response_model=AuthorizationOut, summary="查询单个授权")
def get_authorization(authorization_id: int, db: Session = Depends(get_db)):
    authorization = db.get(Authorization, authorization_id)
    if authorization is None:
        raise api_error(404, "AUTHORIZATION_NOT_FOUND", f"未知授权编号: {authorization_id}")
    return authorization


@router.post("/{authorization_id}/disable", response_model=AuthorizationOut, summary="停用授权（仅影响新申请）")
def disable_authorization(authorization_id: int, db: Session = Depends(get_db)):
    authorization = db.scalar(
        select(Authorization).where(Authorization.id == authorization_id).with_for_update()
    )
    if authorization is None:
        raise api_error(404, "AUTHORIZATION_NOT_FOUND", f"未知授权编号: {authorization_id}")
    authorization.disabled = True
    db.commit()
    return authorization
