from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Message, ModerationLog, Session, User

async def upsert_user(db: AsyncSession, telegram_id: int, username: str | None, first_name: str | None) -> User:
    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None:
        user = User(telegram_id=telegram_id, username=username, first_name=first_name); db.add(user)
    else: user.username, user.first_name, user.last_seen = username, first_name, datetime.now(timezone.utc)
    await db.flush(); return user
async def get_user_by_telegram_id(db, telegram_id): return await db.scalar(select(User).where(User.telegram_id == telegram_id))
async def add_message(db, chat_id, user_id, message_id, text):
    db.add(Message(chat_id=chat_id, user_id=user_id, message_id=message_id, text=text)); await db.flush()
async def history(db, chat_id, limit):
    items = (await db.scalars(select(Message).where(Message.chat_id == chat_id).order_by(desc(Message.timestamp)).limit(limit))).all()
    return list(reversed(items))
async def trim_history(db, chat_id, limit):
    ids = (await db.scalars(select(Message.id).where(Message.chat_id == chat_id).order_by(desc(Message.timestamp)).offset(limit))).all()
    if ids: await db.execute(delete(Message).where(Message.id.in_(ids)))
async def clear_history(db, chat_id): await db.execute(delete(Message).where(Message.chat_id == chat_id))
async def get_session(db, user_id): return await db.scalar(select(Session).where(Session.user_id == user_id))
async def set_session(db, user_id, summary):
    session = await get_session(db, user_id)
    if session: session.context_summary = summary
    else: db.add(Session(user_id=user_id, context_summary=summary))
async def log_action(db, user_id, action, reason, performed_by): db.add(ModerationLog(target_user_id=user_id, action=action, reason=reason, performed_by=performed_by))
async def moderation_history(db, user_id): return (await db.scalars(select(ModerationLog).where(ModerationLog.target_user_id == user_id).order_by(desc(ModerationLog.performed_at)).limit(10))).all()
