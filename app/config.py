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
    retry_enabled: bool = False
    headless: bool = False
    page_timeout_ms: int = 30000
    # Optional Google Maps Geocoding API key. If provided, used to resolve
    # pincode -> city when local DB lookup fails.
    google_maps_api_key: str | None = None
    # Fuzzy matching threshold for matching extracted address city to job city.
    # Value between 0 and 1; higher reduces false positives.
    location_match_threshold: float = 0.85
    # Enable conservative pincode->city filtering before persisting listings.
    # Default False to preserve compatibility with upstream script behavior.
    location_filter_enabled: bool = False

    # -----------------------------------------------------------------------
    # Proxy configuration
    # -----------------------------------------------------------------------
    # Single proxy URL (legacy). Use PROXY_LIST for rotating proxies.
    # Format: http://user:pass@host:port  or  socks5://user:pass@host:port
    proxy_url: str | None = None

    # Comma-separated list of proxy URLs for rotating proxies.
    # Example:
    #   PROXY_LIST=http://u:p@p1.example.com:8080,http://u:p@p2.example.com:8080
    # You can also use newline-separated values in the .env file:
    #   PROXY_LIST="http://u:p@p1.example.com:8080
    #   http://u:p@p2.example.com:8080"
    proxy_list: str | None = None

    # How many failures before a proxy is blacklisted for the session.
    proxy_max_failures: int = 3

    # Rotate proxy on every page (True) or only per job (False).
    proxy_rotate_per_page: bool = True


settings = Settings()
