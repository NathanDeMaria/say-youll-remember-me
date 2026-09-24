"""The bundled files, read into typed rows, and the questions a model asks of them.

Each kind of record is one CSV per league under `data/<league>/`, one row per
observation, keyed by the team's canonical ESPN id with its current name
beside it for whoever reads the file. Blank cells are None; booleans are
`true` / `false`.

Teams are named in questions the way a caller has them -- any name
call-it-what-you-want knows, or an ESPN id -- and resolved to the id the rows
are keyed by, so a school that renamed itself is one team here as it is
there.
"""

import csv
import io
from collections.abc import Callable, Iterable
from functools import cache
from importlib.resources import files
from typing import Any, NamedTuple

from call_it_what_you_want import NCAA, UnknownTeamError, default_teams

from .types import (
    NCAAFB,
    REASONS,
    TABLES,
    CoachChange,
    CoachingStaff,
    QuarterbackSeason,
)

_PACKAGE = "say_youll_remember_me"
_DATA_DIR = "data"

HEAD_COACH_CHANGES = "head_coach_changes"
COACHING_STAFFS = "coaching_staffs"
QUARTERBACKS = "quarterbacks"

_TYPES: dict[str, type[NamedTuple]] = {
    HEAD_COACH_CHANGES: CoachChange,
    COACHING_STAFFS: CoachingStaff,
    QUARTERBACKS: QuarterbackSeason,
}


def _optional(read: Callable[[str], Any]) -> Callable[[str], Any]:
    return lambda cell: read(cell) if cell.strip() else None


def _boolean(cell: str) -> bool:
    if cell not in ("true", "false"):
        raise ValueError(f"expected true or false, got {cell!r}")
    return cell == "true"


def _one_of(choices: tuple[str, ...]) -> Callable[[str], str]:
    def read(cell: str) -> str:
        if cell not in choices:
            raise ValueError(f"expected one of {', '.join(choices)}, got {cell!r}")
        return cell

    return read


# How each column reads. Anything not named here is a required string.
_READERS: dict[str, Callable[[str], Any]] = {
    "season": int,
    "table": _one_of(TABLES),
    "midseason": _boolean,
    "date": _optional(str),
    "outgoing_interim": _boolean,
    "reason": _one_of(REASONS),
    "incoming": _optional(str),
    "incoming_interim": _boolean,
    "head_coach": _optional(str),
    "hc_year": _optional(int),
    "offensive_coordinator": _optional(str),
    "oc_year": _optional(int),
    "defensive_coordinator": _optional(str),
    "dc_year": _optional(int),
    "starts": int,
    "started_week_one": _boolean,
    "attempts": _optional(int),
    "epa": _optional(float),
}


def rows_from_csv(kind: str, lines: Iterable[str]) -> tuple[Any, ...]:
    """Parse one kind of record from CSV text. The header must name every field."""
    row_type = _TYPES[kind]
    reader = csv.DictReader(lines)
    fields = tuple(reader.fieldnames or ())
    if set(fields) != set(row_type._fields):
        missing = sorted(set(row_type._fields) - set(fields))
        unknown = sorted(set(fields) - set(row_type._fields))
        raise ValueError(
            f"{kind}: expected columns {', '.join(row_type._fields)}; "
            f"missing {missing or 'none'}, unexpected {unknown or 'none'}."
        )
    rows = []
    for number, row in enumerate(reader, start=2):  # row 1 is the header
        try:
            rows.append(
                row_type(
                    **{
                        field: _READERS.get(field, str)(row[field])
                        for field in row_type._fields
                    }
                )
            )
        except ValueError as error:
            raise ValueError(f"{kind} row {number}: {error}") from None
    return tuple(rows)


