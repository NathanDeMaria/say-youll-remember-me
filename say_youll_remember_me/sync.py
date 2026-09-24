"""Rebuilding the bundled files from their sources.

    syrm coaches --first 2013 --last 2025   # head-coach changes, season articles
    syrm staffs --first 2014 --last 2026    # coaches and coordinators, infoboxes

Run from a checkout: the files are written into the package's `data/`
directory, to be reviewed and committed like any other change. `--cache`
keeps the fetched wikitext, so a rerun that only changes the parsing costs
no requests.

The quarterback file is not rebuilt here. It is read out of ESPN
play-by-play priced by an expected points model, which lives with the
models; see the README for how it was built.

Not imported by the package, like `wikipedia`.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

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
from .data import COACHING_STAFFS, HEAD_COACH_CHANGES, to_csv
from .types import NCAAFB, CoachChange, CoachingStaff

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


def resolve(name: str) -> str | None:
    """The canonical ESPN id for a school as Wikipedia names it, or None."""
    teams = default_teams(NCAA)
    for candidate in (name, _FROM_WIKIPEDIA.get(name)):
        if candidate is None:
            continue
        try:
            return teams.by_name(candidate).espn_id
        except (UnknownTeamError, AmbiguousTeamError):
            continue
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


def current_name(espn_id: str) -> str:
    """The team's name now, in football where it has one, for a reader of the file."""
    team = default_teams(NCAA).by_espn_id(espn_id)
    for league in (NCAAFB, None):
        try:
            return team.current_name(league=league)
        except (NoNamesError, AmbiguousNameError):
            continue
    return espn_id


def coaches(
    first: int, last: int, cache: Path | None
) -> tuple[list[CoachChange], list[str]]:
    """Head-coach changes from the season articles for `first` through `last`."""
    rows: list[CoachChange] = []
    unplaced: list[str] = []
    for season in range(first, last + 1):
        title = wikipedia.season_article(season)
        article = wikipedia.fetch_article(title, cache)
        if article is None:
            unplaced.append(f"no article: {title}")
            continue
        for change in wikipedia.coaching_changes(article, season):
            espn_id = resolve(change.team)
            if espn_id is None:
                unplaced.append(f"{season}: {change.team}")
                continue
            fields = change._asdict()
            del fields["team"]
            rows.append(
                CoachChange(
                    espn_id=espn_id, team=current_name(espn_id), source=title, **fields
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


def staffs(
    first: int, last: int, cache: Path | None
) -> tuple[list[CoachingStaff], list[str]]:
    """Every FBS team-season's head coach and coordinators, `first` through `last`."""
    wanted: dict[str, tuple[str, int]] = {}
    for season in range(first, last + 1):
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
        found = wikipedia.staff(lead)
        rows.append(
            CoachingStaff(
                espn_id=espn_id,
                team=current_name(espn_id),
                season=season,
                source=title,
                **found._asdict(),
            )
        )
    rows.sort(key=lambda r: (r.season, r.team))
    return rows, missing


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="syrm", description=__doc__.split("\n\n")[0])
    parser.add_argument("what", choices=["coaches", "staffs"])
    parser.add_argument("--first", type=int, required=True)
    parser.add_argument("--last", type=int, required=True)
    parser.add_argument("--cache", type=Path, help="keep fetched wikitext here")
    parser.add_argument("--output", type=Path, help="write here instead of data/")
    args = parser.parse_args(argv)

    if args.what == "coaches":
        rows, problems = coaches(args.first, args.last, args.cache)
        kind = HEAD_COACH_CHANGES
    else:
        rows, problems = staffs(args.first, args.last, args.cache)
        kind = COACHING_STAFFS
    output = args.output or DATA / NCAAFB / f"{kind}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(to_csv(kind, rows), encoding="utf-8")
    print(f"wrote {len(rows)} rows to {output}")
    if problems:
        print(f"{len(problems)} not placed:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)


if __name__ == "__main__":
    main()
