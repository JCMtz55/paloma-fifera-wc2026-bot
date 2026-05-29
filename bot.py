import logging
import os
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

from schedule import MATCHES

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log"),
    ],
)
log = logging.getLogger(__name__)


def format_alert(match: dict) -> str:
    time_str = match["kickoff"].strftime("%H:%M UTC")
    group = match.get("group", "")
    label = f"Group {group}" if group not in ("R32", "R16", "QF", "SF", "3rd", "F") else {
        "R32": "Round of 32", "R16": "Round of 16", "QF": "Quarterfinal",
        "SF": "Semifinal", "3rd": "Third Place", "F": "Final"
    }.get(group, group)
    return (
        f"⚽ *Match starting in 1 hour!*\n\n"
        f"🆚 {match['home']} vs {match['away']}\n"
        f"🏆 {label}\n"
        f"📍 {match.get('venue', '')}\n"
        f"🕐 Kickoff: {time_str}"
    )


def format_upcoming(match: dict, now: datetime) -> str:
    time_until = match["kickoff"] - now
    total_minutes = int(time_until.total_seconds() // 60)
    days, remainder = divmod(total_minutes, 1440)
    hours, minutes = divmod(remainder, 60)

    if days > 0:
        time_label = f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        time_label = f"{hours}h {minutes}m"
    else:
        time_label = f"{minutes}m"

    date_str = match["kickoff"].strftime("%b %d, %H:%M UTC")
    group = match.get("group", "")
    label = f"Group {group}" if group not in ("R32", "R16", "QF", "SF", "3rd", "F") else {
        "R32": "Round of 32", "R16": "Round of 16", "QF": "Quarterfinal",
        "SF": "Semifinal", "3rd": "Third Place", "F": "Final"
    }.get(group, group)
    return (
        f"🆚 *{match['home']} vs {match['away']}*\n"
        f"🏆 {label}  •  📍 {match.get('venue', '')}\n"
        f"🕐 {date_str}  •  ⏳ in {time_label}"
    )


async def check_schedule(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(timezone.utc)
    notified: set = context.bot_data.setdefault("notified", set())

    for match in MATCHES:
        match_id = f"{match['home']}-{match['away']}-{match['kickoff'].isoformat()}"
        time_until = match["kickoff"] - now

        if timedelta(minutes=55) <= time_until <= timedelta(minutes=65):
            if match_id not in notified:
                try:
                    await context.bot.send_message(
                        chat_id=CHAT_ID,
                        text=format_alert(match),
                        parse_mode="Markdown",
                    )
                    notified.add(match_id)
                    log.info(f"Notified: {match['home']} vs {match['away']}")
                except TelegramError as e:
                    log.error(f"Failed to send notification: {e}")


async def upcoming_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(timezone.utc)
    future = sorted(
        [m for m in MATCHES if m["kickoff"] > now],
        key=lambda m: m["kickoff"]
    )[:3]

    if not future:
        await update.message.reply_text("No upcoming matches found.")
        return

    lines = ["📅 *Next 3 matches:*\n"]
    for match in future:
        lines.append(format_upcoming(match, now))

    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("upcoming", upcoming_command))
    app.job_queue.run_repeating(check_schedule, interval=60, first=10)

    log.info(f"Bot started — monitoring {len(MATCHES)} matches.")
    app.run_polling()


if __name__ == "__main__":
    main()
