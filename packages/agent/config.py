"""중앙 설정. 모든 환경변수는 여기서만 읽어 타 모듈이 공유한다."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # LLM
    llm_provider: str
    llm_model: str
    llm_api_key: str
    agent_max_tool_calls: int
    llm_timeout_s: float
    llm_retries: int

    # 데이터
    data_dir: Path

    # API
    cors_origins: list[str]
    rate_limit_per_min: int
    session_db: Path
    session_ttl_s: int
    log_level: str
    log_json: bool

    @classmethod
    def load(cls) -> "Settings":
        root = Path(__file__).resolve().parents[2]
        data_dir = Path(os.getenv("DATA_DIR", "data/processed"))
        if not data_dir.is_absolute():
            data_dir = (root / data_dir).resolve()
        session_db = Path(os.getenv("SESSION_DB", str(root / "data" / "sessions.sqlite3")))
        if not session_db.is_absolute():
            session_db = (root / session_db).resolve()
        origins_raw = os.getenv("CORS_ORIGINS", "")
        origins = [o.strip() for o in origins_raw.split(",") if o.strip()]
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "none").lower(),
            llm_model=os.getenv("LLM_MODEL", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            agent_max_tool_calls=_env_int("AGENT_MAX_TOOL_CALLS", 16),
            llm_timeout_s=_env_float("LLM_TIMEOUT_S", 30.0),
            llm_retries=_env_int("LLM_RETRIES", 2),
            data_dir=data_dir,
            cors_origins=origins,
            rate_limit_per_min=_env_int("RATE_LIMIT_PER_MIN", 30),
            session_db=session_db,
            session_ttl_s=_env_int("SESSION_TTL_S", 3600),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            log_json=os.getenv("LOG_JSON", "false").lower() == "true",
        )


_cached: Settings | None = None


def settings() -> Settings:
    global _cached
    if _cached is None:
        _cached = Settings.load()
    return _cached


def reload_settings() -> Settings:
    """테스트·재구성용. 캐시를 비우고 다시 로드한다."""
    global _cached
    _cached = None
    return settings()
