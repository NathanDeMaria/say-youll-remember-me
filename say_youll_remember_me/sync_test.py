"""Placing Wikipedia's names for schools on the registry's teams. No network."""

from call_it_what_you_want import NCAA, default_teams

from .sync import current_name, resolve


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
