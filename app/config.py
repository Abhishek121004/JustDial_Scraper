from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./data/justdial.db"
    output_dir: str = "output"
    max_pages: int = 5
    scroll_count: int = 4
    min_delay: float = 2.0
    max_delay: float = 5.0
    retry_count: int = 1
    headless: bool = True
    page_timeout_ms: int = 30000


settings = Settings()
