from __future__ import annotations
import asyncio, logging, sys, time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from src.bot import commands
from src.bot.handlers import handle_group_message
from src.bot.moderation import ModerationService
from src.config.settings import ROOT, settings
from src.db.database import SessionLocal, close_database, init_database
from src.llm.llm_router import LLMRouter

def configure_logging():
    Path(settings.log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=[logging.StreamHandler(sys.stdout), RotatingFileHandler(settings.log_file, maxBytes=5_000_000, backupCount=5)])
async def post_init(app): await init_database()
async def post_shutdown(app): await close_database()
def main():
    configure_logging()
    if not settings.telegram_bot_token or not SessionLocal: raise RuntimeError("TELEGRAM_BOT_TOKEN and DATABASE_URL must be configured")
    router = LLMRouter(); app = Application.builder().token(settings.telegram_bot_token).post_init(post_init).post_shutdown(post_shutdown).build()
    app.bot_data.update(session_factory=SessionLocal, llm=router, moderation=ModerationService(app.bot), started_at=time.monotonic())
    for name, callback in {"warn":commands.warn,"kick":commands.kick,"ban":commands.ban,"mute":commands.mute,"unwarn":commands.unwarn,"unban":commands.unban,"userinfo":commands.userinfo,"setrules":commands.setrules,"botstatus":commands.botstatus,"clearhistory":commands.clearhistory,"reload":commands.reload_config}.items(): app.add_handler(CommandHandler(name, callback))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, handle_group_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)
if __name__ == "__main__": main()
