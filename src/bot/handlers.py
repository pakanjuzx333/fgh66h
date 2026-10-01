from __future__ import annotations
import asyncio, logging, time
from collections import defaultdict
from telegram import Update
from telegram.ext import ContextTypes
from src.config.settings import community_config, settings
from src.db import crud
log = logging.getLogger(__name__)
_last_response: dict[int, float] = defaultdict(float)
def _prompt(message, user, history, session):
    lines = [f"{m.user_id}: {m.text}" for m in history]
    budget = settings.local_context_length * 3
    context = "\n".join(lines)[-budget:]
    return (f"User profile: id={user.telegram_id}, username={user.username}, warnings={user.warn_count}, joined={user.joined_at}, notes={user.notes}.\n"
            f"Session summary: {session.context_summary if session else ''}\nRecent chat:\n{context}\n\nCurrent message from {user.telegram_id}: {message.text}\n"
            "Decide whether to respond and/or moderate the current sender. Output JSON only.")
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message; sender = update.effective_user
    if not message or not sender or not message.text or sender.is_bot: return
    if settings.telegram_group_id and message.chat_id != settings.telegram_group_id: return
    try:
        factory = context.application.bot_data["session_factory"]
        async with factory() as db:
            user = await crud.upsert_user(db, sender.id, sender.username, sender.first_name)
            await crud.add_message(db, message.chat_id, user.id, message.message_id, message.text)
            await crud.trim_history(db, message.chat_id, settings.max_chat_history)
            history, session = await crud.history(db, message.chat_id, settings.max_chat_history), await crud.get_session(db, user.id)
            await db.commit()
        if time.monotonic() - _last_response[sender.id] < 3: return
        decision = await context.application.bot_data["llm"].generate(_prompt(message, user, history, session), community_config.system_prompt())
        _last_response[sender.id] = time.monotonic()
        mod = decision.get("moderation_action")
        if mod and community_config.data["moderation_rules"].get("auto_moderation", True) and not community_config.data["moderation_rules"].get("require_admin_approval", False):
            await context.application.bot_data["moderation"].execute_action(mod, decision.get("target_user_id") or sender.id, decision.get("moderation_reason") or "Community rule violation", {"chat_id": message.chat_id, "session_factory": factory})
        if decision.get("should_respond") and decision.get("response_text"):
            await message.reply_text(decision["response_text"])
        async with factory() as db:
            await crud.set_session(db, user.id, f"Last message: {message.text[-1000:]}"); await db.commit()
    except Exception: log.exception("Failed to process message %s", message.message_id)
