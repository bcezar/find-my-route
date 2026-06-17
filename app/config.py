from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "find-my-route"
    nominatim_user_agent: str = "find-my-route/1.0"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    tsp_timeout_seconds: int = 5
    max_addresses: int = 50
    google_maps_api_key: Optional[str] = None
    osrm_base_url: Optional[str] = None
    turso_database_url: Optional[str] = None
    turso_auth_token: Optional[str] = None
    ga_measurement_id: Optional[str] = None


settings = Settings()
