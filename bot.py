import logging
import math
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, PicklePersistence

from schedule import MATCHES

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
# Auto-delete the bot's command replies after this many minutes (0 = never).
AUTO_DELETE_MINUTES = int(os.getenv("AUTO_DELETE_MINUTES", "5"))
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "")
FOOTBALL_API_URL = "https://api.football-data.org/v4/competitions/WC/matches"

# Maps common API name variants to our schedule names
API_NAME_MAP = {
    "korea republic": "South Korea",
    "republic of korea": "South Korea",
    "ir iran": "Iran",
    "islamic republic of iran": "Iran",
    "bosnia and herzegovina": "Bosnia-Herzegovina",
    "côte d'ivoire": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
    "united states": "USA",
    "usa": "USA",
    "dr congo": "DR Congo",
    "democratic republic of congo": "DR Congo",
    "cape verde islands": "Cape Verde",
    "czechia": "Czech Republic",
    "republic of ireland": "Ireland",
}

STAGE_MAP = {
    "GROUP_STAGE": None,        # handled by group letter
    "ROUND_OF_32": "R32",
    "LAST_16": "R16",
    "QUARTER_FINALS": "QF",
    "SEMI_FINALS": "SF",
    "THIRD_PLACE": "3RD",
    "FINAL": "FIN",
}

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
    "SF": "Semifinal", "3RD": "Third Place", "FIN": "Final",
}

GROUP_STAGE = set("ABCDEFGHIJKL")

# ------------------------------------------------------------------ #
#  Betting config                                                     #
# ------------------------------------------------------------------ #

STARTING_BALANCE = 500
MIN_BET = 10
BET_CUTOFF = timedelta(minutes=10)  # bets lock 10 min before kickoff
TOPUP_AMOUNT = 100  # bailout handed out to broke bettors via /topup

OUTCOME_EMOJI = {"home": "🟢", "away": "🔴", "draw": "🤝"}


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def group_label(group: str) -> str:
    if group in GROUP_STAGE:
        return f"Group {group}"
    return KNOCKOUT_LABELS.get(group, group)


def fmt_time(kickoff_utc: datetime) -> str:
    local = kickoff_utc.astimezone(LOCAL_TZ)
    tz_abbr = local.strftime("%Z")
    return f"{local.strftime('%b %d, %I:%M %p')} {tz_abbr}"


def fmt_alert(match: dict, mentions: list[str] | None = None) -> str:
    text = (
        f"⚽ *Match starting in 1 hour!*\n\n"
        f"🆚 {match['home']} vs {match['away']}\n"
        f"🏆 {group_label(match.get('group', ''))}\n"
        f"📍 {match.get('venue', '')}\n"
        f"🕐 Kickoff: {fmt_time(match['kickoff'])}"
    )
    if mentions:
        text += "\n\n" + " ".join(mentions)
    return text


