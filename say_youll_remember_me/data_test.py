"""The bundled files: that they read, that every row is a team call-it-what-you-want
knows, and that the answers to a few questions anybody could check are right."""

import pytest

from . import (
    COACHING_STAFFS,
    FIRED,
    HEAD_COACH_CHANGES,
    LEAGUES,
    LEFT_FOR_JOB,
    NFL,
    QUARTERBACKS,
    RESIGNED,
    RETIRED,
    coaching_staffs,
    departure,
    head_coach_changes,
    passer_seasons,
    quarterback_seasons,
    quarterbacks,
    registry,
    rows_from_csv,
    staff,
    team_id,
    to_csv,
    week_one_starter,
)
from .data import bundled_text

KINDS = [
    (HEAD_COACH_CHANGES, head_coach_changes),
    (COACHING_STAFFS, coaching_staffs),
    (QUARTERBACKS, quarterback_seasons),
]
ALL = [(kind, read, league) for kind, read in KINDS for league in LEAGUES]
IDS = [f"{league}-{kind}" for kind, _, league in ALL]


@pytest.mark.parametrize("kind, read, league", ALL, ids=IDS)
def test_every_row_is_a_team_the_registry_knows(kind, read, league) -> None:
    teams = registry(league)
    rows = read(league)
    assert rows
    unknown = {row.espn_id for row in rows} - {t.espn_id for t in teams}
    assert not unknown, f"{kind} has ESPN ids call-it-what-you-want doesn't: {unknown}"


@pytest.mark.parametrize("kind, read, league", ALL, ids=IDS)
def test_the_files_round_trip(kind, read, league) -> None:
    assert to_csv(kind, read(league)) == bundled_text(kind, league)


@pytest.mark.parametrize("league", LEAGUES)
def test_one_staff_per_team_season(league) -> None:
    keys = [(r.espn_id, r.season) for r in coaching_staffs(league)]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("league", LEAGUES)
def test_one_row_per_quarterback_team_season(league) -> None:
    keys = [(r.espn_id, r.season, r.player_key) for r in quarterback_seasons(league)]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("league", LEAGUES)
def test_at_most_one_week_one_starter_per_team_season(league) -> None:
    seen = [
        (r.espn_id, r.season) for r in quarterback_seasons(league) if r.started_week_one
    ]
    assert len(seen) == len(set(seen))


def test_a_team_is_asked_about_by_any_name_or_id() -> None:
    assert (
        team_id("App State Mountaineers")
        == team_id("Appalachian State Mountaineers")
        == team_id(team_id("App State Mountaineers"))
    )


# What anybody who follows the sport could check. If one of these fails
# after a rebuild, the parser moved, not the history.


def test_fired_then_hired_as_an_assistant_is_a_firing() -> None:
    # The article's reason cell says where Tom Allen landed, not that he was
    # let go -- which is exactly the row that reads as "left for a job".
    change = departure("Indiana Hoosiers", 2024)
    assert change is not None
    assert (change.outgoing, change.reason, change.incoming) == (
        "Tom Allen",
        FIRED,
        "Curt Cignetti",
    )


def test_a_coach_hired_away_after_the_regular_season_left_for_a_job() -> None:
    change = departure("Oregon State Beavers", 2024)
    assert change is not None
    assert change.outgoing == "Jonathan Smith"
    assert change.reason == LEFT_FOR_JOB
    assert not change.midseason


def test_a_mid_season_firing_answers_for_the_next_season() -> None:
    change = departure("Florida State Seminoles", 2020)
    assert change is not None
    assert (change.outgoing, change.reason, change.midseason, change.season) == (
        "Willie Taggart",
        FIRED,
        True,
        2019,
    )


def test_a_retirement() -> None:
    change = departure("Alabama Crimson Tide", 2024)
    assert change is not None
    assert (change.outgoing, change.reason) == ("Nick Saban", RETIRED)


