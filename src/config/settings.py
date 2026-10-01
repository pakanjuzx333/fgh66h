"""Runtime settings and reloadable community configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    try: return int(os.getenv(name, default))
    except ValueError: return default

@dataclass
class Settings:
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_group_id: int = field(default_factory=lambda: _int("TELEGRAM_GROUP_ID", 0))
    admin_user_ids: set[int] = field(default_factory=lambda: {int(x.strip()) for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip().isdigit()})
    llm_mode: str = field(default_factory=lambda: os.getenv("LLM_MODE", "local").lower())
    local_model_path: str = field(default_factory=lambda: os.getenv("LOCAL_MODEL_PATH", "./models/phi-3-mini-q4.gguf"))
    local_context_length: int = field(default_factory=lambda: _int("LOCAL_MODEL_CONTEXT_LENGTH", 4096))
    local_max_tokens: int = field(default_factory=lambda: _int("LOCAL_MODEL_MAX_TOKENS", 512))
    local_temperature: float = field(default_factory=lambda: float(os.getenv("LOCAL_MODEL_TEMPERATURE", "0.7")))
    local_threads: int = field(default_factory=lambda: _int("LOCAL_MODEL_THREADS", 4))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    max_chat_history: int = field(default_factory=lambda: _int("MAX_CHAT_HISTORY", 50))
    session_timeout_minutes: int = field(default_factory=lambda: _int("SESSION_TIMEOUT_MINUTES", 60))
    mute_duration_minutes: int = field(default_factory=lambda: _int("MUTE_DURATION_MINUTES", 60))
    inference_queue_size: int = field(default_factory=lambda: _int("INFERENCE_QUEUE_SIZE", 200))
    inference_workers: int = field(default_factory=lambda: _int("INFERENCE_WORKERS", 1))
    user_debounce_seconds: float = field(default_factory=lambda: float(os.getenv("USER_DEBOUNCE_SECONDS", "1.2")))
    max_ai_response_per_user_seconds: float = field(default_factory=lambda: float(os.getenv("AI_RESPONSE_COOLDOWN_SECONDS", "3")))
    spam_window_seconds: int = field(default_factory=lambda: _int("SPAM_WINDOW_SECONDS", 12))
    spam_messages_per_window: int = field(default_factory=lambda: _int("SPAM_MESSAGES_PER_WINDOW", 6))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_file: str = field(default_factory=lambda: os.getenv("LOG_FILE", "logs/telegram-ai-manager.log"))
    google_gemini_api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_GEMINI_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))

class CommunityConfig:
    def __init__(self, path: Path = ROOT / "config.yaml") -> None:
        self.path = path; self.data: dict[str, Any] = {}; self.reload()
    def reload(self) -> None:
        with self.path.open(encoding="utf-8") as handle:
            self.data = yaml.safe_load(handle) or {}
    def system_prompt(self) -> str:
        c, p, m, r = (self.data.get(k, {}) for k in ("community", "bot_personality", "moderation_rules", "response_rules"))
        return (f"You are {p.get('name','the community manager')} for {c.get('name','this community')}. "
                f"Tone: {p.get('tone','professional')}. Style: {p.get('speaking_style','Be helpful.')}.\n"
                f"Project: {c.get('project_description','')}. Language: {c.get('language','English')}.\n"
                f"Moderation rules: {m}. Response rules: {r}. Never invent project facts. "
                "Return ONLY one JSON object using keys should_respond, response_text, moderation_action, moderation_reason, target_user_id. "
                "moderation_action is null, warn, kick, ban, or mute. Do not moderate admins.")

settings = Settings()
community_config = CommunityConfig()
