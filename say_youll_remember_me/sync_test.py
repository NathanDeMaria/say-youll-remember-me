"""Placing Wikipedia's names for schools on the registry's teams. No network."""

from call_it_what_you_want import NCAA, default_teams

from .sync import current_name, nfl_teams, resolve
from .types import NFL


def _id(name: str) -> str:
    return default_teams(NCAA).by_name(name).espn_id


def test_a_name_both_agree_on() -> None:
    assert resolve("Rutgers Scarlet Knights") == _id("Rutgers Scarlet Knights")


def test_a_name_only_wikipedia_uses() -> None:
    assert resolve("FIU Panthers") == _id("Florida International Panthers")
    assert resolve("Louisiana–Monroe Warhawks") == _id("UL Monroe Warhawks")


def test_a_school_linked_without_its_team_name() -> None:
    assert resolve("Colorado State") == _id("Colorado State Rams")


def test_a_school_nobody_knows() -> None:
    assert resolve("Hogwarts Hippogriffs") is None


def test_a_team_with_no_football_name_is_still_named() -> None:
    # A program new to football, known so far only by its basketball teams.
    assert current_name("2130") == "Chicago State Cougars"


def test_a_rebuild_replaces_only_the_seasons_it_read() -> None:
    from .data import COACHING_STAFFS, HEAD_COACH_CHANGES, coaching_staffs
    from .data import head_coach_changes as changes
    from .sync import _replaced

    staff_2019 = next(r for r in coaching_staffs() if r.season == 2019)
    assert _replaced(COACHING_STAFFS, staff_2019, 2019, 2019)
    assert not _replaced(COACHING_STAFFS, staff_2019, 2020, 2026)
    # A coaching change is replaced by re-reading the article it came from,
    # whichever season it lands in: the 2019 article's December hires are 2020's.
    december = next(
        r for r in changes() if r.source.startswith("2019 ") and r.season == 2020
    )
    assert _replaced(HEAD_COACH_CHANGES, december, 2019, 2019)
    assert not _replaced(HEAD_COACH_CHANGES, december, 2020, 2020)


def test_nfl_names_as_wikipedia_writes_them() -> None:
    assert resolve("Oakland Raiders", NFL) == "13"
    # ESPN called it plain "Washington" in 2020 and 2021.
    assert resolve("Washington Football Team", NFL) == "28"
    assert resolve("Hogwarts Hippogriffs", NFL) is None
    assert current_name("13", NFL) == "Las Vegas Raiders"


def test_the_nfl_before_and_after_the_texans() -> None:
    assert len(nfl_teams(2001)) == 31
    assert len(nfl_teams(2002)) == 32
