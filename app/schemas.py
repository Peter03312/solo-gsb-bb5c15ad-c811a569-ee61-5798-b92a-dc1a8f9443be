"""Pydantic 请求/响应模型与入参校验。"""
from datetime import datetime
from typing import Literal

from pydantic import (AwareDatetime, BaseModel, ConfigDict, Field,
                      model_validator)


class MaterialCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200, description="素材名称（唯一）")


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class AuthorizationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    material_id: int = Field(description="素材编号")
    region: str = Field(min_length=1, max_length=100, description="地区，如 CN、US")
    channel: str = Field(min_length=1, max_length=100, description="渠道，如 web、app")
    start_at: AwareDatetime = Field(description="时段起点（含），须带时区")
    end_at: AwareDatetime = Field(description="时段终点（不含），须带时区")
    max_count: int = Field(ge=1, description="可发行次数")

    @model_validator(mode="after")
    def _check_window(self):
        if self.end_at <= self.start_at:
            raise ValueError("非法时段：end_at 必须晚于 start_at（左闭右开区间）")
        return self


class AuthorizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    region: str
    channel: str
    start_at: datetime
    end_at: datetime
    max_count: int
    used_count: int
    disabled: bool
    created_at: datetime


class DistributionRequestCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    material_ids: list[int] = Field(min_length=1, description="素材编号列表，不可重复")
    region: str = Field(min_length=1, max_length=100)
    channel: str = Field(min_length=1, max_length=100)
    requested_at: AwareDatetime = Field(description="发行时刻，须带时区")

    @model_validator(mode="after")
    def _check_duplicate_materials(self):
        if len(set(self.material_ids)) != len(self.material_ids):
            raise ValueError("重复素材：material_ids 中存在重复编号")
        return self


class DistributionRequestItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    material_id: int
    authorization: AuthorizationOut


class DistributionRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    region: str
    channel: str
    requested_at: datetime
    status: Literal["approved", "revoked"]
    created_at: datetime
    revoked_at: datetime | None
    items: list[DistributionRequestItemOut]
