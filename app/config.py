import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    hr_internal_api_base_url: str  # HR botining ichki API manzili
    hr_internal_api_token: str  # HR'ning INTERNAL_API_TOKEN'iga mos qiymat
    state_database_path: str  # production-sync'ning o'z holati (allaqachon ko'rilgan hodisalar)
    ombor_api_base_url: str | None
    ombor_actor_name: str
    poll_interval_seconds: int


def load_config() -> Config:
    return Config(
        hr_internal_api_base_url=os.environ["HR_INTERNAL_API_BASE_URL"],
        hr_internal_api_token=os.environ["HR_INTERNAL_API_TOKEN"],
        state_database_path=os.getenv("STATE_DATABASE_PATH", "production_sync_state.db"),
        ombor_api_base_url=os.getenv("OMBOR_API_BASE_URL", "").strip() or None,
        ombor_actor_name=os.getenv("OMBOR_ACTOR_NAME", "production-sync"),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "300")),
    )
