import asyncio
import unittest
from src.bot.pipeline import FastModerator, InferencePipeline
from src.config.settings import settings

class FastModeratorTests(unittest.TestCase):
    def setUp(self):
        self.old_count, self.old_window = settings.spam_messages_per_window, settings.spam_window_seconds
        settings.spam_messages_per_window, settings.spam_window_seconds = 3, 60
    def tearDown(self): settings.spam_messages_per_window, settings.spam_window_seconds = self.old_count, self.old_window
    def test_flood_is_muted(self):
        guard = FastModerator()
        self.assertIsNone(guard.inspect(1, 2, "one").action)
        self.assertIsNone(guard.inspect(1, 2, "two").action)
        self.assertEqual(guard.inspect(1, 2, "three").action, "mute")
    def test_duplicate_is_warned(self):
        old = settings.spam_messages_per_window; settings.spam_messages_per_window = 100
        guard = FastModerator()
        guard.inspect(1, 2, "same"); guard.inspect(1, 2, "same")
        self.assertEqual(guard.inspect(1, 2, "same").action, "warn")
        settings.spam_messages_per_window = old

class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_latest_job_replaces_older_user_job(self):
        pipeline, completed = InferencePipeline(10), []
        await pipeline.submit((1, 2), lambda: completed.append("old") or asyncio.sleep(0))
        await pipeline.submit((1, 2), lambda: completed.append("new") or asyncio.sleep(0))
        await pipeline.start(); await asyncio.sleep(1.4); await pipeline.stop()
        self.assertEqual(completed, ["new"])
        self.assertEqual(pipeline.coalesced, 1)
