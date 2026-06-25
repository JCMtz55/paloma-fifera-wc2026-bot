from datetime import datetime, timezone, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bot import (
    normalize_name,
    is_duplicate,
    map_api_match,
    find_team,
    group_label,
    make_match_key,
    resolve_outcome,
    result_to_outcome,
    compute_odds,
    settle_match,
    outcome_team_label,
)

UTC = timezone.utc


def kickoff(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# ------------------------------------------------------------------ #
#  normalize_name                                                      #
# ------------------------------------------------------------------ #

def test_normalize_known_variants():
    assert normalize_name("Korea Republic") == "South Korea"
    assert normalize_name("IR Iran") == "Iran"
    assert normalize_name("Bosnia and Herzegovina") == "Bosnia-Herzegovina"
    assert normalize_name("Côte d'Ivoire") == "Ivory Coast"
    assert normalize_name("Czechia") == "Czech Republic"
    assert normalize_name("United States") == "USA"


def test_normalize_case_insensitive():
    assert normalize_name("korea republic") == "South Korea"
    assert normalize_name("KOREA REPUBLIC") == "South Korea"


def test_normalize_unknown_returns_original():
    assert normalize_name("Mexico") == "Mexico"
    assert normalize_name("Brazil") == "Brazil"


def test_normalize_none_returns_tbd():
    assert normalize_name(None) == "TBD"
    assert normalize_name("") == "TBD"


# ------------------------------------------------------------------ #
#  group_label                                                         #
# ------------------------------------------------------------------ #

def test_group_label_group_stage():
    assert group_label("A") == "Group A"
    assert group_label("F") == "Group F"   # the bug — was showing "Final"
    assert group_label("L") == "Group L"


def test_group_label_knockout():
    assert group_label("R32") == "Round of 32"
    assert group_label("R16") == "Round of 16"
    assert group_label("QF") == "Quarterfinal"
    assert group_label("SF") == "Semifinal"
    assert group_label("3RD") == "Third Place"
    assert group_label("FIN") == "Final"


def test_group_label_f_is_not_final():
    assert group_label("F") != "Final"


# ------------------------------------------------------------------ #
#  is_duplicate                                                        #
# ------------------------------------------------------------------ #

def make_match(home, away, dt):
    return {"home": home, "away": away, "kickoff": dt, "group": "A", "matchday": 1, "venue": ""}


def test_is_duplicate_exact_match():
    existing = [make_match("Mexico", "South Africa", kickoff(2026, 6, 11, 19))]
    candidate = make_match("Mexico", "South Africa", kickoff(2026, 6, 11, 19))
    assert is_duplicate(candidate, existing)


def test_is_duplicate_api_name_variant():
    existing = [make_match("South Korea", "Czech Republic", kickoff(2026, 6, 12, 3))]
    candidate = make_match("Korea Republic", "Czechia", kickoff(2026, 6, 12, 3))
    assert is_duplicate(candidate, existing)


def test_is_duplicate_different_time_not_duplicate():
    existing = [make_match("Mexico", "South Africa", kickoff(2026, 6, 11, 19))]
    candidate = make_match("Mexico", "South Africa", kickoff(2026, 6, 11, 21))
    assert not is_duplicate(candidate, existing)


def test_is_duplicate_same_time_different_teams_not_duplicate():
    # Matchday 3 — two matches at the same time but different teams
    existing = [make_match("Mexico", "Czech Republic", kickoff(2026, 6, 25, 1))]
    candidate = make_match("South Africa", "South Korea", kickoff(2026, 6, 25, 1))
    assert not is_duplicate(candidate, existing)


def test_is_duplicate_empty_existing():
    assert not is_duplicate(make_match("Brazil", "Morocco", kickoff(2026, 6, 13, 22)), [])


# ------------------------------------------------------------------ #
#  map_api_match                                                       #
# ------------------------------------------------------------------ #

def make_api_match(home, away, utc_date, stage="GROUP_STAGE", group="GROUP_A", matchday=1, venue="Stadium"):
    return {
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "utcDate": utc_date,
        "stage": stage,
        "group": group,
        "matchday": matchday,
        "venue": venue,
    }


def test_map_api_match_group_stage():
    raw = make_api_match("Mexico", "South Africa", "2026-06-11T19:00:00Z", group="GROUP_A")
    result = map_api_match(raw)
    assert result is not None
    assert result["home"] == "Mexico"
    assert result["away"] == "South Africa"
    assert result["group"] == "A"
    assert result["kickoff"] == kickoff(2026, 6, 11, 19)


def test_map_api_match_normalizes_names():
    raw = make_api_match("Korea Republic", "Czechia", "2026-06-12T03:00:00Z", group="GROUP_A")
    result = map_api_match(raw)
    assert result["home"] == "South Korea"
    assert result["away"] == "Czech Republic"


def test_map_api_match_knockout_stage():
    raw = make_api_match("Brazil", "France", "2026-07-10T23:00:00Z", stage="QUARTER_FINALS", group=None)
    result = map_api_match(raw)
    assert result["group"] == "QF"


def test_map_api_match_final():
    raw = make_api_match("TBD", "TBD", "2026-07-26T23:00:00Z", stage="FINAL", group=None)
    result = map_api_match(raw)
    assert result is None  # TBD teams should be skipped


def test_map_api_match_missing_date_returns_none():
    raw = make_api_match("Mexico", "South Africa", "", group="GROUP_A")
    result = map_api_match(raw)
    assert result is None


# ------------------------------------------------------------------ #
#  find_team                                                           #
# ------------------------------------------------------------------ #

def test_find_team_exact():
    assert find_team("Mexico") == "Mexico"


def test_find_team_case_insensitive():
    assert find_team("mexico") == "Mexico"
    assert find_team("BRAZIL") == "Brazil"


def test_find_team_partial():
    assert find_team("south korea") == "South Korea"
    assert find_team("ivory") == "Ivory Coast"


def test_find_team_not_found():
    assert find_team("Wakanda") is None


def test_find_team_multi_word():
    assert find_team("czech republic") == "Czech Republic"
    assert find_team("new zealand") == "New Zealand"
    assert find_team("saudi") == "Saudi Arabia"
    assert find_team("cape verde") == "Cape Verde"


# ------------------------------------------------------------------ #
#  Betting — make_match_key / resolve_outcome / result_to_outcome     #
# ------------------------------------------------------------------ #

MATCH = make_match("Mexico", "USA", kickoff(2026, 6, 22, 19))


def test_make_match_key():
    assert make_match_key(MATCH) == "Mexico vs USA"


def test_resolve_outcome_home_win():
    assert resolve_outcome(MATCH, "Mexico", "win") == "home"


def test_resolve_outcome_away_win():
    assert resolve_outcome(MATCH, "USA", "win") == "away"


def test_resolve_outcome_draw():
    assert resolve_outcome(MATCH, "Mexico", "draw") == "draw"
    assert resolve_outcome(MATCH, "USA", "draw") == "draw"


def test_resolve_outcome_team_not_in_match():
    assert resolve_outcome(MATCH, "Brazil", "win") is None


def test_result_to_outcome_home_team():
    assert result_to_outcome(MATCH, "Mexico", "win") == "home"
    assert result_to_outcome(MATCH, "Mexico", "loss") == "away"
    assert result_to_outcome(MATCH, "Mexico", "tie") == "draw"


def test_result_to_outcome_away_team():
    assert result_to_outcome(MATCH, "USA", "win") == "away"
    assert result_to_outcome(MATCH, "USA", "loss") == "home"
    assert result_to_outcome(MATCH, "USA", "tie") == "draw"


def test_outcome_team_label():
    assert outcome_team_label(MATCH, "home") == "Mexico"
    assert outcome_team_label(MATCH, "away") == "USA"
    assert outcome_team_label(MATCH, "draw") == "Draw"


# ------------------------------------------------------------------ #
#  Betting — compute_odds                                             #
# ------------------------------------------------------------------ #

def test_compute_odds_empty():
    odds = compute_odds({})
    assert odds["total"] == 0
    assert odds["bettors"] == 0
    assert odds["home"]["ratio"] == 0.0


def test_compute_odds_pools_and_ratios():
    bets = {
        "u1": {"outcome": "home", "amount": 100},
        "u2": {"outcome": "home", "amount": 100},
        "u3": {"outcome": "away", "amount": 100},
        "u4": {"outcome": "draw", "amount": 50},
    }
    odds = compute_odds(bets)
    assert odds["total"] == 350
    assert odds["bettors"] == 4
    assert odds["home"]["pool"] == 200
    assert odds["home"]["bets"] == 2
    assert odds["home"]["ratio"] == 350 / 200
    assert odds["away"]["ratio"] == 350 / 100
    assert odds["draw"]["ratio"] == 350 / 50


def test_compute_odds_minimum_ratio_is_one():
    # Solo bettor: pool == total, ratio would be 1.0 (never below)
    bets = {"u1": {"outcome": "home", "amount": 100}}
    odds = compute_odds(bets)
    assert odds["home"]["ratio"] == 1.0


# ------------------------------------------------------------------ #
#  Betting — settle_match                                             #
# ------------------------------------------------------------------ #

def test_settle_match_basic_payouts():
    bets = {
        "u1": {"outcome": "home", "amount": 100},
        "u2": {"outcome": "away", "amount": 100},
    }
    records, no_winners = settle_match(bets, "home")
    assert not no_winners
    by_user = {r["user_id"]: r for r in records}
    # u1 picked home (winner): total 200 / winning pool 100 = 2.0x → 200
    assert by_user["u1"]["won"] is True
    assert by_user["u1"]["payout"] == 200
    # u2 picked away (loser): 0
    assert by_user["u2"]["won"] is False
    assert by_user["u2"]["payout"] == 0


def test_settle_match_floor_rounding():
    bets = {
        "u1": {"outcome": "home", "amount": 100},
        "u2": {"outcome": "home", "amount": 50},
        "u3": {"outcome": "away", "amount": 70},
    }
    # total 220, winning pool 150
    records, no_winners = settle_match(bets, "home")
    by_user = {r["user_id"]: r for r in records}
    assert by_user["u1"]["payout"] == 146   # floor(100 * 220/150) = floor(146.67)
    assert by_user["u2"]["payout"] == 73    # floor(50 * 220/150) = floor(73.33)
    assert by_user["u3"]["payout"] == 0


def test_settle_match_no_winners_refunds_all():
    bets = {
        "u1": {"outcome": "home", "amount": 100},
        "u2": {"outcome": "away", "amount": 80},
    }
    records, no_winners = settle_match(bets, "draw")
    assert no_winners
    by_user = {r["user_id"]: r for r in records}
    assert by_user["u1"]["payout"] == 100   # stake refunded
    assert by_user["u2"]["payout"] == 80
    assert all(r["won"] is False for r in records)


def test_settle_match_solo_winner_gets_stake_back():
    bets = {"u1": {"outcome": "home", "amount": 100}}
    records, no_winners = settle_match(bets, "home")
    assert not no_winners
    assert records[0]["payout"] == 100      # min ratio 1.0x → stake back