def fmt_showdown(match: dict, home_user: dict, away_user: dict) -> str:
    return (
        f"🔥 *SHOWDOWN ALERT!* 🔥\n\n"
        f"Two of our own are going head to head in *1 hour!*\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"[{home_user['name']}](tg://user?id={home_user['id']}) roots for *{match['home']}*\n"
        f"📊 {home_user['points']} pts | {home_user['goals']} goals\n\n"
        f"⚔️\n\n"
        f"[{away_user['name']}](tg://user?id={away_user['id']}) roots for *{match['away']}*\n"
        f"📊 {away_user['points']} pts | {away_user['goals']} goals\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🏆 {group_label(match.get('group', ''))}  •  📍 {match.get('venue', '')}\n"
        f"🕐 Kickoff: {fmt_time(match['kickoff'])}\n\n"
        f"May the best team win! 🏆"
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


def save_user_name(context: ContextTypes.DEFAULT_TYPE, user) -> None:
    user_names: dict = context.bot_data.setdefault("user_names", {})
    user_names[str(user.id)] = user.first_name or f"User{str(user.id)[-4:]}"


def all_matches(context: ContextTypes.DEFAULT_TYPE) -> list:
    return context.bot_data.get("matches", MATCHES)


def future_matches(now: datetime, context: ContextTypes.DEFAULT_TYPE) -> list:
    return sorted([m for m in all_matches(context) if m["kickoff"] > now], key=lambda m: m["kickoff"])


def normalize_name(name: str | None) -> str:
    if not name:
        return "TBD"
    return API_NAME_MAP.get(name.lower().strip(), name)


def is_duplicate(mapped: dict, existing: list) -> bool:
    home = mapped["home"].lower()
    away = mapped["away"].lower()
    kickoff = mapped["kickoff"]
    for m in existing:
        if abs((m["kickoff"] - kickoff).total_seconds()) > 600:
            continue
        m_home = m["home"].lower()
        m_away = m["away"].lower()
        home_match = home == m_home or any(w in m_home for w in home.split() if len(w) > 3)
        away_match = away == m_away or any(w in m_away for w in away.split() if len(w) > 3)
        if home_match and away_match:
            return True
    return False


def map_api_match(api_match: dict) -> dict | None:
    home = normalize_name((api_match.get("homeTeam") or {}).get("name"))
    away = normalize_name((api_match.get("awayTeam") or {}).get("name"))
    utc_date = api_match.get("utcDate", "")
    if not utc_date or home == "TBD" or away == "TBD":
        return None

    kickoff = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
    stage = api_match.get("stage", "")
    raw_group = api_match.get("group") or ""

    if stage == "GROUP_STAGE" and raw_group:
        group = raw_group.replace("GROUP_", "")[:1]
    else:
        group = STAGE_MAP.get(stage, stage)

    return {
        "home": home,
        "away": away,
        "kickoff": kickoff,
        "group": group,
        "matchday": api_match.get("matchday"),
        "venue": api_match.get("venue") or "",
    }


def find_team(query: str) -> str | None:
    """Return the exact team name from MATCHES that matches the query, or None."""
    q = query.lower()
    all_teams = {m["home"] for m in MATCHES} | {m["away"] for m in MATCHES}
    matches = [t for t in all_teams if q in t.lower()]
    if len(matches) == 1:
        return matches[0]
    # Prefer exact match if multiple partial matches
    exact = [t for t in matches if t.lower() == q]
    return exact[0] if exact else (matches[0] if len(matches) > 0 else None)


def teams_by_group(exclude: set | None = None) -> dict:
    """Group-stage teams keyed by group letter, optionally excluding some teams.

    Groups left with no remaining teams are dropped from the result.
    """
    exclude = exclude or set()
    groups: dict[str, list] = {}
    for m in MATCHES:
        g = m.get("group", "?")
        groups.setdefault(g, [])
        for team in (m["home"], m["away"]):
            if team not in exclude and team not in groups[g]:
                groups[g].append(team)
    return {g: sorted(teams) for g, teams in groups.items() if teams}


# ------------------------------------------------------------------ #
#  Betting helpers (pure functions — unit tested)                     #
# ------------------------------------------------------------------ #

def make_match_key(match: dict) -> str:
    """Deterministic key for a match: 'Home vs Away'."""
    return f"{match['home']} vs {match['away']}"


def resolve_outcome(match: dict, team: str, choice: str) -> str | None:
    """Map a user's bet (team + 'win'/'draw') to 'home'/'away'/'draw'."""
    if choice == "draw":
        return "draw"
    if choice == "win":
        if match["home"] == team:
            return "home"
        if match["away"] == team:
            return "away"
    return None


def result_to_outcome(match: dict, team: str, result_type: str) -> str | None:
    """Map an admin /result (team + win/tie/loss) to the winning outcome."""
    is_home = match["home"] == team
    if result_type == "tie":
        return "draw"
    if result_type == "win":
        return "home" if is_home else "away"
    if result_type == "loss":
        return "away" if is_home else "home"
    return None


def compute_odds(match_bets: dict) -> dict:
    """Parimutuel odds from a match's bets ({user_id: {outcome, amount}})."""
    pools = {"home": 0, "away": 0, "draw": 0}
    counts = {"home": 0, "away": 0, "draw": 0}
    for bet in match_bets.values():
        pools[bet["outcome"]] += bet["amount"]
        counts[bet["outcome"]] += 1
    total = sum(pools.values())
    result = {"total": total, "bettors": len(match_bets)}
    for o in ("home", "away", "draw"):
        wp = pools[o]
        result[o] = {
            "bets": counts[o],
            "pool": wp,
            "ratio": max(total / wp, 1.0) if wp > 0 else 0.0,
        }
    return result


def settle_match(match_bets: dict, winning_outcome: str) -> tuple[list, bool]:
    """Compute payouts for every bet on a match.

    Returns (records, no_winners). Each record is a dict with user_id, amount,
    outcome, won, payout. When nobody picked the winning outcome, every bettor
    is refunded their stake (no_winners=True, all records won=False).
    """
    pools = {"home": 0, "away": 0, "draw": 0}
    for bet in match_bets.values():
        pools[bet["outcome"]] += bet["amount"]
    total = sum(pools.values())
    winning_pool = pools[winning_outcome]
    no_winners = winning_pool == 0

    records = []
    for uid, bet in match_bets.items():
        if no_winners:
            payout, won = bet["amount"], False
        elif bet["outcome"] == winning_outcome:
            payout = max(math.floor(bet["amount"] * total / winning_pool), bet["amount"])
            won = True
        else:
            payout, won = 0, False
        records.append({
            "user_id": uid,
            "amount": bet["amount"],
            "outcome": bet["outcome"],
            "won": won,
            "payout": payout,
        })
    return records, no_winners


def outcome_team_label(match: dict, outcome: str) -> str:
    """Human label for an outcome using real team names."""
    if outcome == "home":
        return match["home"]
    if outcome == "away":
        return match["away"]
    return "Draw"


# ------------------------------------------------------------------ #
#  Betting helpers (context-bound)                                    #
# ------------------------------------------------------------------ #

def get_balance(context: ContextTypes.DEFAULT_TYPE, user_id: str) -> int:
    """Return the user's balance, lazily granting the starting balance."""
    wallets: dict = context.bot_data.setdefault("wallets", {})
    if user_id not in wallets:
        wallets[user_id] = STARTING_BALANCE
    return wallets[user_id]


def next_match_for_team(team: str, context: ContextTypes.DEFAULT_TYPE, now: datetime) -> dict | None:
    upcoming = sorted(
        [m for m in all_matches(context)
         if (m["home"] == team or m["away"] == team) and m["kickoff"] > now],
        key=lambda m: m["kickoff"],
    )
    return upcoming[0] if upcoming else None


def match_to_settle_for_team(team: str, context: ContextTypes.DEFAULT_TYPE, now: datetime) -> dict | None:
    """Most recently kicked-off, not-yet-settled match for a team."""
    settled: set = context.bot_data.get("settled_matches", set())
    past = sorted(
        [m for m in all_matches(context)
         if (m["home"] == team or m["away"] == team)
         and m["kickoff"] < now
         and make_match_key(m) not in settled],
        key=lambda m: m["kickoff"],
        reverse=True,
    )
    return past[0] if past else None


def fmt_odds_inline(match: dict, context: ContextTypes.DEFAULT_TYPE) -> str:
    """One-line odds summary for the 1-hour alert."""
    match_bets = context.bot_data.get("bets", {}).get(make_match_key(match), {})
    odds = compute_odds(match_bets)
    parts = []
    for o in ("home", "draw", "away"):
        label = outcome_team_label(match, o)
        ratio = odds[o]["ratio"]
        ratio_str = f"{ratio:.1f}x" if ratio > 0 else "—"
        parts.append(f"{OUTCOME_EMOJI[o]} {label} {ratio_str}")
    return (
        "\n\n💰 *Betting open — closes in 50 minutes!*\n"
        f"Current odds: {'  '.join(parts)}\n"
        f"Place your bet: `/bet {match['home']} win 50`"
    )


# ------------------------------------------------------------------ #
#  Scheduled job — 1-hour alerts                                      #
# ------------------------------------------------------------------ #

async def check_schedule(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)
    notified: set = context.bot_data.setdefault("notified", set())

    for match in all_matches(context):
        match_id = f"{match['home']}-{match['away']}-{match['kickoff'].isoformat()}"
        time_until = match["kickoff"] - now

        if timedelta(minutes=55) <= time_until <= timedelta(minutes=65):
            if match_id not in notified:
                try:
                    registrations: dict = context.bot_data.get("registrations", {})
                    user_names: dict = context.bot_data.get("user_names", {})
                    team_results: dict = context.bot_data.get("team_results", {})

                    # Find which user owns each team in this match
                    home_owner, away_owner = None, None
                    for uid, teams in registrations.items():
                        if match["home"] in teams:
                            home_owner = uid
                        if match["away"] in teams:
                            away_owner = uid

                    def user_stats(uid: str, team: str) -> dict:
                        teams = registrations.get(uid, [])
                        points = sum(team_results.get(t, {}).get("points", 0) for t in teams)
                        goals = sum(team_results.get(t, {}).get("goals", 0) for t in teams)
                        return {
                            "id": uid,
                            "name": user_names.get(uid, "Fan"),
                            "team": team,
                            "points": points,
                            "goals": goals,
                        }

                    if home_owner and away_owner and home_owner != away_owner:
                        text = fmt_showdown(match, user_stats(home_owner, match["home"]), user_stats(away_owner, match["away"]))
                    else:
                        mentions = []
                        for uid in {home_owner, away_owner} - {None}:
                            name = user_names.get(uid, "Fan")
                            mentions.append(f"[{name}](tg://user?id={uid})")
                        text = fmt_alert(match, mentions or None)

                    text += fmt_odds_inline(match, context)

                    await safe_send_message(
                        context.bot,
                        chat_id=CHAT_ID,
                        text=text,
                        parse_mode="Markdown",
                    )
                    notified.add(match_id)
                    log.info(f"Notified: {match['home']} vs {match['away']}")
                except TelegramError as e:
                    log.error(f"Failed to send notification: {e}")


# ------------------------------------------------------------------ #
#  Daily API sync                                                      #
# ------------------------------------------------------------------ #

async def sync_schedule(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not FOOTBALL_API_KEY:
        log.warning("FOOTBALL_API_KEY not set — skipping sync.")
        return

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                FOOTBALL_API_URL,
                headers={"X-Auth-Token": FOOTBALL_API_KEY},
                params={"season": 2026},
                timeout=10,
            )
            r.raise_for_status()
            api_matches = r.json().get("matches", [])
    except Exception as e:
        log.error(f"Schedule sync failed: {e}")
        return

    mapped_matches = [m for m in (map_api_match(a) for a in api_matches) if m]

    if not mapped_matches:
        log.warning("API returned no matches — keeping existing schedule.")
        return

    previous = context.bot_data.get("matches", [])
    context.bot_data["matches"] = mapped_matches
    log.info(f"Schedule synced: {len(mapped_matches)} matches loaded.")

    # Announce newly added matches (e.g. knockout stage fixtures)
    prev_keys = {(m["home"], m["away"]) for m in previous}
    new_matches = [m for m in mapped_matches if (m["home"], m["away"]) not in prev_keys]

    if new_matches and previous:  # skip announcement on first sync
        lines = ["📋 *New matches announced:*\n"]
        for m in new_matches:
            lines.append(
                f"🆚 *{m['home']} vs {m['away']}*  —  {group_label(m.get('group', ''))}\n"
                f"🕐 {fmt_time(m['kickoff'])}"
            )
        await safe_send_message(
            context.bot,
            chat_id=CHAT_ID,
            text="\n\n".join(lines),
            parse_mode="Markdown",
        )


# ------------------------------------------------------------------ #
#  Ephemeral replies                                                   #
# ------------------------------------------------------------------ #

async def _delete_message_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id, message_id = context.job.data
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramError:
        pass  # already deleted, or older than Telegram's 48h delete window


async def safe_send_message(bot, chat_id, text, **kwargs):
    """Send a message, falling back to plain text if Markdown parsing fails."""
    try:
        return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except BadRequest as e:
        log.warning(f"send_message failed ({e}); retrying without parse_mode")
        kwargs.pop("parse_mode", None)
        return await bot.send_message(chat_id=chat_id, text=text, **kwargs)


async def reply_ephemeral(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    """Reply to a command and auto-delete the reply after AUTO_DELETE_MINUTES."""
    try:
        msg = await update.message.reply_text(text, **kwargs)
    except BadRequest as e:
        # Usually a Markdown parse failure from a stray special char in dynamic
        # content. Retry as plain text so the user always gets a reply.
        log.warning(f"reply_text failed ({e}); retrying without parse_mode")
        kwargs.pop("parse_mode", None)
        msg = await update.message.reply_text(text, **kwargs)
    if AUTO_DELETE_MINUTES > 0:
        context.job_queue.run_once(
            _delete_message_job,
            when=timedelta(minutes=AUTO_DELETE_MINUTES),
            data=(msg.chat_id, msg.message_id),
        )
    return msg


# ------------------------------------------------------------------ #
#  Commands                                                            #
# ------------------------------------------------------------------ #

async def cmd_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    save_user_name(context, update.effective_user)
    now = datetime.now(tz=UTC)
    matches = future_matches(now, context)[:3]

    if not matches:
        await reply_ephemeral(update, context, "No upcoming matches found.")
        return

    lines = ["📅 *Next 3 matches:*\n"]
    lines += [fmt_match(m, now) for m in matches]
    await reply_ephemeral(update, context, "\n\n".join(lines), parse_mode="Markdown")


async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)
    matches = future_matches(now, context)

    if not matches:
        await reply_ephemeral(update, context, "No upcoming matches found.")
        return

    await reply_ephemeral(update, context, fmt_match(matches[0], now), parse_mode="Markdown")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)
    today_local = now.astimezone(LOCAL_TZ).date()

    matches = [m for m in all_matches(context) if m["kickoff"].astimezone(LOCAL_TZ).date() == today_local]
    matches.sort(key=lambda m: m["kickoff"])

    if not matches:
        await reply_ephemeral(update, context, "No matches today.")
        return

    lines = [f"📅 *Matches today ({today_local.strftime('%b %d')}):*\n"]
    for m in matches:
        lines.append(
            f"🆚 *{m['home']} vs {m['away']}*\n"
            f"🏆 {group_label(m.get('group', ''))}  •  📍 {m.get('venue', '')}\n"
            f"🕐 {fmt_time(m['kickoff'])}"
        )
    await reply_ephemeral(update, context, "\n\n".join(lines), parse_mode="Markdown")


async def cmd_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)
    tomorrow_local = (now.astimezone(LOCAL_TZ) + timedelta(days=1)).date()

    matches = [m for m in all_matches(context) if m["kickoff"].astimezone(LOCAL_TZ).date() == tomorrow_local]
    matches.sort(key=lambda m: m["kickoff"])

    if not matches:
        await reply_ephemeral(update, context, "No matches tomorrow.")
        return

    lines = [f"📅 *Matches tomorrow ({tomorrow_local.strftime('%b %d')}):*\n"]
    for m in matches:
        lines.append(
            f"🆚 *{m['home']} vs {m['away']}*\n"
            f"🏆 {group_label(m.get('group', ''))}  •  📍 {m.get('venue', '')}\n"
            f"🕐 {fmt_time(m['kickoff'])}"
        )
    await reply_ephemeral(update, context, "\n\n".join(lines), parse_mode="Markdown")


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    save_user_name(context, update.effective_user)
    now = datetime.now(tz=UTC)
    week_end = now + timedelta(days=7)

    matches = [
        m for m in all_matches(context)
        if now < m["kickoff"] <= week_end
    ]
    matches.sort(key=lambda m: m["kickoff"])

    if not matches:
        await reply_ephemeral(update, context, "No matches in the next 7 days.")
        return

    # Group by local date for readability
    from collections import defaultdict
    by_day = defaultdict(list)
    for m in matches:
        day = m["kickoff"].astimezone(LOCAL_TZ).strftime("%A, %b %d")
        by_day[day].append(m)

    lines = ["📅 *Matches this week*"]
    for day, day_matches in by_day.items():
        lines.append(f"\n📆 *{day}*")
        for m in day_matches:
            local = m["kickoff"].astimezone(LOCAL_TZ)
            time_str = local.strftime("%I:%M %p").lstrip("0")
            tz_abbr = local.strftime("%Z")
            label = group_label(m.get("group", ""))
            lines.append(f"`{time_str} {tz_abbr}`  {m['home']} vs {m['away']}  ·  _{label}_")

    await reply_ephemeral(update, context, "\n".join(lines), parse_mode="Markdown")


