import os
from dataclasses import dataclass

from erp_bridge_kit.matching import DEFAULT_CONFIDENCE_THRESHOLD


@dataclass(frozen=True)
class Config:
    hr_database_path: str  # HR botining SQLite fayliga yo'l (FAQAT o'qish uchun)
    state_database_path: str  # production-sync'ning o'z holati (allaqachon ko'rilgan hodisalar)
    ombor_api_base_url: str | None
    ombor_actor_name: str
    match_threshold: float
    poll_interval_seconds: int
    box_to_units: int  # 1 HR "box"i nechta Ombor birligiga (banka) teng


def load_config() -> Config:
    return Config(
        hr_database_path=os.environ["HR_DATABASE_PATH"],
        state_database_path=os.getenv("STATE_DATABASE_PATH", "production_sync_state.db"),
        ombor_api_base_url=os.getenv("OMBOR_API_BASE_URL", "").strip() or None,
        ombor_actor_name=os.getenv("OMBOR_ACTOR_NAME", "production-sync"),
        match_threshold=float(os.getenv("MATCH_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD)),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "300")),
        box_to_units=int(os.getenv("BOX_TO_UNITS", "24")),
    )