def test_no_change_is_none() -> None:
    assert departure("Georgia Bulldogs", 2024) is None


def test_a_staff() -> None:
    found = staff("Michigan Wolverines", 2021)
    assert found is not None
    assert (found.head_coach, found.defensive_coordinator, found.dc_year) == (
        "Jim Harbaugh",
        "Mike Macdonald",
        1,
    )


def test_a_week_one_starter() -> None:
    found = week_one_starter("LSU Tigers", 2019)
    assert found is not None
    assert found.player_key == "burrow j"
    assert found.epa_per_attempt is not None and found.epa_per_attempt > 0.3


def test_quarterbacks_come_most_starts_first() -> None:
    found = quarterbacks("LSU Tigers", 2019)
    assert [r.starts for r in found] == sorted((r.starts for r in found), reverse=True)


def test_a_transfer_is_found_at_both_schools() -> None:
    before = passer_seasons("mestemaker d", 2025)
    after = passer_seasons("mestemaker d", 2026)
    assert [r.team for r in before] == ["North Texas Mean Green"]
    assert [r.team for r in after] == ["Oklahoma State Cowboys"]


def test_a_file_missing_a_column_is_refused() -> None:
    with pytest.raises(ValueError, match="missing"):
        rows_from_csv(QUARTERBACKS, ["espn_id,team,season", "1,A,2020"])


def test_a_reason_outside_the_categories_is_refused() -> None:
    header = bundled_text(HEAD_COACH_CHANGES).splitlines()[0]
    row = "1,A,2020,in_season,false,,X,false,sacked,Sacked,,false,src"
    with pytest.raises(ValueError, match="row 2"):
        rows_from_csv(HEAD_COACH_CHANGES, [header, row])


# --- the NFL ---------------------------------------------------------------


def test_nfl_ids_are_the_nfls() -> None:
    # 2 is the Bills there and Auburn here.
    assert team_id("Oakland Raiders", NFL) == team_id("Las Vegas Raiders", NFL) == "13"
    assert registry(NFL).by_espn_id("2").current_name() == "Buffalo Bills"
    assert team_id("2") == team_id("Auburn Tigers")


def _nfl_reason(team: str, season: int) -> str | None:
    change = departure(team, season, NFL)
    return change.reason if change is not None else None


def test_nfl_departures() -> None:
    # Saban to Alabama, Petrino to Arkansas mid-season, Dungy retired.
    assert _nfl_reason("Miami Dolphins", 2007) == LEFT_FOR_JOB
    assert _nfl_reason("Atlanta Falcons", 2008) == LEFT_FOR_JOB
    assert _nfl_reason("Indianapolis Colts", 2009) == RETIRED
    # Gruden resigned in October 2021; the coach who opened 2021 is gone.
    assert _nfl_reason("Las Vegas Raiders", 2022) == RESIGNED
    assert _nfl_reason("Kansas City Chiefs", 2020) is None


def test_a_medical_leave_is_not_a_departure() -> None:
    # Pagano missed most of 2012 and opened 2013.
    assert _nfl_reason("Indianapolis Colts", 2013) is None


def test_an_nfl_staff_names_the_coach_replaced_in_season_second() -> None:
    row = staff("Washington Commanders", 2019, NFL)
    assert row is not None
    assert row.head_coach == "Jay Gruden / Bill Callahan"
    assert row.hc_year is None


def _opener(team: str, season: int) -> str | None:
    row = week_one_starter(team, season, NFL)
    return row.player_key if row is not None else None


def test_nfl_quarterbacks() -> None:
    assert _opener("Tampa Bay Buccaneers", 2020) == "brady t"
    # Mariota opened 2019; Tannehill started the rest, playoffs included.
    assert _opener("Tennessee Titans", 2019) == "mariota m"
    assert quarterbacks("Tennessee Titans", 2019, NFL)[0].player_key == "tannehill r"
