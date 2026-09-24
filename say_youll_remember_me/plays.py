"""Building `quarterbacks.csv` from ESPN play-by-play.

Needs the `plays` extra, and AWS credentials that can read endgame's bucket,
where the processed play store lives.

For each season:

- every week's plays, grouped into games, with the home side inferred from
  the scoring plays by `lucky_ones.game.infer_home_team_id`;
- each team's starter in each game, by `qb.team_games` -- whoever threw the
  early passes;
- from `lucky_ones.points.FIRST_LEGIBLE_SEASON` on, every snap priced by
  `lucky_ones`' expected points model at the bound cassandra's EPA index
  uses, and each pass attempt credited to its passer;
- each team's first game *with play-by-play*, whose starter is the one
  marked `started_week_one`. Usually the opener. When ESPN has no plays for
  the opener -- most often against a lower-division school -- it is the
  first game it does have, which is the nearest thing to a preseason depth
  chart the plays can offer, and what the research the file was built for
  read it as.

Starters are read by offense team id, so a game counts even when which side
was home can't be told. Pricing a snap needs the home side, so a game whose
home side can't be inferred from its plays is left unpriced rather than
guessed at.

`season_quarterbacks` is the part that turns games into rows, and takes
everything it needs as arguments so it can be checked without a bucket.
`build` is the part that reads one.

Not imported by the package.
"""

import asyncio
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import NamedTuple

from call_it_what_you_want import NCAA, UnknownTeamError, default_teams
from endgame_aws import get_processed_plays_store
from lucky_ones import MODELS
from lucky_ones.arrow import StorePlaySource
from lucky_ones.epa import DEFAULT_CLIP, PlayEPA
from lucky_ones.game import GamePlays, infer_home_team_id
from lucky_ones.plays import Play
from lucky_ones.points import FIRST_LEGIBLE_SEASON

from .qb import name_key, passer, team_games
from .sync import current_name
from .types import NCAAFB, QuarterbackSeason

# Source week numbers to ask the play store for. The store is keyed by the
# feed's own numbering, which need not match the schedule's calendar weeks;
# asking for every plausible number and dropping a game seen twice sidesteps
# the question. A week that isn't there comes back empty.
MAX_WEEK = 30
# How many weeks of plays to read at once.
CONCURRENT_WEEKS = 8
# A passer who never started is kept only with a real sample behind him.
MIN_ATTEMPTS = 50

Pricer = Callable[[GamePlays], Sequence[PlayEPA]]


class Game(NamedTuple):
    """One game's plays, and whether its home side is known well enough to price."""

    game_id: str
    home_team_id: str
    away_team_id: str
    plays: Sequence[Play]
    priced: bool

    def as_game_plays(self, season: int) -> GamePlays:
        return GamePlays(
            game_id=self.game_id,
            league=NCAAFB,
            season=season,
            week=0,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            plays=self.plays,
        )


@dataclass
class _Tally:
    starts: int = 0
    started_week_one: bool = False
    attempts: int = 0
    epa: float = 0.0
    names: Counter[str] = field(default_factory=Counter)


