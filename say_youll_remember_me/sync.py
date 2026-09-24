"""Rebuilding the bundled files from their sources.

    syrm coaches --first 2013 --last 2025      # season articles
    syrm staffs --first 2014 --last 2026       # team-season infoboxes
    syrm quarterbacks --first 2013 --last 2026 # play-by-play; the `plays` extra
    syrm coaches --league nfl --first 2006 --last 2026

`--league` is `ncaafb` unless given. College files cover FBS team-seasons;
NFL files cover every franchise ESPN listed that season.

Run from a checkout: the files are written into the package's `data/`
directory, to be reviewed and committed like any other change. Only the
seasons asked for are replaced -- the rest of the file is kept -- so
refreshing the season in progress is `--first 2026 --last 2026`. For
coaches the seasons are the articles read, since one article's changes
land in two seasons. `--cache` keeps the fetched wikitext, so a rerun that
only changes the parsing costs no requests.

Not imported by the package, like `wikipedia` and `plays`.
"""

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from call_it_what_you_want import (
    NCAA,
    AmbiguousNameError,
    AmbiguousTeamError,
    NoNamesError,
    Teams,
    UnknownTeamError,
    default_classifications,
    default_teams,
)

from . import wikipedia
from .data import (
    COACHING_STAFFS,
    HEAD_COACH_CHANGES,
    QUARTERBACKS,
    registry,
    rows_from_csv,
    to_csv,
)
from .types import LEAGUES, NCAAFB, NFL, CoachChange, CoachingStaff

DATA = Path(__file__).parent / "data"

# Where call-it-what-you-want and Wikipedia name a school differently, by the
# former's current name. Used both ways: to build a team-season article's
# title, and to place a name read off a season article.
WIKIPEDIA_NAMES = {
    "Hawai'i Rainbow Warriors": "Hawaii Rainbow Warriors",
    "Miami (OH) RedHawks": "Miami RedHawks",
    "Massachusetts Minutemen": "UMass Minutemen",
    "Florida International Panthers": "FIU Panthers",
    "San José State Spartans": "San Jose State Spartans",
    "UL Monroe Warhawks": "Louisiana–Monroe Warhawks",
    "App State Mountaineers": "Appalachian State Mountaineers",
    "Delaware Blue Hens": "Delaware Fightin' Blue Hens",
}
_FROM_WIKIPEDIA = {wiki: ours for ours, wiki in WIKIPEDIA_NAMES.items()}

# The NFL's differ in one place: ESPN called Washington just "Washington"
# from 2019 through 2021, and Wikipedia titles those seasons by the name
# the team played under. Keyed by ESPN's name and the season.
NFL_WIKIPEDIA_NAMES = {
    ("Washington", 2019): "Washington Redskins",
    ("Washington", 2020): "Washington Football Team",
    ("Washington", 2021): "Washington Football Team",
}
_FROM_NFL_WIKIPEDIA = {wiki: ours for (ours, _), wiki in NFL_WIKIPEDIA_NAMES.items()}


def resolve(name: str, league: str = NCAAFB) -> str | None:
    """The canonical ESPN id for a team as Wikipedia names it, or None."""
    teams = registry(league)
    aliases = _FROM_NFL_WIKIPEDIA if league == NFL else _FROM_WIKIPEDIA
    for candidate in (name, aliases.get(name)):
        if candidate is None:
            continue
        try:
            return teams.by_name(candidate).espn_id
        except (UnknownTeamError, AmbiguousTeamError):
            continue
    if league == NFL:
        return None
    # A cell that links the school rather than its team -- "Colorado State"
    # -- is placed when exactly one football program's name starts with it.
    prefixed = [
        team.espn_id
        for team in teams
        if _football_name(team.espn_id, teams).startswith(name + " ")
    ]
    return prefixed[0] if len(prefixed) == 1 else None


def _football_name(espn_id: str, teams: Teams) -> str:
    try:
        return teams.by_espn_id(espn_id).current_name(league=NCAAFB)
    except (NoNamesError, AmbiguousNameError):
        return ""


def current_name(espn_id: str, league: str = NCAAFB) -> str:
    """The team's name now, in football where it has one, for a reader of the file."""
    if league == NFL:
        return registry(NFL).by_espn_id(espn_id).current_name()
    team = default_teams(NCAA).by_espn_id(espn_id)
    for context in (NCAAFB, None):
        try:
            return team.current_name(league=context)
        except (NoNamesError, AmbiguousNameError):
            continue
    return espn_id


def coaches(
    first: int, last: int, cache: Path | None, league: str = NCAAFB
) -> tuple[list[CoachChange], list[str]]:
    """Head-coach changes from the season articles for `first` through `last`."""
    rows: list[CoachChange] = []
    unplaced: list[str] = []
    for season in range(first, last + 1):
        title = wikipedia.season_article(season, league)
        article = wikipedia.fetch_article(title, cache)
        if article is None:
            unplaced.append(f"no article: {title}")
            continue
        for change in wikipedia.coaching_changes(article, season, league):
            espn_id = resolve(change.team, league)
            if espn_id is None:
                unplaced.append(f"{season}: {change.team}")
                continue
            fields = change._asdict()
            del fields["team"]
            rows.append(
                CoachChange(
                    espn_id=espn_id,
                    team=current_name(espn_id, league),
                    source=title,
                    **fields,
                )
            )
    rows.sort(key=lambda r: (r.season, r.date or "9999", r.team))
    return rows, unplaced


