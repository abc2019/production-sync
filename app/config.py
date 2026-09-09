import json
import os
from dataclasses import dataclass, field

from erp_bridge_kit.matching import DEFAULT_CONFIDENCE_THRESHOLD


@dataclass(frozen=True)
class Config:
    hr_internal_api_base_url: str  # HR botining ichki API manzili (masalan http://hr.internal:8089)
    hr_internal_api_token: str  # HR'ning INTERNAL_API_TOKEN'iga mos qiymat
    state_database_path: str  # production-sync'ning o'z holati (allaqachon ko'rilgan hodisalar)
    ombor_api_base_url: str | None
    ombor_actor_name: str
    match_threshold: float
    poll_interval_seconds: int
    # HR'da bitta topshiriq turli birlikda hisobot berilishi mumkin (masalan
    # ba'zi vazifalar "box"da, ba'zilari to'g'ridan-to'g'ri "partiya"da).
    # Har bir birlik uchun 1 dona (banka)ga necha marta ko'paytirish kerakligi.
    unit_multipliers: dict[str, int] = field(
        default_factory=lambda: {"box": 24, "partiya": 300, "dona": 1, "ta": 1}
    )


def load_config() -> Config:
    raw_multipliers = os.getenv("UNIT_MULTIPLIERS", "")
    if raw_multipliers.strip():
        try:
            unit_multipliers = {k.lower(): int(v) for k, v in json.loads(raw_multipliers).items()}
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            raise RuntimeError(f"UNIT_MULTIPLIERS noto'g'ri JSON: {e}")
    else:
        unit_multipliers = {"box": 24, "partiya": 300, "dona": 1, "ta": 1}

    return Config(
        hr_internal_api_base_url=os.environ["HR_INTERNAL_API_BASE_URL"],
        hr_internal_api_token=os.environ["HR_INTERNAL_API_TOKEN"],
        state_database_path=os.getenv("STATE_DATABASE_PATH", "production_sync_state.db"),
        ombor_api_base_url=os.getenv("OMBOR_API_BASE_URL", "").strip() or None,
        ombor_actor_name=os.getenv("OMBOR_ACTOR_NAME", "production-sync"),
        match_threshold=float(os.getenv("MATCH_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD)),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "300")),
        unit_multipliers=unit_multipliers,
    )
