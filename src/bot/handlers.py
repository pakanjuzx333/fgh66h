from __future__ import annotations
import logging
import time
from telegram import Update
from telegram.ext import ContextTypes
from src.config.settings import community_config, settings
from src.db import crud
log = logging.getLogger(__name__)
_last_reply: dict[int, float] = {}
def _prompt(text, user, history, session):
    # Approximate character budget keeps prompts inside the configured local context.
    transcript = "\n".join(f"{m.user_id}: {m.text}" for m in history)[-(settings.local_context_length * 3):]
    return (f"User profile: telegram_id={user.telegram_id}; username={user.username}; warnings={user.warn_count}; joined={user.joined_at}; notes={user.notes}.\n"
            f"Session: {session.context_summary if session else ''}\nRecent chat:\n{transcript}\n\n"
            f"Current message from {user.telegram_id}: {text}\n"
            "Assess this message. Only reply when directly addressed, asked a project question, or a helpful short intervention is needed. "
            "Always assess moderation. Moderate only the current sender. Output JSON only.")
async def _delete_message(update: Update) -> None:
    try: await update.effective_message.delete()
    except Exception: log.warning("Could not delete message %s (missing Telegram permission?)", update.effective_message.message_id)
async def _process_ai(chat_id, telegram_id, text, message, application):
    """Run off the Telegram update path; model latency cannot block ingestion."""
    factory = application.bot_data["session_factory"]
    try:
        async with factory() as db:
            user = await crud.get_user_by_telegram_id(db, telegram_id)
            if not user: return
            history = await crud.history(db, chat_id, settings.max_chat_history)
            session = await crud.get_session(db, user.id)
        decision = await application.bot_data["llm"].generate(_prompt(text, user, history, session), community_config.system_prompt())
        action = decision.get("moderation_action")
        if action and community_config.data["moderation_rules"].get("auto_moderation", True) and not community_config.data["moderation_rules"].get("require_admin_approval", False):
            await application.bot_data["moderation"].execute_action(action, telegram_id, decision.get("moderation_reason") or "Community rule violation", {"chat_id": chat_id, "session_factory": factory})
        now = time.monotonic()
        if decision.get("should_respond") and decision.get("response_text") and now - _last_reply.get(telegram_id, 0) >= settings.max_ai_response_per_user_seconds:
            try:
                await application.bot.send_message(chat_id, decision["response_text"], reply_to_message_id=message.message_id)
                _last_reply[telegram_id] = now
            except Exception: log.exception("Could not send AI response")
        async with factory() as db:
            await crud.set_session(db, user.id, f"Last message: {text[-1000:]}"); await db.commit()
    except Exception: log.exception("Failed AI processing for message %s", message.message_id)
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, sender = update.effective_message, update.effective_user
    if not message or not sender or not message.text or sender.is_bot: return
    if settings.telegram_group_id and message.chat_id != settings.telegram_group_id: return
    factory = context.application.bot_data["session_factory"]
    try:
        async with factory() as db:
            user = await crud.upsert_user(db, sender.id, sender.username, sender.first_name)
            await crud.add_message(db, message.chat_id, user.id, message.message_id, message.text)
            await crud.trim_history(db, message.chat_id, settings.max_chat_history)
            await db.commit()
        verdict = context.application.bot_data["fast_moderator"].inspect(message.chat_id, sender.id, message.text, sender.id in settings.admin_user_ids)
        if verdict.action:
            if verdict.delete_message: await _delete_message(update)
            await context.application.bot_data["moderation"].execute_action(verdict.action, sender.id, verdict.reason or "Fast moderation rule", {"chat_id": message.chat_id, "session_factory": factory})
            return
        await context.application.bot_data["inference_pipeline"].submit((message.chat_id, sender.id), lambda: _process_ai(message.chat_id, sender.id, message.text, message, context.application))
    except Exception: log.exception("Failed to ingest message %s", message.message_id)