def fbs_teams(season: int) -> list[str]:
    """ESPN ids of the teams call-it-what-you-want files as FBS in `season`."""
    teams = default_teams(NCAA)
    classifications = default_classifications(NCAA)
    found = []
    for team in teams:
        placed = classifications.classification_in(team.espn_id, season, NCAAFB)
        if placed is not None and placed.division == "FBS":
            found.append(team.espn_id)
    return found


def nfl_teams(season: int) -> list[str]:
    """ESPN ids of the NFL franchises call-it-what-you-want lists in `season`."""
    return [
        team.espn_id
        for team in registry(NFL)
        if any(name.year == season for name in team.names)
    ]


def staffs(
    first: int, last: int, cache: Path | None, league: str = NCAAFB
) -> tuple[list[CoachingStaff], list[str]]:
    """Every team-season's head coach and coordinators, `first` through `last`.

    College is FBS only. An NFL team-season article is titled by the name
    the team played under that season, so it's looked up by season.
    """
    wanted: dict[str, tuple[str, int]] = {}
    for season in range(first, last + 1):
        if league == NFL:
            for espn_id in nfl_teams(season):
                name = registry(NFL).by_espn_id(espn_id).name_in(season)
                name = NFL_WIKIPEDIA_NAMES.get((name, season), name)
                wanted[wikipedia.team_season_article(name, season, NFL)] = (
                    espn_id,
                    season,
                )
            continue
        for espn_id in fbs_teams(season):
            name = current_name(espn_id)
            title = wikipedia.team_season_article(
                WIKIPEDIA_NAMES.get(name, name), season
            )
            wanted[title] = (espn_id, season)
    leads = wikipedia.fetch_leads(list(wanted), cache)
    rows: list[CoachingStaff] = []
    missing: list[str] = []
    for title, (espn_id, season) in wanted.items():
        lead = leads.get(title)
        if not lead:
            missing.append(title)
            continue
        found = wikipedia.staff(lead, league)
        rows.append(
            CoachingStaff(
                espn_id=espn_id,
                team=current_name(espn_id, league),
                season=season,
                source=title,
                **found._asdict(),
            )
        )
    rows.sort(key=lambda r: (r.season, r.team))
    return rows, missing


def _replaced(kind: str, row: Any, first: int, last: int, league: str = NCAAFB) -> bool:
    """Whether a rebuild of `first` through `last` replaces this existing row."""
    if kind == HEAD_COACH_CHANGES:
        read = {wikipedia.season_article(s, league) for s in range(first, last + 1)}
        return row.source in read
    return first <= row.season <= last


_ORDER: dict[str, Callable[[Any], tuple]] = {
    HEAD_COACH_CHANGES: lambda r: (r.season, r.date or "9999", r.team),
    COACHING_STAFFS: lambda r: (r.season, r.team),
    QUARTERBACKS: lambda r: (r.season, r.team, -r.starts, -(r.attempts or 0)),
}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="syrm", description=__doc__.split("\n\n")[0])
    parser.add_argument("what", choices=["coaches", "staffs", "quarterbacks"])
    parser.add_argument("--league", choices=LEAGUES, default=NCAAFB)
    parser.add_argument("--first", type=int, required=True)
    parser.add_argument("--last", type=int, required=True)
    parser.add_argument("--cache", type=Path, help="keep fetched wikitext here")
    parser.add_argument("--output", type=Path, help="write here instead of data/")
    args = parser.parse_args(argv)

    rows: Sequence[Any]
    if args.what == "coaches":
        rows, problems = coaches(args.first, args.last, args.cache, args.league)
        kind = HEAD_COACH_CHANGES
    elif args.what == "staffs":
        rows, problems = staffs(args.first, args.last, args.cache, args.league)
        kind = COACHING_STAFFS
    else:
        # Only here: it needs the `plays` extra, which the other two don't.
        from .plays import build

        rows, problems = asyncio.run(build(args.first, args.last, args.league))
        kind = QUARTERBACKS

    output = args.output or DATA / args.league / f"{kind}.csv"
    kept: list[Any] = []
    if output.exists():
        existing = rows_from_csv(kind, output.read_text(encoding="utf-8").splitlines())
        kept = [
            r
            for r in existing
            if not _replaced(kind, r, args.first, args.last, args.league)
        ]
    merged = sorted([*kept, *rows], key=_ORDER[kind])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(to_csv(kind, merged), encoding="utf-8")
    print(f"wrote {len(rows)} rebuilt rows and kept {len(kept)} to {output}")
    if problems:
        print(f"{len(problems)} not placed:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)


if __name__ == "__main__":
    main()