async def cmd_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)

    if not context.args:
        await reply_ephemeral(update, context, "Usage: /group A")
        return

    letter = context.args[0].upper()
    matches = [m for m in all_matches(context) if m.get("group") == letter]
    matches.sort(key=lambda m: m["kickoff"])

    if not matches:
        await reply_ephemeral(update, context, f"No matches found for Group {letter}.")
        return

    lines = [f"📅 *Group {letter} schedule:*\n"]
    for m in matches:
        status = "✅" if m["kickoff"] < now else "🕐"
        lines.append(
            f"🆚 *{m['home']} vs {m['away']}*  (MD{m.get('matchday', '?')})\n"
            f"📍 {m.get('venue', '')}  •  {status} {fmt_time(m['kickoff'])}"
        )
    await reply_ephemeral(update, context, "\n\n".join(lines), parse_mode="Markdown")


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)

    if not context.args:
        await reply_ephemeral(update, context, "Usage: /schedule Mexico")
        return

    team = " ".join(context.args).lower()
    matches = [
        m for m in all_matches(context)
        if team in m["home"].lower() or team in m["away"].lower()
    ]
    matches.sort(key=lambda m: m["kickoff"])

    if not matches:
        await reply_ephemeral(update, context, f"No matches found for \"{' '.join(context.args)}\".")
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
    await reply_ephemeral(update, context, "\n\n".join(lines), parse_mode="Markdown")


