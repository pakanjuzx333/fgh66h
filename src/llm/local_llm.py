from __future__ import annotations
import asyncio, json, logging, re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from llama_cpp import Llama
from src.config.settings import settings
log = logging.getLogger(__name__)
DEFAULT = {"should_respond": False, "response_text": "", "moderation_action": None, "moderation_reason": None, "target_user_id": None}

def parse_decision(raw: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match: raise ValueError("No JSON object in model response")
    result = json.loads(match.group(0)); action = result.get("moderation_action")
    if action not in (None, "warn", "kick", "ban", "mute"): raise ValueError("Invalid moderation action")
    return {**DEFAULT, **result, "should_respond": bool(result.get("should_respond", False)), "response_text": str(result.get("response_text") or "")}

class LocalLLM:
    def __init__(self) -> None:
        path = Path(settings.local_model_path)
        if not path.exists(): raise FileNotFoundError(f"Local GGUF model not found: {path}")
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="llama")
        self.model = Llama(model_path=str(path), n_ctx=settings.local_context_length, n_threads=settings.local_threads, verbose=False)
    def _complete(self, prompt: str) -> str:
        output = self.model.create_chat_completion(messages=[{"role":"user", "content":prompt}], temperature=settings.local_temperature, max_tokens=settings.local_max_tokens, response_format={"type":"json_object"})
        return output["choices"][0]["message"]["content"]
    async def generate(self, prompt: str, system_prompt: str) -> dict[str, Any]:
        full = f"SYSTEM:\n{system_prompt}\n\nREQUEST:\n{prompt}"
        loop = asyncio.get_running_loop()
        for attempt in range(2):
            try:
                raw = await loop.run_in_executor(self.executor, self._complete, full)
                return parse_decision(raw)
            except Exception as exc:
                log.warning("Local LLM response invalid (attempt %s): %s", attempt + 1, exc)
                full += "\nYour prior output was invalid. Return only valid JSON matching the requested schema."
        return DEFAULT.copy()
