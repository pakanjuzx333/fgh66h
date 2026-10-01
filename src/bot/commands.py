from __future__ import annotations
import logging, time
from datetime import datetime, timedelta, timezone
from telegram import ChatPermissions, Update
from telegram.ext import ContextTypes
from sqlalchemy import text
from src.config.settings import community_config, settings
from src.db import crud
log = logging.getLogger(__name__)
def _admin(update): return bool(update.effective_user and update.effective_user.id in settings.admin_user_ids)
async def _guard(update):
    if _admin(update): return True
    if update.effective_message: await update.effective_message.reply_text("This command is restricted to bot administrators.")
    return False
async def _target(db, args):
    if not args: return None
    value = args[0].lstrip("@")
    if value.lstrip("-").isdigit(): return await crud.get_user_by_telegram_id(db, int(value))
    from src.db.models import User
    from sqlalchemy import select
    return await db.scalar(select(User).where(User.username == value))
async def _action(update, context, action):
    if not await _guard(update): return
    args = context.args; factory = context.application.bot_data["session_factory"]
    async with factory() as db: user = await _target(db, args)
    if not user: await update.message.reply_text("Usage: /%s @user [reason] (the user must have a stored profile)." % action); return
    offset = 1
    if action == "mute" and len(args) > 1 and args[1].isdigit(): settings.mute_duration_minutes = int(args[1]); offset = 2
    reason = " ".join(args[offset:]) or "Manual moderation action"
    ok = await context.application.bot_data["moderation"].execute_action(action, user.telegram_id, reason, {"chat_id": update.effective_chat.id, "session_factory": factory}, update.effective_user.username or str(update.effective_user.id))
    await update.message.reply_text("Action completed." if ok else "Action failed; check bot permissions and logs.")
async def warn(u,c): await _action(u,c,"warn")
async def kick(u,c): await _action(u,c,"kick")
async def ban(u,c): await _action(u,c,"ban")
async def mute(u,c): await _action(u,c,"mute")
async def unwarn(update, context):
    if not await _guard(update): return
    async with context.application.bot_data["session_factory"]() as db:
        user = await _target(db, context.args)
        if user: user.warn_count = max(0, user.warn_count - 1); await db.commit()
    await update.message.reply_text("Warning removed." if user else "User not found.")
async def unban(update, context):
    if not await _guard(update): return
    async with context.application.bot_data["session_factory"]() as db: user = await _target(db, context.args)
    if not user: await update.message.reply_text("User not found."); return
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, user.telegram_id); user.is_banned = False
        async with context.application.bot_data["session_factory"]() as db: db_user=await crud.get_user_by_telegram_id(db,user.telegram_id); db_user.is_banned=False; await db.commit()
        await update.message.reply_text("User unbanned.")
    except Exception: log.exception("Unban failed"); await update.message.reply_text("Unban failed.")
async def userinfo(update, context):
    if not await _guard(update): return
    async with context.application.bot_data["session_factory"]() as db:
        user = await _target(db, context.args)
        if not user: await update.message.reply_text("User not found."); return
        actions = await crud.moderation_history(db, user.id)
        history = "\n".join(f"• {a.action}: {a.reason}" for a in actions) or "None"
        await update.message.reply_text(f"User: @{user.username or user.telegram_id}\nWarnings: {user.warn_count}\nJoined: {user.joined_at}\nModeration history:\n{history}")
async def setrules(update, context):
    if await _guard(update): await update.message.reply_text(str(community_config.data.get("moderation_rules", {}))[:4000])
async def botstatus(update, context):
    if not await _guard(update): return
    try:
        async with context.application.bot_data["session_factory"]() as db: await db.execute(text("SELECT 1")); database="connected"
    except Exception: database="unavailable"
    up=int(time.monotonic()-context.application.bot_data["started_at"])
    await update.message.reply_text(f"LLM: {context.application.bot_data['llm'].name}\nDatabase: {database}\nUptime: {up}s")
async def clearhistory(update, context):
    if not await _guard(update): return
    async with context.application.bot_data["session_factory"]() as db: await crud.clear_history(db, update.effective_chat.id); await db.commit()
    await update.message.reply_text("Chat history cleared.")
async def reload_config(update, context):
    if not await _guard(update): return
    try: community_config.reload(); await update.message.reply_text("Configuration reloaded.")
    except Exception: log.exception("Reload failed"); await update.message.reply_text("Configuration reload failed.")
