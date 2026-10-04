"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import init_db
from .routers import authorizations, distribution_requests, materials


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # 启动时建表，等待数据库就绪
    yield


app = FastAPI(
    title="素材发行授权核验 API",
    version="1.0.0",
    description="登记素材与授权，核验发行申请并占用/释放发行次数。",
    lifespan=lifespan,
)

app.include_router(materials.router)
app.include_router(authorizations.router)
app.include_router(distribution_requests.router)


@app.get("/health", tags=["健康检查"], summary="健康检查")
def health():
    return {"status": "ok"}
