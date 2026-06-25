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