def season_quarterbacks(
    season: int,
    games: Sequence[Game],
    canonical: Callable[[str], str | None],
    price: Pricer | None,
    source: str,
) -> tuple[list[QuarterbackSeason], set[str]]:
    """One season's quarterback rows, and the play team ids nobody could place.

    `games` in the order they were played. `canonical` turns a play's team
    id into the id rows are keyed by, or None for one the registry doesn't
    know. `price` is the expected points model, None for a season it doesn't
    cover -- whose rows then carry no attempts or EPA, rather than a zero
    that reads as a quarterback who never threw.
    """
    tallies: dict[tuple[str, str], _Tally] = {}
    unplaced: set[str] = set()
    opened: set[str] = set()
    for game in games:
        ids = {
            game.home_team_id: canonical(game.home_team_id),
            game.away_team_id: canonical(game.away_team_id),
        }
        unplaced |= {raw for raw, placed in ids.items() if placed is None}
        plays = game.plays

        started = team_games(
            [p.game_id for p in plays],
            [p.offense_team_id for p in plays],
            [p.text for p in plays],
        )
        for (_, raw_team), qb in started.items():
            team = ids.get(raw_team)
            if team is None:
                continue
            tally = tallies.setdefault((team, qb.starter_key), _Tally())
            tally.starts += 1
            tally.names[qb.starter] += 1
            if team not in opened:
                opened.add(team)
                tally.started_week_one = True

        if price is None or not game.priced:
            continue
        texts = {p.play_id: p.text for p in plays}
        for priced in price(game.as_game_plays(season)):
            thrower = passer(texts.get(priced.play_id))
            if thrower is None:
                continue
            side = game.home_team_id if priced.offense_is_home else game.away_team_id
            team = ids.get(side)
            if team is None:
                continue
            tally = tallies.setdefault((team, name_key(thrower)), _Tally())
            tally.attempts += 1
            tally.epa += priced.bounded
            tally.names[thrower] += 1

    rows = [
        QuarterbackSeason(
            espn_id=team,
            team=current_name(team),
            season=season,
            player=tally.names.most_common(1)[0][0],
            player_key=key,
            starts=tally.starts,
            started_week_one=tally.started_week_one,
            attempts=tally.attempts if price is not None else None,
            epa=round(tally.epa, 4) if price is not None else None,
            source=source,
        )
        for (team, key), tally in tallies.items()
        if tally.starts > 0 or tally.attempts >= MIN_ATTEMPTS
    ]
    rows.sort(key=lambda r: (r.team, -r.starts, -(r.attempts or 0), r.player_key))
    return rows, unplaced


def canonical_id(team_id: str) -> str | None:
    try:
        return default_teams(NCAA).by_espn_id(team_id).espn_id
    except UnknownTeamError:
        return None


async def _season_games(source: StorePlaySource, season: int) -> list[Game]:
    """Every game of `season` with plays, in the order they were played."""
    limit = asyncio.Semaphore(CONCURRENT_WEEKS)

    async def week(number: int) -> Sequence[Play]:
        async with limit:
            return await source.load_week(NCAAFB, season, number)

    weeks = await asyncio.gather(*(week(n) for n in range(1, MAX_WEEK + 1)))
    by_game: dict[str, list[Play]] = {}
    order: dict[str, tuple] = {}
    for number, plays in enumerate(weeks, start=1):
        for play in plays:
            if play.game_id not in by_game:
                by_game[play.game_id] = []
                order[play.game_id] = (number, play.wallclock is None, play.wallclock)
            by_game[play.game_id].append(play)

    games = []
    for game_id, plays in by_game.items():
        teams = sorted({p.offense_team_id for p in plays if p.offense_team_id})
        if len(teams) != 2:
            continue
        home = infer_home_team_id(plays)
        games.append(
            Game(
                game_id=game_id,
                home_team_id=home or teams[0],
                away_team_id=teams[1] if home in (None, teams[0]) else teams[0],
                plays=plays,
                priced=home is not None,
            )
        )
    games.sort(
        key=lambda g: (
            order[g.game_id][0],
            order[g.game_id][1],
            order[g.game_id][2] or 0,
            g.game_id,
        )
    )
    return games


async def build(first: int, last: int) -> tuple[list[QuarterbackSeason], list[str]]:
    """Quarterback rows for `first` through `last`, and what couldn't be placed."""
    source = StorePlaySource(get_processed_plays_store())
    model = MODELS[NCAAFB]
    run = model.expected_points_release.run_id

    def price(game: GamePlays) -> Sequence[PlayEPA]:
        return model.epa_per_play(game, clip=DEFAULT_CLIP).plays

    rows: list[QuarterbackSeason] = []
    problems: list[str] = []
    for season in range(first, last + 1):
        priced = season >= FIRST_LEGIBLE_SEASON
        games = await _season_games(source, season)
        unpriced = sum(not g.priced for g in games)
        if priced and unpriced:
            problems.append(
                f"{season}: {unpriced} games left unpriced, home side unknown"
            )
        found, unplaced = season_quarterbacks(
            season,
            games,
            canonical_id,
            price if priced else None,
            f"espn-pbp/ep-{run}" if priced else "espn-pbp",
        )
        rows += found
        problems += [f"{season}: play team id {raw}" for raw in sorted(unplaced)]
        print(f"{season}: {len(found)} quarterback-seasons", flush=True)
    return rows, problems
