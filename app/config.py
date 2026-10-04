"""应用配置：全部支持环境变量覆盖。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLAlchemy 连接串，Compose 中通过环境变量注入
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/licensing"

    # 启动时等待数据库就绪的重试参数
    db_connect_retries: int = 30
    db_connect_retry_delay: float = 1.0  # 秒


settings = Settings()
