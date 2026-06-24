import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, PicklePersistence

from schedule import MATCHES

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "")
FOOTBALL_API_URL = "https://api.football-data.org/v4/competitions/WC/matches"

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
    return MATCHES + context.bot_data.get("dynamic_matches", [])


def future_matches(now: datetime, context: ContextTypes.DEFAULT_TYPE) -> list:
    return sorted([m for m in all_matches(context) if m["kickoff"] > now], key=lambda m: m["kickoff"])


def map_api_match(api_match: dict) -> dict | None:
    home = api_match.get("homeTeam", {}).get("name", "TBD")
    away = api_match.get("awayTeam", {}).get("name", "TBD")
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

                    await context.bot.send_message(
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

    now = datetime.now(tz=UTC)
    date_from = now.strftime("%Y-%m-%d")
    date_to = (now + timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                FOOTBALL_API_URL,
                headers={"X-Auth-Token": FOOTBALL_API_KEY},
                params={"dateFrom": date_from, "dateTo": date_to, "season": 2026},
                timeout=10,
            )
            r.raise_for_status()
            api_matches = r.json().get("matches", [])
    except Exception as e:
        log.error(f"Schedule sync failed: {e}")
        return

    dynamic_matches: list = context.bot_data.setdefault("dynamic_matches", [])
    existing = {(m["home"], m["away"]) for m in MATCHES + dynamic_matches}

    new_matches = []
    for api_match in api_matches:
        mapped = map_api_match(api_match)
        if not mapped:
            continue
        key = (mapped["home"], mapped["away"])
        if key not in existing:
            dynamic_matches.append(mapped)
            existing.add(key)
            new_matches.append(mapped)
            log.info(f"New match added: {mapped['home']} vs {mapped['away']}")

    if new_matches:
        lines = ["📋 *Schedule updated — new matches announced:*\n"]
        for m in new_matches:
            lines.append(
                f"🆚 *{m['home']} vs {m['away']}*  —  {group_label(m['group'])}\n"
                f"🕐 {fmt_time(m['kickoff'])}"
            )
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text="\n\n".join(lines),
            parse_mode="Markdown",
        )
    else:
        log.info("Schedule sync complete — no new matches.")


# ------------------------------------------------------------------ #
#  Commands                                                            #
# ------------------------------------------------------------------ #

async def cmd_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    save_user_name(context, update.effective_user)
    now = datetime.now(tz=UTC)
    matches = future_matches(now, context)[:3]

    if not matches:
        await update.message.reply_text("No upcoming matches found.")
        return

    lines = ["📅 *Next 3 matches:*\n"]
    lines += [fmt_match(m, now) for m in matches]
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)
    matches = future_matches(now, context)

    if not matches:
        await update.message.reply_text("No upcoming matches found.")
        return

    await update.message.reply_text(fmt_match(matches[0], now), parse_mode="Markdown")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=UTC)
    today_local = now.astimezone(LOCAL_TZ).date()

    matches = [m for m in all_matches(context) if m["kickoff"].astimezone(LOCAL_TZ).date() == today_local]
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

    matches = [m for m in all_matches(context) if m["kickoff"].astimezone(LOCAL_TZ).date() == tomorrow_local]
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
    matches = [m for m in all_matches(context) if m.get("group") == letter]
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
        m for m in all_matches(context)
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


