"""Bounded, coalescing inference pipeline and zero-latency spam guard.

Every update is persisted.  The local model only sees the newest pending message per
user, while deterministic abuse signals are acted on before model inference.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Awaitable, Callable

from src.config.settings import community_config, settings

log = logging.getLogger(__name__)
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)

@dataclass(slots=True)
class FastVerdict:
    action: str | None = None
    reason: str | None = None
    delete_message: bool = False

class FastModerator:
    """Small deterministic guard; no model call is required to stop floods."""
    def __init__(self) -> None:
        self.events: dict[tuple[int, int], deque[tuple[float, str]]] = defaultdict(deque)
    def inspect(self, chat_id: int, user_id: int, text: str, is_admin: bool = False) -> FastVerdict:
        if is_admin or not community_config.data.get("moderation_rules", {}).get("fast_filters", {}).get("enabled", True):
            return FastVerdict()
        now, key = time.monotonic(), (chat_id, user_id)
        window = self.events[key]; window.append((now, text.strip().casefold()))
        while window and now - window[0][0] > settings.spam_window_seconds: window.popleft()
        rules = community_config.data["moderation_rules"].get("fast_filters", {})
        delete = bool(rules.get("delete_spam_messages", True))
        if len(window) >= settings.spam_messages_per_window:
            return FastVerdict("mute", f"Flooding: {len(window)} messages in {settings.spam_window_seconds}s", delete)
        normalized = text.strip().casefold()
        repeats = sum(value == normalized for _, value in window)
        if normalized and repeats >= int(rules.get("duplicate_message_threshold", 3)):
            return FastVerdict("warn", "Repeated message spam", delete)
        patterns = tuple(item.casefold() for item in rules.get("suspicious_link_patterns", []))
        if patterns and any(pattern in text.casefold() for pattern in patterns):
            return FastVerdict("mute", "Suspicious short or invite link", delete)
        return FastVerdict()

@dataclass(slots=True)
class InferenceJob:
    key: tuple[int, int]
    run: Callable[[], Awaitable[None]]
    enqueued_at: float

class InferencePipeline:
    """A bounded latest-message-wins queue safe for a single llama.cpp instance."""
    def __init__(self, max_size: int, workers: int = 1) -> None:
        self.max_size, self.workers = max_size, max(1, workers)
        self._jobs: deque[InferenceJob] = deque()
        self._latest: dict[tuple[int, int], InferenceJob] = {}
        self._condition = asyncio.Condition()
        self._tasks: list[asyncio.Task] = []
        self._stopping = False
        self.dropped = self.coalesced = self.completed = 0
    async def start(self) -> None:
        # llama.cpp model objects serialize generation internally; one worker avoids
        # context corruption and gives predictable latency on typical VPS hardware.
        self._tasks = [asyncio.create_task(self._worker(), name=f"llm-worker-{n}") for n in range(self.workers)]
    async def stop(self) -> None:
        self._stopping = True
        async with self._condition: self._condition.notify_all()
        await asyncio.gather(*self._tasks, return_exceptions=True)
    async def submit(self, key: tuple[int, int], run: Callable[[], Awaitable[None]]) -> bool:
        job = InferenceJob(key, run, time.monotonic())
        async with self._condition:
            old = self._latest.get(key)
            if old is not None:
                self._latest[key] = job; self.coalesced += 1; self._condition.notify(); return True
            if len(self._jobs) >= self.max_size:
                evicted = self._jobs.popleft(); self._latest.pop(evicted.key, None); self.dropped += 1
            self._jobs.append(job); self._latest[key] = job; self._condition.notify(); return True
    async def _worker(self) -> None:
        while True:
            async with self._condition:
                while not self._jobs and not self._stopping: await self._condition.wait()
                if self._stopping and not self._jobs: return
                initial = self._jobs.popleft(); job = self._latest.pop(initial.key, initial)
            # Short debounce lets a conversation burst settle and prevents stale replies.
            delay = settings.user_debounce_seconds - (time.monotonic() - job.enqueued_at)
            if delay > 0: await asyncio.sleep(delay)
            try: await job.run(); self.completed += 1
            except asyncio.CancelledError: raise
            except Exception: log.exception("Inference job failed for %s", job.key)
    def stats(self) -> dict[str, int]: return {"queued": len(self._jobs), "coalesced": self.coalesced, "dropped": self.dropped, "completed": self.completed}
