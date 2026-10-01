from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from telegram import ChatPermissions
from src.config.settings import community_config, settings
from src.db import crud
log = logging.getLogger(__name__)
class ModerationService:
    def __init__(self, bot): self.bot = bot
    async def execute_action(self, action, target_user_id, reason, context, performed_by="AI"):
        if action not in {"warn", "kick", "ban", "mute"} or target_user_id in settings.admin_user_ids: return False
        try:
            async with context["session_factory"]() as db:
                user = await crud.get_user_by_telegram_id(db, target_user_id)
                if not user: return False
                if action == "warn":
                    user.warn_count += 1
                    await self.bot.send_message(context["chat_id"], f"⚠️ {user.first_name or 'Member'}, warning: {reason}")
                    threshold = community_config.data["moderation_rules"].get("max_warnings_before_kick", 3)
                    await crud.log_action(db, user.id, "warn", reason, performed_by)
                    if user.warn_count >= threshold:
                        await self._kick(context["chat_id"], target_user_id); await crud.log_action(db, user.id, "kick", "Warning threshold reached", "AI")
                elif action == "kick": await self._kick(context["chat_id"], target_user_id); await crud.log_action(db, user.id, action, reason, performed_by)
                elif action == "ban":
                    await self.bot.ban_chat_member(context["chat_id"], target_user_id); user.is_banned = True; await crud.log_action(db, user.id, action, reason, performed_by)
                else:
                    until = datetime.now(timezone.utc) + timedelta(minutes=settings.mute_duration_minutes)
                    await self.bot.restrict_chat_member(context["chat_id"], target_user_id, permissions=ChatPermissions.no_permissions(), until_date=until)
                    await crud.log_action(db, user.id, action, reason, performed_by)
                await db.commit()
            await self._notify_admins(f"Moderation: {action} user {target_user_id}. Reason: {reason}")
            return True
        except Exception:
            log.exception("Could not execute %s for user %s", action, target_user_id); return False
    async def _kick(self, chat_id, user_id):
        await self.bot.ban_chat_member(chat_id, user_id); await self.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
    async def _notify_admins(self, text):
        for admin in settings.admin_user_ids:
            try: await self.bot.send_message(admin, text)
            except Exception: log.warning("Unable to notify admin %s", admin)
