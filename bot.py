import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
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

UTC = ZoneInfo("UTC")
LOCAL_TZ = ZoneInfo("America/Los_Angeles")

KNOCKOUT_LABELS = {
    "R32": "Round of 32", "R16": "Round of 16", "QF": "Quarterfinal",
    "SF": "Semifinal", "3rd": "Third Place", "F": "Final",
}


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def group_label(group: str) -> str:
    return KNOCKOUT_LABELS.get(group, f"Group {group}")


def fmt_time(kickoff_utc: datetime) -> str:
    local = kickoff_utc.astimezone(LOCAL_TZ)
    tz_abbr = local.strftime("%Z")
    return f"{local.strftime('%b %d, %I:%M %p')} {tz_abbr}"


def fmt_alert(match: dict) -> str:
    return (
        f"⚽ *Match starting in 1 hour!*\n\n"
        f"🆚 {match['home']} vs {match['away']}\n"
        f"🏆 {group_label(match.get('group', ''))}\n"
        f"📍 {match.get('venue', '')}\n"
        f"🕐 Kickoff: {fmt_time(match['kickoff'])}"
    )


def fmt_match(match: dict, now: datetime) -> str:
    time_until = match["kickoff"] - now
    mins = int(time_until.total_seconds() // 60)
    days, rem = divmod(mins, 1440)
    hours, minutes = divmod(rem, 60)
    if days > 0:
        countdown = f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        countdown = f"{hours}h {minutes}m"
    else:
        countdown = f"{minutes}m"

    return (
        f"🆚 *{match['home']} vs {match['away']}*\n"
        f"🏆 {group_label(match.get('group', ''))}  •  📍 {match.get('venue', '')}\n"
        f"🕐 {fmt_time(match['kickoff'])}  •  ⏳ in {countdown}"
    )


def future_matches(now: datetime) -> list:
    return sorted([m for m in MATCHES if m["kickoff"] > now], key=lambda m: m["kickoff"])


# ------------------------------------------------------------------ #
#  Scheduled job — 1-hour alerts                                      #
# ------------------------------------------------------------------ #

async def check_schedule(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)
    notified: set = context.bot_data.setdefault("notified", set())

    for match in MATCHES:
        match_id = f"{match['home']}-{match['away']}-{match['kickoff'].isoformat()}"
        time_until = match["kickoff"] - now

        if timedelta(minutes=55) <= time_until <= timedelta(minutes=65):
            if match_id not in notified:
                try:
                    await context.bot.send_message(
                        chat_id=CHAT_ID,
                        text=fmt_alert(match),
                        parse_mode="Markdown",
                    )
                    notified.add(match_id)
                    log.info(f"Notified: {match['home']} vs {match['away']}")
                except TelegramError as e:
                    log.error(f"Failed to send notification: {e}")


# ------------------------------------------------------------------ #
#  Commands                                                            #
# ------------------------------------------------------------------ #

async def cmd_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)
    matches = future_matches(now)[:3]

    if not matches:
        await update.message.reply_text("No upcoming matches found.")
        return

    lines = ["📅 *Next 3 matches:*\n"]
    lines += [fmt_match(m, now) for m in matches]
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)
    matches = future_matches(now)

    if not matches:
        await update.message.reply_text("No upcoming matches found.")
        return

    await update.message.reply_text(fmt_match(matches[0], now), parse_mode="Markdown")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)
    today_local = now.astimezone(LOCAL_TZ).date()

    matches = [m for m in MATCHES if m["kickoff"].astimezone(LOCAL_TZ).date() == today_local]
    matches.sort(key=lambda m: m["kickoff"])

    if not matches:
        await update.message.reply_text("No matches today.")
        return

    lines = [f"📅 *Matches today ({today_local.strftime('%b %d')}):*\n"]
    for m in matches:
        lines.append(
            f"🆚 *{m['home']} vs {m['away']}*\n"
            f"🏆 {group_label(m.get('group', ''))}  •  📍 {m.get('venue', '')}\n"
            f"🕐 {fmt_time(m['kickoff'])}"
        )
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)
    tomorrow_local = (now.astimezone(LOCAL_TZ) + timedelta(days=1)).date()

    matches = [m for m in MATCHES if m["kickoff"].astimezone(LOCAL_TZ).date() == tomorrow_local]
    matches.sort(key=lambda m: m["kickoff"])

    if not matches:
        await update.message.reply_text("No matches tomorrow.")
        return

    lines = [f"📅 *Matches tomorrow ({tomorrow_local.strftime('%b %d')}):*\n"]
    for m in matches:
        lines.append(
            f"🆚 *{m['home']} vs {m['away']}*\n"
            f"🏆 {group_label(m.get('group', ''))}  •  📍 {m.get('venue', '')}\n"
            f"🕐 {fmt_time(m['kickoff'])}"
        )
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)

    if not context.args:
        await update.message.reply_text("Usage: /group A")
        return

    letter = context.args[0].upper()
    matches = [m for m in MATCHES if m.get("group") == letter]
    matches.sort(key=lambda m: m["kickoff"])

    if not matches:
        await update.message.reply_text(f"No matches found for Group {letter}.")
        return

    lines = [f"📅 *Group {letter} schedule:*\n"]
    for m in matches:
        status = "✅" if m["kickoff"] < now else "🕐"
        lines.append(
            f"🆚 *{m['home']} vs {m['away']}*  (MD{m.get('matchday', '?')})\n"
            f"📍 {m.get('venue', '')}  •  {status} {fmt_time(m['kickoff'])}"
        )
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)

    if not context.args:
        await update.message.reply_text("Usage: /schedule Mexico")
        return

    team = " ".join(context.args).lower()
    matches = [
        m for m in MATCHES
        if team in m["home"].lower() or team in m["away"].lower()
    ]
    matches.sort(key=lambda m: m["kickoff"])

    if not matches:
        await update.message.reply_text(f"No matches found for \"{' '.join(context.args)}\".")
        return

    team_display = matches[0]["home"] if team in matches[0]["home"].lower() else matches[0]["away"]
    lines = [f"📅 *{team_display} schedule:*\n"]
    for m in matches:
        status = "✅" if m["kickoff"] < now else "⏳"
        opponent = m["away"] if team in m["home"].lower() else m["home"]
        side = "vs" if team in m["home"].lower() else "@"
        lines.append(
            f"{status} *{side} {opponent}*  —  {group_label(m.get('group', ''))} MD{m.get('matchday', '?')}\n"
            f"📍 {m.get('venue', '')}  •  🕐 {fmt_time(m['kickoff'])}"
        )
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "⚽ *World Cup 2026 Bot*\n\n"
        "I'll automatically notify the group 1 hour before every match. "
        "All times are shown in PT.\n\n"
        "*Commands:*\n"
        "/upcoming — Next 3 upcoming matches\n"
        "/next — The very next match\n"
        "/today — All matches today\n"
        "/tomorrow — All matches tomorrow\n"
        "/group A — Full schedule for a group \\(A–L\\)\n"
        "/schedule Mexico — All matches for a specific team\n"
        "/help — Show this message"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


# ------------------------------------------------------------------ #
#  Entry point                                                         #
# ------------------------------------------------------------------ #

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("upcoming", cmd_upcoming))
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("tomorrow", cmd_tomorrow))
    app.add_handler(CommandHandler("group", cmd_group))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("help", cmd_help))

    app.job_queue.run_repeating(check_schedule, interval=60, first=10)

    log.info(f"Bot started — monitoring {len(MATCHES)} matches.")
    app.run_polling()


if __name__ == "__main__":
    main()
