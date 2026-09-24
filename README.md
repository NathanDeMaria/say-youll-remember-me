# say-youll-remember-me

What changed about a team between seasons: who its head coach is and why
the last one left, who its coordinators are, and who plays quarterback --
the offseason facts a rating model can't see in last season's scores.

## Usage

```python
from say_youll_remember_me import departure, quarterbacks, staff, week_one_starter

departure("Indiana Hoosiers", 2024)
# CoachChange(outgoing='Tom Allen', reason='fired', incoming='Curt Cignetti', ...)
departure("Georgia Bulldogs", 2024)  # None: the coach who opened 2023 opened 2024

staff("Michigan Wolverines", 2021)
# CoachingStaff(head_coach='Jim Harbaugh', hc_year=7, ...,
#               defensive_coordinator='Mike Macdonald', dc_year=1, ...)

week_one_starter("LSU Tigers", 2019)
# QuarterbackSeason(player='Joe Burrow', starts=15, attempts=518, epa=261.1584, ...)
```

Teams are asked about by any name
[call-it-what-you-want](https://github.com/NathanDeMaria/call-it-what-you-want)
knows, or by ESPN id, and every row is keyed by the canonical ESPN id it
answers with -- so "Appalachian State Mountaineers" and "App State
Mountaineers" are one team here, as they are there. That package is the
only dependency; reading the data pulls in nothing else, and
`imports_test.py` keeps it that way.

The whole files are there too: `head_coach_changes()`, `coaching_staffs()`
and `quarterback_seasons()` return every row as a typed `NamedTuple`.

## The data

`say_youll_remember_me/data/<league>/<kind>.csv`, one row per observation.
Only college football (`ncaafb`) so far. Blank cells are None, booleans
`true` / `false`. Snapshot of 2026-09-24: 2026 rows cover the season to
date.

### `head_coach_changes.csv` -- 468 changes, seasons 2013-2026

Every row of the "Coaching changes" tables in Wikipedia's *20XX NCAA
Division I FBS football season* articles, 2013-2025.

| column | |
|---|---|
| `season` | the season the change first matters for |
| `midseason` | the coach didn't finish the regular season (gone by November 20) |
| `table` | `in_season` (preseason, in-season and December changes) or `end_of_season` |
| `date` | ISO |
| `outgoing`, `incoming` | names; `*_interim` flags an interim on either side |
| `reason` | `fired` 182, `left_for_job` 82, `resigned` 32, `retired` 19, `health` 3, `other` 4, and `interim_replaced` 146 |
| `reason_text` | what the article said, kept so a category can be revisited |

A mid-season firing's `season` is the one it happened in; anything after
the regular season -- late-November firings, December hires, the whole
end-of-season table -- is the next one, even when an interim coaches the
bowl game.

The reason categories are read off the article's words, and two rules
aren't obvious:

- **A coach whose next job was an assistant's was fired.** The article
  often says where he landed instead of why he left -- "Hired as defensive
  coordinator by Penn State" is Tom Allen, fired by Indiana -- and read
  literally that's a coach leaving for a job.
- **"Agreed to part ways" is a firing.**

The four `other` rows are head coaches who took position-coach jobs, which
could be either; `reason_text` says which.

To ask why the coach who opened a season is gone, use `departure`: it
skips rows where the coach leaving was an interim.

### `coaching_staffs.csv` -- 1,704 team-seasons, 2014-2026

The infobox of every FBS team-season article (*2019 LSU Tigers football
team*): `head_coach`, `offensive_coordinator`, `defensive_coordinator`, and
each one's season at the school (`hc_year`, `oc_year`, `dc_year`; 1 is a
first-year coordinator). Co-coordinators are joined with " / ". Which teams
are FBS in a season is call-it-what-you-want's classification.

Coverage: head coach 1,697, offensive coordinator's year 1,429, defensive
coordinator's year 1,545. Missing: UAB 2015-16, when the program was shut
down.

### `quarterbacks.csv` -- 7,720 quarterback-team-seasons, 2013-2026

From ESPN play-by-play: every quarterback who started a game, plus any
passer with 50+ attempts who didn't.

| column | |
|---|---|
| `player` | as the play text spells it -- "Joe Burrow" or "F.Mendoza" depending on the season's format |
| `player_key` | "last first-initial", what matches a quarterback across spellings and schools |
| `starts` | games he started: threw the team's early passes, not the most of them |
| `started_week_one` | started the team's first game |
| `attempts`, `epa` | his pass attempts and their summed expected points added |
| `source` | `espn-pbp/ep-<run>`: which expected points fit priced the plays |

`epa` is `lucky_ones`' ncaafb model (expected points run 20260920-230959),
each play bounded at +/-3, the same call and bound as cassandra's EPA
index. None before 2014, which the expected points fit doesn't cover.
`passer_seasons(key, season)` finds a quarterback at every school he threw
for, which is how a transfer's record follows him.

`player_key` can collide: two quarterbacks sharing a surname and first
initial are one key. It's rare within a season and a team, less rare across
the country, so check the team before treating two rows as one player.

## Rebuilding

```bash
uv run syrm coaches --first 2013 --last 2025 --cache ~/.cache/syrm
uv run syrm staffs --first 2014 --last 2026 --cache ~/.cache/syrm
```

Writes into `data/`, to be reviewed and committed like any other change.
`--cache` keeps the fetched wikitext, so a rerun that only changes the
parsing costs no requests. Requests go 20 titles at a time, 4 seconds
apart, identified by this repo's URL -- the Wikimedia API rate-limits a
generic client within a few dozen.

The quarterback file isn't rebuilt here yet. It was built from
cassandra's play-text parser (`cassandra.qb`) and `lucky_ones`' expected
points model, reading the processed play store; moving that builder here,
with the parser cassandra's quarterback-availability index also uses, is
the next step.

## Sources

Coaching data is from [Wikipedia](https://en.wikipedia.org), under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); each row's
`source` names the article. Quarterback data is derived from ESPN
play-by-play.

## Development

```bash
uv sync
uv run pytest
uv run ruff format --check . && uv run ruff check . && uv run ty check .
```