async def cmd_teams(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    groups: dict[str, list] = {}
    for m in MATCHES:
        g = m.get("group", "?")
        if g not in groups:
            groups[g] = []
        for team in (m["home"], m["away"]):
            if team not in groups[g]:
                groups[g].append(team)

    lines = ["🌍 *World Cup 2026 Teams:*\n"]
    for g in sorted(groups):
        teams = sorted(groups[g])
        lines.append(f"*Group {g}:* {' • '.join(teams)}")

    lines.append("\nUse /register followed by the team name to add it to your list.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /register Mexico")
        return

    team = find_team(" ".join(context.args))
    if not team:
        await update.message.reply_text(f"❌ Team not found. Check the spelling and try again.")
        return

    user_id = str(update.effective_user.id)
    registrations: dict = context.bot_data.setdefault("registrations", {})
    user_teams: list = registrations.setdefault(user_id, [])

    if team in user_teams:
        await update.message.reply_text(f"You already have *{team}* registered.", parse_mode="Markdown")
        return

    user_teams.append(team)

    # Store display name for leaderboard
    user_names: dict = context.bot_data.setdefault("user_names", {})
    user_names[user_id] = update.effective_user.first_name or f"User{user_id[-4:]}"

    await update.message.reply_text(f"✅ *{team}* added to your teams.", parse_mode="Markdown")


async def cmd_unregister(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /unregister Mexico")
        return

    team = find_team(" ".join(context.args))
    user_id = str(update.effective_user.id)
    registrations: dict = context.bot_data.get("registrations", {})
    user_teams: list = registrations.get(user_id, [])

    if not team or team not in user_teams:
        await update.message.reply_text(f"❌ That team isn't in your list.")
        return

    user_teams.remove(team)
    await update.message.reply_text(f"✅ *{team}* removed from your teams.", parse_mode="Markdown")


async def cmd_myteams(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    save_user_name(context, update.effective_user)
    now = datetime.now(tz=UTC)
    user_id = str(update.effective_user.id)
    registrations: dict = context.bot_data.get("registrations", {})
    user_teams: list = registrations.get(user_id, [])

    if not user_teams:
        await update.message.reply_text(
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

    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return

    if len(context.args) < 3:
        await update.message.reply_text("Usage: /result Mexico win 3\nResult must be: win, tie, or loss")
        return

    # Find where the result keyword is — everything before it is the team name
    result_keywords = ("win", "tie", "loss")
    split_index = next(
        (i for i, a in enumerate(context.args) if a.lower() in result_keywords), None
    )
    if split_index is None or split_index == 0:
        await update.message.reply_text("❌ Result must be: win, tie, or loss\nUsage: /result South Korea win 3")
        return

    team_query = " ".join(context.args[:split_index])
    result_type = context.args[split_index].lower()

    try:
        goals = int(context.args[split_index + 1])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Goals must be a number.\nUsage: /result South Korea win 3")
        return

    team = find_team(team_query)
    if not team:
        await update.message.reply_text("❌ Team not found. Use /teams to see all team names.")
        return

    points = {"win": 2, "tie": 1, "loss": 0}[result_type]

    team_results: dict = context.bot_data.setdefault("team_results", {})
    if team not in team_results:
        team_results[team] = {"points": 0, "goals": 0}
    team_results[team]["points"] += points
    team_results[team]["goals"] += goals

    result_emoji = {"win": "✅", "tie": "🤝", "loss": "❌"}[result_type]
    await update.message.reply_text(
        f"{result_emoji} *{team}* — {result_type} | {goals} goals | +{points} pts",
        parse_mode="Markdown",
    )


async def cmd_adjust(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
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
        await update.message.reply_text("❌ Could not parse command. Usage: /adjust Mexico -2 -3")
        return

    team_query = " ".join(context.args[:split_index])
    team = find_team(team_query)
    if not team:
        await update.message.reply_text("❌ Team not found. Use /teams to see all team names.")
        return

    try:
        points_delta = int(context.args[split_index])
        goals_delta = int(context.args[split_index + 1])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Points and goals must be numbers. Usage: /adjust Mexico -2 -3")
        return

    team_results: dict = context.bot_data.setdefault("team_results", {})
    if team not in team_results:
        team_results[team] = {"points": 0, "goals": 0}

    team_results[team]["points"] += points_delta
    team_results[team]["goals"] += goals_delta

    p = team_results[team]["points"]
    g = team_results[team]["goals"]
    await update.message.reply_text(
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
        await update.message.reply_text("No users registered yet. Use /register to join.")
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
        "/group A — Full schedule for a group (A-L)\n"
        "/schedule Mexico — All matches for a specific team\n"
        "/teams — List all teams by group\n"
        "/register Mexico — Add a team to your personal list\n"
        "/unregister Mexico — Remove a team from your list\n"
        "/myteams — Your teams and their next matches\n"
        "/result Mexico win 3 — Log a match result (win/tie/loss + goals)\n"
        "/leaderboard — Show standings with points and goals\n"
        "/help — Show this message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ------------------------------------------------------------------ #
#  Entry point                                                         #
# ------------------------------------------------------------------ #

def main() -> None:
    data_path = os.getenv("DATA_PATH", ".")
    persistence = PicklePersistence(filepath=os.path.join(data_path, "bot_data.pkl"))
    app = Application.builder().token(BOT_TOKEN).persistence(persistence).build()

    app.add_handler(CommandHandler("upcoming", cmd_upcoming))
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("tomorrow", cmd_tomorrow))
    app.add_handler(CommandHandler("group", cmd_group))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("teams", cmd_teams))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("unregister", cmd_unregister))
    app.add_handler(CommandHandler("myteams", cmd_myteams))
    app.add_handler(CommandHandler("result", cmd_result))
    app.add_handler(CommandHandler("adjust", cmd_adjust))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CommandHandler("help", cmd_help))

    app.job_queue.run_repeating(check_schedule, interval=60, first=10)
    app.job_queue.run_daily(sync_schedule, time=datetime.strptime("07:00", "%H:%M").time().replace(tzinfo=UTC))

    log.info(f"Bot started — monitoring {len(MATCHES)} matches.")
    app.run_polling()


if __name__ == "__main__":
    main()
