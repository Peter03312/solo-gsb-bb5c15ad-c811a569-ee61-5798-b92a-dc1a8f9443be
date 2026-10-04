"""统一业务错误：detail 中携带机器可读的 code 与中文 message。"""
from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str, **extra) -> HTTPException:
    detail = {"code": code, "message": message}
    detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)