async def cmd_teams(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    eliminated: set = context.bot_data.get("eliminated", set())
    groups = teams_by_group(exclude=eliminated)

    if not groups:
        await reply_ephemeral(update, context, "All teams have been eliminated! 🏆")
        return

    lines = ["🌍 *Active Teams:*\n"]
    for g in sorted(groups):
        lines.append(f"*Group {g}:* {' • '.join(groups[g])}")

    if eliminated:
        lines.append(f"\n_{len(eliminated)} team(s) eliminated — see /eliminated_")
    lines.append("\nUse /register followed by the team name to add it to your list.")
    await reply_ephemeral(update, context, "\n".join(lines), parse_mode="Markdown")


async def cmd_eliminated(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    save_user_name(context, update.effective_user)
    eliminated: set = context.bot_data.setdefault("eliminated", set())

    # No args → anyone can view the list of eliminated teams.
    if not context.args:
        if not eliminated:
            await reply_ephemeral(update, context, "✅ No teams have been eliminated yet.")
            return
        lines = ["❌ *Eliminated teams:*\n"]
        lines += [f"• {t}" for t in sorted(eliminated)]
        await reply_ephemeral(update, context, "\n".join(lines), parse_mode="Markdown")
        return

    # With a team arg → admin marks a team as eliminated.
    if update.effective_user.id != ADMIN_ID:
        await reply_ephemeral(update, context, "❌ Only the admin can mark teams as eliminated.")
        return

    team = find_team(" ".join(context.args))
    if not team:
        await reply_ephemeral(update, context, "❌ Team not found. Use /teams to see all team names.")
        return

    if team in eliminated:
        await reply_ephemeral(update, context, f"*{team}* is already eliminated.", parse_mode="Markdown")
        return

    eliminated.add(team)
    await reply_ephemeral(update, context, f"❌ *{team}* has been eliminated.", parse_mode="Markdown")


async def cmd_revive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await reply_ephemeral(update, context, "❌ You don't have permission to use this command.")
        return

    if not context.args:
        await reply_ephemeral(update, context, "Usage: /revive Mexico")
        return

    team = find_team(" ".join(context.args))
    eliminated: set = context.bot_data.setdefault("eliminated", set())
    if not team or team not in eliminated:
        await reply_ephemeral(update, context, "❌ That team isn't on the eliminated list.")
        return

    eliminated.remove(team)
    await reply_ephemeral(update, context, f"✅ *{team}* is back in — removed from the eliminated list.", parse_mode="Markdown")


async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await reply_ephemeral(update, context, "Usage: /register Mexico")
        return

    team = find_team(" ".join(context.args))
    if not team:
        await reply_ephemeral(update, context, f"❌ Team not found. Check the spelling and try again.")
        return

    user_id = str(update.effective_user.id)
    registrations: dict = context.bot_data.setdefault("registrations", {})
    user_teams: list = registrations.setdefault(user_id, [])

    if team in user_teams:
        await reply_ephemeral(update, context, f"You already have *{team}* registered.", parse_mode="Markdown")
        return

    user_teams.append(team)

    # Store display name for leaderboard
    user_names: dict = context.bot_data.setdefault("user_names", {})
    user_names[user_id] = update.effective_user.first_name or f"User{user_id[-4:]}"

    await reply_ephemeral(update, context, f"✅ *{team}* added to your teams.", parse_mode="Markdown")


async def cmd_unregister(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await reply_ephemeral(update, context, "Usage: /unregister Mexico")
        return

    team = find_team(" ".join(context.args))
    user_id = str(update.effective_user.id)
    registrations: dict = context.bot_data.get("registrations", {})
    user_teams: list = registrations.get(user_id, [])

    if not team or team not in user_teams:
        await reply_ephemeral(update, context, f"❌ That team isn't in your list.")
        return

    user_teams.remove(team)
    await reply_ephemeral(update, context, f"✅ *{team}* removed from your teams.", parse_mode="Markdown")


async def cmd_myteams(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    save_user_name(context, update.effective_user)
    now = datetime.now(tz=UTC)
    user_id = str(update.effective_user.id)
    registrations: dict = context.bot_data.get("registrations", {})
    user_teams: list = registrations.get(user_id, [])

    if not user_teams:
        await reply_ephemeral(update, context, 
            "You have no teams registered. Use /register Mexico to add one."
        )
        return

    lines = [f"⭐ *Your teams:*\n"]
    for team in user_teams:
        team_matches = [
            m for m in all_matches(context)
            if m["home"] == team or m["away"] == team
        ]
        next_match = next((m for m in sorted(team_matches, key=lambda m: m["kickoff"]) if m["kickoff"] > now), None)

        if next_match:
            opponent = next_match["away"] if next_match["home"] == team else next_match["home"]
            side = "vs" if next_match["home"] == team else "@"
            time_until = next_match["kickoff"] - now
            mins = int(time_until.total_seconds() // 60)
            days, rem = divmod(mins, 1440)
            hours, minutes = divmod(rem, 60)
            countdown = f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            lines.append(
                f"🏳 *{team}*\n"
                f"Next: {side} {opponent}  —  {group_label(next_match.get('group', ''))} MD{next_match.get('matchday', '?')}\n"
                f"📍 {next_match.get('venue', '')}  •  🕐 {fmt_time(next_match['kickoff'])}  •  ⏳ in {countdown}"
            )
        else:
            lines.append(f"🏳 *{team}*\nNo upcoming matches.")

    await reply_ephemeral(update, context, "\n\n".join(lines), parse_mode="Markdown")


async def cmd_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await reply_ephemeral(update, context, "❌ You don't have permission to use this command.")
        return

    if len(context.args) < 3:
        await reply_ephemeral(update, context, "Usage: /result Mexico win 3\nResult must be: win, tie, or loss")
        return

    # Find where the result keyword is — everything before it is the team name
    result_keywords = ("win", "tie", "loss")
    split_index = next(
        (i for i, a in enumerate(context.args) if a.lower() in result_keywords), None
    )
    if split_index is None or split_index == 0:
        await reply_ephemeral(update, context, "❌ Result must be: win, tie, or loss\nUsage: /result South Korea win 3")
        return

    team_query = " ".join(context.args[:split_index])
    result_type = context.args[split_index].lower()

    try:
        goals = int(context.args[split_index + 1])
    except (IndexError, ValueError):
        await reply_ephemeral(update, context, "❌ Goals must be a number.\nUsage: /result South Korea win 3")
        return

    team = find_team(team_query)
    if not team:
        await reply_ephemeral(update, context, "❌ Team not found. Use /teams to see all team names.")
        return

    points = {"win": 2, "tie": 1, "loss": 0}[result_type]

    team_results: dict = context.bot_data.setdefault("team_results", {})
    if team not in team_results:
        team_results[team] = {"points": 0, "goals": 0}
    team_results[team]["points"] += points
    team_results[team]["goals"] += goals

    result_emoji = {"win": "✅", "tie": "🤝", "loss": "❌"}[result_type]
    await reply_ephemeral(update, context, 
        f"{result_emoji} *{team}* — {result_type} | {goals} goals | +{points} pts",
        parse_mode="Markdown",
    )

    await settle_bets(context, team, result_type)


async def settle_bets(context: ContextTypes.DEFAULT_TYPE, team: str, result_type: str) -> None:
    """Settle any open bets on the team's most recent match and announce payouts."""
    now = datetime.now(tz=UTC)
    match = match_to_settle_for_team(team, context, now)
    if not match:
        return

    key = make_match_key(match)
    bets: dict = context.bot_data.setdefault("bets", {})
    settled: set = context.bot_data.setdefault("settled_matches", set())
    match_bets = bets.get(key, {})

    # Mark settled regardless, so /result can't double-settle the same match.
    settled.add(key)

    if not match_bets:
        return

    winning_outcome = result_to_outcome(match, team, result_type)
    if winning_outcome is None:
        return

    records, no_winners = settle_match(match_bets, winning_outcome)

    wallets: dict = context.bot_data.setdefault("wallets", {})
    history: list = context.bot_data.setdefault("bet_history", [])
    user_names: dict = context.bot_data.get("user_names", {})
    odds = compute_odds(match_bets)
    ratio = odds[winning_outcome]["ratio"]

    winner_lines = []
    for rec in records:
        if rec["payout"] > 0:
            wallets[rec["user_id"]] = wallets.get(rec["user_id"], STARTING_BALANCE) + rec["payout"]
        history.append({
            "match_key": key,
            "user_id": rec["user_id"],
            "outcome": rec["outcome"],
            "amount": rec["amount"],
            "won": rec["won"],
            "payout": rec["payout"],
            "settled_at": now.isoformat(),
        })
        if rec["won"]:
            name = user_names.get(rec["user_id"], f"User{rec['user_id'][-4:]}")
            gain = rec["payout"] - rec["amount"]
            winner_lines.append(
                f"  🎉 {name} +{gain:,} 🪙  (was {rec['amount']:,} 🪙 @ {ratio:.1f}x) "
                f"→ {wallets[rec['user_id']]:,} 🪙 total"
            )

    # Remove the settled match's bets
    del bets[key]

    win_label = outcome_team_label(match, winning_outcome)
    text = (
        f"💰 *Bet Results — {match['home']} vs {match['away']}*\n\n"
        f"Winning outcome: {OUTCOME_EMOJI[winning_outcome]} {win_label}\n"
    )
    if no_winners:
        text += "\nNo winning bets — pool returned to bettors."
    else:
        text += "\n*Winners:*\n" + "\n".join(winner_lines)

    try:
        await safe_send_message(context.bot, chat_id=CHAT_ID, text=text, parse_mode="Markdown")
    except TelegramError as e:
        log.error(f"Failed to send settlement announcement: {e}")



async def cmd_syncnow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await reply_ephemeral(update, context, "❌ You don't have permission to use this command.")
        return
    await reply_ephemeral(update, context, "🔄 Fetching schedule from API...")
    await sync_schedule(context)
    count = len(context.bot_data.get("matches", []))
    await reply_ephemeral(update, context, f"✅ Done — {count} matches loaded.")


async def cmd_adjust(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await reply_ephemeral(update, context, "❌ You don't have permission to use this command.")
        return

    if len(context.args) < 3:
        await reply_ephemeral(update, context, 
            "Usage: /adjust Mexico -2 -3\n"
            "First number = points delta, second = goals delta\n"
            "Use negative numbers to subtract."
        )
        return

    # Find where numbers start — everything before is the team name
    split_index = next(
        (i for i, a in enumerate(context.args) if a.lstrip("+-").isdigit()), None
    )
    if split_index is None or split_index == 0:
        await reply_ephemeral(update, context, "❌ Could not parse command. Usage: /adjust Mexico -2 -3")
        return

    team_query = " ".join(context.args[:split_index])
    team = find_team(team_query)
    if not team:
        await reply_ephemeral(update, context, "❌ Team not found. Use /teams to see all team names.")
        return

    try:
        points_delta = int(context.args[split_index])
        goals_delta = int(context.args[split_index + 1])
    except (IndexError, ValueError):
        await reply_ephemeral(update, context, "❌ Points and goals must be numbers. Usage: /adjust Mexico -2 -3")
        return

    team_results: dict = context.bot_data.setdefault("team_results", {})
    if team not in team_results:
        team_results[team] = {"points": 0, "goals": 0}

    team_results[team]["points"] += points_delta
    team_results[team]["goals"] += goals_delta

    p = team_results[team]["points"]
    g = team_results[team]["goals"]
    await reply_ephemeral(update, context, 
        f"✅ *{team}* adjusted.\n"
        f"Points: {'+' if points_delta >= 0 else ''}{points_delta} → *{p} pts total*\n"
        f"Goals: {'+' if goals_delta >= 0 else ''}{goals_delta} → *{g} goals total*",
        parse_mode="Markdown",
    )


async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    save_user_name(context, update.effective_user)
    registrations: dict = context.bot_data.get("registrations", {})
    user_names: dict = context.bot_data.get("user_names", {})
    team_results: dict = context.bot_data.get("team_results", {})

    if not registrations:
        await reply_ephemeral(update, context, "No users registered yet. Use /register to join.")
        return

    scores = []
    for user_id, teams in registrations.items():
        if not teams:
            continue
        total_points = sum(team_results.get(t, {}).get("points", 0) for t in teams)
        total_goals = sum(team_results.get(t, {}).get("goals", 0) for t in teams)
        name = user_names.get(user_id, f"User{user_id[-4:]}")
        scores.append({"name": name, "points": total_points, "goals": total_goals, "teams": teams})

    scores.sort(key=lambda x: (-x["points"], -x["goals"]))

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 *Leaderboard:*\n"]
    for i, s in enumerate(scores):
        rank = medals[i] if i < 3 else f"{i + 1}\\."
        teams_str = " • ".join(s["teams"])
        lines.append(
            f"{rank} *{s['name']}* — {s['points']} pts | {s['goals']} goals\n"
            f"   {teams_str}"
        )

    await reply_ephemeral(update, context, "\n\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------ #
#  Betting commands                                                    #
# ------------------------------------------------------------------ #

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    save_user_name(context, update.effective_user)
    user_id = str(update.effective_user.id)
    wallets: dict = context.bot_data.setdefault("wallets", {})
    first_time = user_id not in wallets
    balance = get_balance(context, user_id)

    if first_time:
        await reply_ephemeral(update, context, 
            f"👋 Welcome! You've been granted *{STARTING_BALANCE:,} 🪙* to start betting.\n\n"
            f"Use /bet Mexico win 50 to place your first bet, or /odds Mexico to see the lines.",
            parse_mode="Markdown",
        )
    else:
        await reply_ephemeral(update, context, 
            f"🪙 Your balance: *{balance:,} coins*", parse_mode="Markdown"
        )


async def cmd_bet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    save_user_name(context, update.effective_user)
    now = datetime.now(tz=UTC)

    if len(context.args) < 3:
        await reply_ephemeral(update, context, 
            "Usage: /bet <team> <win|draw> <amount>\nExample: /bet Mexico win 50"
        )
        return

    choice = context.args[-2].lower()
    amount_raw = context.args[-1]
    team_query = " ".join(context.args[:-2])

    if choice not in ("win", "draw"):
        await reply_ephemeral(update, context, "❌ Outcome must be `win` or `draw`.\nExample: /bet Mexico win 50", parse_mode="Markdown")
        return

    try:
        amount = int(amount_raw)
    except ValueError:
        await reply_ephemeral(update, context, "❌ Amount must be a whole number.\nExample: /bet Mexico win 50")
        return

    if amount < MIN_BET:
        await reply_ephemeral(update, context, f"❌ Minimum bet is {MIN_BET} coins.")
        return

    team = find_team(team_query)
    if not team:
        await reply_ephemeral(update, context, "❌ Team not found. Use /teams to see all team names.")
        return

    match = next_match_for_team(team, context, now)
    if not match or now >= match["kickoff"] - BET_CUTOFF:
        await reply_ephemeral(update, context, "❌ Bets for this match are closed.")
        return

    outcome = resolve_outcome(match, team, choice)
    if outcome is None:
        await reply_ephemeral(update, context, "❌ Couldn't read that bet. Example: /bet Mexico win 50")
        return

    user_id = str(update.effective_user.id)
    balance = get_balance(context, user_id)
    key = make_match_key(match)
    bets: dict = context.bot_data.setdefault("bets", {})
    match_bets: dict = bets.setdefault(key, {})

    # Replacing an existing bet: refund the old stake first.
    replaced = None
    if user_id in match_bets:
        replaced = match_bets[user_id]
        balance += replaced["amount"]

    if amount > balance:
        await reply_ephemeral(update, context, f"❌ Not enough coins. Your balance: {balance:,} 🪙")
        return

    context.bot_data["wallets"][user_id] = balance - amount
    match_bets[user_id] = {"outcome": outcome, "amount": amount}

    pick = "Draw" if outcome == "draw" else f"{outcome_team_label(match, outcome)} to win"
    lines = []
    if replaced:
        old_pick = "Draw" if replaced["outcome"] == "draw" else f"{outcome_team_label(match, replaced['outcome'])} to win"
        lines.append(
            f"⚠️ You already bet on this match. Your previous bet of "
            f"{replaced['amount']:,} 🪙 on {old_pick} has been replaced.\n"
        )
    lines.append(
        f"✅ *Bet placed!*\n"
        f"{match['home']} vs {match['away']}  —  {group_label(match.get('group', ''))}\n"
        f"Your pick: {OUTCOME_EMOJI[outcome]} {pick}\n"
        f"Amount: {amount:,} 🪙\n"
        f"Balance: {context.bot_data['wallets'][user_id]:,} 🪙"
    )
    await reply_ephemeral(update, context, "\n".join(lines), parse_mode="Markdown")


async def cmd_odds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)
    if not context.args:
        await reply_ephemeral(update, context, "Usage: /odds Mexico")
        return

    team = find_team(" ".join(context.args))
    if not team:
        await reply_ephemeral(update, context, "❌ Team not found. Use /teams to see all team names.")
        return

    match = next_match_for_team(team, context, now)
    if not match:
        await reply_ephemeral(update, context, f"No upcoming match found for {team}.")
        return

    key = make_match_key(match)
    match_bets = context.bot_data.get("bets", {}).get(key, {})
    odds = compute_odds(match_bets)

    closed = now >= match["kickoff"] - BET_CUTOFF
    if closed:
        status = "🔒 Betting closed"
    else:
        time_left = match["kickoff"] - BET_CUTOFF - now
        mins = int(time_left.total_seconds() // 60)
        hrs, m = divmod(mins, 60)
        status = f"Closes in {hrs}h {m}m" if hrs else f"Closes in {m}m"

    header = (
        f"📊 *Live Odds — {match['home']} vs {match['away']}*\n"
        f"{group_label(match.get('group', ''))}  •  {status}"
    )

    if odds["total"] == 0:
        await reply_ephemeral(update, context, 
            f"{header}\n\nNo bets placed yet — be the first!", parse_mode="Markdown"
        )
        return

    rows = []
    for o in ("home", "draw", "away"):
        label = outcome_team_label(match, o)
        ratio = odds[o]["ratio"]
        ratio_str = f"{ratio:.1f}x" if ratio > 0 else "—"
        rows.append(
            f"{OUTCOME_EMOJI[o]} {label} — {odds[o]['bets']} bets · "
            f"{odds[o]['pool']:,} 🪙 · {ratio_str}"
        )

    await reply_ephemeral(update, context, 
        f"{header}\n\n" + "\n".join(rows) +
        f"\n\nTotal pool: {odds['total']:,} 🪙 | {odds['bettors']} bettors",
        parse_mode="Markdown",
    )


async def cmd_mybets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    save_user_name(context, update.effective_user)
    user_id = str(update.effective_user.id)
    bets: dict = context.bot_data.get("bets", {})

    # Map match_key → match dict for the open bets
    matches_by_key = {make_match_key(m): m for m in all_matches(context)}

    user_bets = []
    for key, match_bets in bets.items():
        if user_id in match_bets and key in matches_by_key:
            user_bets.append((matches_by_key[key], match_bets))

    if not user_bets:
        await reply_ephemeral(update, context, 
            "You have no open bets. Use /bet Mexico win 50 to place one."
        )
        return

    user_bets.sort(key=lambda mb: mb[0]["kickoff"])
    lines = ["📋 *Your open bets:*\n"]
    for i, (match, match_bets) in enumerate(user_bets, 1):
        bet = match_bets[user_id]
        odds = compute_odds(match_bets)
        ratio = odds[bet["outcome"]]["ratio"]
        est = math.floor(bet["amount"] * ratio) if ratio > 0 else bet["amount"]
        pick = "Draw" if bet["outcome"] == "draw" else outcome_team_label(match, bet["outcome"])
        day = match["kickoff"].astimezone(LOCAL_TZ).strftime("%b %d")
        lines.append(
            f"{i}. *{match['home']} vs {match['away']}*  ({group_label(match.get('group', ''))}, {day})\n"
            f"   Pick: {OUTCOME_EMOJI[bet['outcome']]} {pick}  •  {bet['amount']:,} 🪙  •  "
            f"odds {ratio:.1f}x → est. {est:,} 🪙"
        )

    await reply_ephemeral(update, context, "\n\n".join(lines), parse_mode="Markdown")


async def cmd_betleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    save_user_name(context, update.effective_user)
    wallets: dict = context.bot_data.get("wallets", {})
    user_names: dict = context.bot_data.get("user_names", {})
    history: list = context.bot_data.get("bet_history", [])

    if not wallets:
        await reply_ephemeral(update, context, "No bets placed yet. Use /bet to join in.")
        return

    # Tally wins / total settled bets per user
    wins: dict = {}
    totals: dict = {}
    for rec in history:
        uid = rec["user_id"]
        totals[uid] = totals.get(uid, 0) + 1
        if rec["won"]:
            wins[uid] = wins.get(uid, 0) + 1

    scores = sorted(
        wallets.items(), key=lambda kv: kv[1], reverse=True
    )

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🪙 *Betting Leaderboard:*\n"]
    for i, (uid, balance) in enumerate(scores):
        rank = medals[i] if i < 3 else f"{i + 1}\\."
        name = user_names.get(uid, f"User{uid[-4:]}")
        w = wins.get(uid, 0)
        t = totals.get(uid, 0)
        bet_word = "bet" if t == 1 else "bets"
        win_word = "win" if w == 1 else "wins"
        lines.append(f"{rank} *{name}* — {balance:,} 🪙  ({w} {win_word} / {t} {bet_word})")

    await reply_ephemeral(update, context, "\n".join(lines), parse_mode="Markdown")


async def cmd_cancelbet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await reply_ephemeral(update, context, "❌ You don't have permission to use this command.")
        return

    now = datetime.now(tz=UTC)
    if not context.args:
        await reply_ephemeral(update, context, "Usage: /cancelbet Mexico")
        return

    team = find_team(" ".join(context.args))
    if not team:
        await reply_ephemeral(update, context, "❌ Team not found. Use /teams to see all team names.")
        return

    match = next_match_for_team(team, context, now)
    if not match:
        await reply_ephemeral(update, context, f"No upcoming match found for {team}.")
        return

    key = make_match_key(match)
    bets: dict = context.bot_data.setdefault("bets", {})
    match_bets = bets.get(key, {})

    if not match_bets:
        await reply_ephemeral(update, context, f"No bets to refund on {key}.")
        return

    wallets: dict = context.bot_data.setdefault("wallets", {})
    total_refunded = 0
    for uid, bet in match_bets.items():
        wallets[uid] = wallets.get(uid, STARTING_BALANCE) + bet["amount"]
        total_refunded += bet["amount"]
    count = len(match_bets)
    del bets[key]

    await reply_ephemeral(update, context, 
        f"✅ All bets on {key} have been refunded.\n"
        f"{count} {'bet' if count == 1 else 'bets'} · {total_refunded:,} 🪙 returned to bettors.",
    )


async def cmd_topup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await reply_ephemeral(update, context, "❌ You don't have permission to use this command.")
        return

    wallets: dict = context.bot_data.setdefault("wallets", {})
    user_names: dict = context.bot_data.get("user_names", {})

    topped = [uid for uid, balance in wallets.items() if balance <= 0]
    if not topped:
        await reply_ephemeral(update, context, "No users are at 0 coins — nobody needs a top-up.")
        return

    for uid in topped:
        wallets[uid] = TOPUP_AMOUNT

    names = ", ".join(user_names.get(uid, f"User{uid[-4:]}") for uid in topped)
    count = len(topped)
    await reply_ephemeral(update, context, f"✅ Topped up {count} broke {'bettor' if count == 1 else 'bettors'} to {TOPUP_AMOUNT} 🪙.")

    try:
        await safe_send_message(
            context.bot,
            chat_id=CHAT_ID,
            text=(
                f"🎁 *Bailout!* {count} broke {'bettor' if count == 1 else 'bettors'} "
                f"got a fresh {TOPUP_AMOUNT} 🪙 to get back in the game:\n{names}"
            ),
            parse_mode="Markdown",
        )
    except TelegramError as e:
        log.error(f"Failed to send top-up announcement: {e}")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "⚽ *World Cup 2026 Bot*\n\n"
        "I'll automatically notify the group 1 hour before every match. "
        "All times are shown in PT.\n\n"
        "*Commands:*\n"
        "/upcoming — Next 3 upcoming matches\n"
        "/week — All matches in the next 7 days\n"
        "/next — The very next match\n"
        "/today — All matches today\n"
        "/tomorrow — All matches tomorrow\n"
        "/group A — Full schedule for a group (A-L)\n"
        "/schedule Mexico — All matches for a specific team\n"
        "/teams — List active teams by group\n"
        "/eliminated — See which teams are out\n"
        "/register Mexico — Add a team to your personal list\n"
        "/unregister Mexico — Remove a team from your list\n"
        "/myteams — Your teams and their next matches\n"
        "/result Mexico win 3 — Log a match result (win/tie/loss + goals)\n"
        "/leaderboard — Show standings with points and goals\n"
        "/help — Show this message\n\n"
        "*Betting (fake coins 🪙):*\n"
        "/balance — Check your coin balance\n"
        "/bet Mexico win 50 — Bet 50 coins on Mexico to win (or `draw`)\n"
        "/odds Mexico — Live pool odds for Mexico's next match\n"
        "/mybets — Your open bets\n"
        "/betleaderboard — Betting standings"
    )
    await reply_ephemeral(update, context, text, parse_mode="Markdown")


# ------------------------------------------------------------------ #
#  Error handler                                                       #
# ------------------------------------------------------------------ #

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Exception while handling an update:", exc_info=context.error)


# ------------------------------------------------------------------ #
#  Entry point                                                         #
# ------------------------------------------------------------------ #

def main() -> None:
    data_path = os.getenv("DATA_PATH", ".")
    persistence = PicklePersistence(filepath=os.path.join(data_path, "bot_data.pkl"))
    app = Application.builder().token(BOT_TOKEN).persistence(persistence).build()

    app.add_handler(CommandHandler("upcoming", cmd_upcoming))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("tomorrow", cmd_tomorrow))
    app.add_handler(CommandHandler("group", cmd_group))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("teams", cmd_teams))
    app.add_handler(CommandHandler("eliminated", cmd_eliminated))
    app.add_handler(CommandHandler("revive", cmd_revive))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("unregister", cmd_unregister))
    app.add_handler(CommandHandler("myteams", cmd_myteams))
    app.add_handler(CommandHandler("syncnow", cmd_syncnow))
    app.add_handler(CommandHandler("result", cmd_result))
    app.add_handler(CommandHandler("adjust", cmd_adjust))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("bet", cmd_bet))
    app.add_handler(CommandHandler("odds", cmd_odds))
    app.add_handler(CommandHandler("mybets", cmd_mybets))
    app.add_handler(CommandHandler("betleaderboard", cmd_betleaderboard))
    app.add_handler(CommandHandler("cancelbet", cmd_cancelbet))
    app.add_handler(CommandHandler("topup", cmd_topup))
    app.add_handler(CommandHandler("help", cmd_help))

    app.add_error_handler(on_error)

    app.job_queue.run_repeating(check_schedule, interval=60, first=10)
    app.job_queue.run_once(sync_schedule, when=5)  # sync immediately on startup
    app.job_queue.run_daily(sync_schedule, time=datetime.strptime("07:00", "%H:%M").time().replace(tzinfo=UTC))

    log.info(f"Bot started — monitoring {len(MATCHES)} matches.")
    app.run_polling()


if __name__ == "__main__":
    main()