def to_csv(kind: str, rows: Iterable[NamedTuple]) -> str:
    """Write rows back out in the bundled files' format."""
    fields = _TYPES[kind]._fields
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(fields)
    for row in rows:
        writer.writerow(_cell(value) for value in row)
    return out.getvalue()


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def bundled_text(kind: str, league: str = NCAAFB) -> str:
    return (
        files(_PACKAGE)
        .joinpath(_DATA_DIR, league, f"{kind}.csv")
        .read_text(encoding="utf-8")
    )


@cache
def head_coach_changes(league: str = NCAAFB) -> tuple[CoachChange, ...]:
    """Every head-coaching change on file for `league`."""
    return rows_from_csv(
        HEAD_COACH_CHANGES, bundled_text(HEAD_COACH_CHANGES, league).splitlines()
    )


@cache
def coaching_staffs(league: str = NCAAFB) -> tuple[CoachingStaff, ...]:
    """Every team-season's head coach and coordinators on file for `league`."""
    return rows_from_csv(
        COACHING_STAFFS, bundled_text(COACHING_STAFFS, league).splitlines()
    )


@cache
def quarterback_seasons(league: str = NCAAFB) -> tuple[QuarterbackSeason, ...]:
    """Every quarterback-team-season on file for `league`."""
    return rows_from_csv(QUARTERBACKS, bundled_text(QUARTERBACKS, league).splitlines())


def team_id(team: str) -> str:
    """The canonical ESPN id for `team`: any name it has gone by, or any of its ids.

    Raises call-it-what-you-want's `UnknownTeamError` or `AmbiguousTeamError`
    for a name it can't place on exactly one team.
    """
    teams = default_teams(NCAA)
    try:
        return teams.by_espn_id(team).espn_id
    except UnknownTeamError:
        return teams.by_name(team).espn_id


def departure(team: str, season: int, league: str = NCAAFB) -> CoachChange | None:
    """Why the head coach who opened `season - 1` isn't opening `season`.

    None if he is. Otherwise the change that ended his tenure: after that
    season, before this one, or during that season (a mid-season firing,
    whose interim may or may not have kept the job -- either way the coach
    who opened it is gone). Rows where the coach leaving was an interim are
    skipped, since the question is about the coach who opened the season.
    If more than one qualifies, the earliest.
    """
    espn_id = team_id(team)
    candidates = [
        change
        for change in head_coach_changes(league)
        if change.espn_id == espn_id
        and not change.outgoing_interim
        and (
            (change.season == season and not change.midseason)
            or (change.season == season - 1 and change.midseason)
        )
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda c: c.date or "9999")


def staff(team: str, season: int, league: str = NCAAFB) -> CoachingStaff | None:
    """Who ran `team` in `season`, or None if the file has no row for it."""
    espn_id = team_id(team)
    for row in coaching_staffs(league):
        if row.espn_id == espn_id and row.season == season:
            return row
    return None


def quarterbacks(
    team: str, season: int, league: str = NCAAFB
) -> tuple[QuarterbackSeason, ...]:
    """`team`'s quarterbacks in `season`, most starts first."""
    espn_id = team_id(team)
    found = [
        row
        for row in quarterback_seasons(league)
        if row.espn_id == espn_id and row.season == season
    ]
    return tuple(sorted(found, key=lambda r: (-r.starts, -(r.attempts or 0))))


def week_one_starter(
    team: str, season: int, league: str = NCAAFB
) -> QuarterbackSeason | None:
    """Who started `team`'s first game of `season`, if the plays say."""
    for row in quarterbacks(team, season, league):
        if row.started_week_one:
            return row
    return None


def passer_seasons(
    player_key: str, season: int, league: str = NCAAFB
) -> tuple[QuarterbackSeason, ...]:
    """Every team a quarterback with this key threw for in `season`.

    More than one for a mid-season transfer or, more often, two
    quarterbacks who share a surname and initial -- which is why this
    hands back rows rather than one number.
    """
    return tuple(
        row
        for row in quarterback_seasons(league)
        if row.player_key == player_key and row.season == season
    )
