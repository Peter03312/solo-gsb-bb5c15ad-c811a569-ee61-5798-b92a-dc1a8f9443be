"""素材登记与查询。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import api_error
from ..models import Material
from ..schemas import MaterialCreate, MaterialOut

router = APIRouter(prefix="/materials", tags=["素材"])


@router.post("", response_model=MaterialOut, status_code=201, summary="登记素材")
def create_material(payload: MaterialCreate, db: Session = Depends(get_db)):
    exists = db.scalar(select(Material.id).where(Material.name == payload.name))
    if exists is not None:
        raise api_error(409, "MATERIAL_EXISTS", f"素材名称已存在: {payload.name}")
    material = Material(name=payload.name)
    db.add(material)
    try:
        db.commit()
    except IntegrityError:  # 并发下唯一约束兜底
        db.rollback()
        raise api_error(409, "MATERIAL_EXISTS", f"素材名称已存在: {payload.name}")
    return material


@router.get("", response_model=list[MaterialOut], summary="素材列表")
def list_materials(db: Session = Depends(get_db)):
    return db.scalars(select(Material).order_by(Material.id)).all()


@router.get("/{material_id}", response_model=MaterialOut, summary="查询单个素材")
def get_material(material_id: int, db: Session = Depends(get_db)):
    material = db.get(Material, material_id)
    if material is None:
        raise api_error(404, "MATERIAL_NOT_FOUND", f"未知素材编号: {material_id}")
    return material
