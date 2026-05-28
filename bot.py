import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError

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


def format_message(match: dict) -> str:
    kickoff_utc = match["kickoff"]
    time_str = kickoff_utc.strftime("%H:%M UTC")
    group = match.get("group", "")
    venue = match.get("venue", "")
    label = f"Group {group}" if group not in ("R32", "R16", "QF", "SF", "3rd", "F") else {
        "R32": "Round of 32", "R16": "Round of 16", "QF": "Quarterfinal",
        "SF": "Semifinal", "3rd": "Third Place", "F": "Final"
    }.get(group, group)
    return (
        f"⚽ *Match starting in 1 hour!*\n\n"
        f"🆚 {match['home']} vs {match['away']}\n"
        f"🏆 {label}\n"
        f"📍 {venue}\n"
        f"🕐 Kickoff: {time_str}"
    )


async def notify(bot: Bot, match: dict) -> None:
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=format_message(match),
            parse_mode="Markdown",
        )
        log.info(f"Notification sent: {match['home']} vs {match['away']}")
    except TelegramError as e:
        log.error(f"Failed to send notification: {e}")


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    notified = set()  # track sent notifications to avoid duplicates

    log.info(f"Bot started — monitoring {len(MATCHES)} matches.")

    while True:
        now = datetime.now(timezone.utc)

        for match in MATCHES:
            match_id = f"{match['home']}-{match['away']}-{match['kickoff'].isoformat()}"
            time_until = match["kickoff"] - now

            if timedelta(minutes=55) <= time_until <= timedelta(minutes=65):
                if match_id not in notified:
                    await notify(bot, match)
                    notified.add(match_id)

        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
