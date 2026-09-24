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

departure("Miami Dolphins", 2007, "nfl")
# CoachChange(outgoing='Nick Saban', reason='left_for_job', incoming='Cam Cameron', ...)
```

Every question takes a league, `ncaafb` unless given.

Teams are asked about by any name
[call-it-what-you-want](https://github.com/NathanDeMaria/call-it-what-you-want)
knows, or by ESPN id, and every row is keyed by the canonical ESPN id it
answers with -- so "Appalachian State Mountaineers" and "App State
Mountaineers" are one team here, as they are there, and so are the Oakland
and Las Vegas Raiders. The NFL numbers its teams from scratch, so its ids
are looked up in that package's `nfl` namespace. That package is the
only dependency; reading the data pulls in nothing else, and
`imports_test.py` keeps it that way.

The whole files are there too: `head_coach_changes()`, `coaching_staffs()`
and `quarterback_seasons()` return every row as a typed `NamedTuple`.

## The data

`say_youll_remember_me/data/<league>/<kind>.csv`, one row per observation:
college football (`ncaafb`), then the NFL (`nfl`, below). Blank cells are
None, booleans `true` / `false`. Snapshot of 2026-09-24: 2026 rows cover
the season to date.

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

### `quarterbacks.csv` -- 6,903 quarterback-team-seasons, 2013-2026

From ESPN play-by-play, by `syrm quarterbacks`: every quarterback who
started a game, plus any passer with 50+ attempts who didn't.

| column | |
|---|---|
| `player` | as the play text spells it -- "Joe Burrow" or "F.Mendoza" depending on the season's format |
| `player_key` | "last first-initial", what matches a quarterback across spellings and schools |
| `starts` | games he started: threw the team's early passes, not the most of them |
| `started_week_one` | started the team's first game with play-by-play |
| `attempts`, `epa` | his pass attempts and their summed expected points added |
| `source` | `espn-pbp/ep-<run>`: which expected points fit priced the plays |

"First game with play-by-play" is usually the opener. When ESPN has no
plays for the opener -- most often against a lower-division school -- it's
the first game it does have, the nearest thing to a preseason depth chart
the plays offer.

Starters are credited by the offense's team id, so a game counts whichever
side was home. Pricing a snap needs the home side, which is inferred from
the scoring plays; the few games where the scoring doesn't say (8 to 11 a
season) are counted for starts and left unpriced.

`epa` is `lucky_ones`' ncaafb model (expected points run 20260920-230959),
each play bounded at +/-3, the same call and bound as cassandra's EPA
index. None before 2014, which the expected points fit doesn't cover.
`passer_seasons(key, season)` finds a quarterback at every school he threw
for, which is how a transfer's record follows him.

`player_key` can collide: two quarterbacks sharing a surname and first
initial are one key. It's rare within a season and a team, less rare across
the country, so check the team before treating two rows as one player.

### The NFL

Same three files and columns, under `data/nfl/`.

**`head_coach_changes.csv` -- 195 changes, seasons 2006-2026.** The
head-coach tables of *20XX NFL season*, 2006-2026, which split the other
way from college: `table` is `offseason` (every change between the last
season and this one; `season` is the article's) or `in_season` (this
season's coaches who didn't finish it; `midseason`). A coach fired
mid-season usually appears twice, in that season's in-season table and
the next one's off-season table; `departure` answers with the earlier.
Reasons: `fired` 172, `retired` 9, `resigned` 8, `left_for_job` 4 (Herm
Edwards traded to Kansas City, Nick Saban to Alabama, Bobby Petrino to
Arkansas in both tables), `other` 2 (Sean Payton's 2012 suspension and
reinstatement). An NFL "contract expired" is a firing: a team that wanted
him would have extended it. A medical leave he came back from isn't a
change and isn't on file. Dates come from the notes, where they're given.

**`coaching_staffs.csv` -- 704 team-seasons, 2005-2026.** The *2019 Kansas
City Chiefs season* infobox, whose head coach field is `coach`. A coach
replaced during the season is joined with " / " after the one who opened
it ("Jay Gruden / Bill Callahan"). The NFL infobox numbers nobody's
seasons, so the `*_year` columns are empty, and it names coordinators for
only about half the team-seasons (345 offensive, 341 defensive). Agrees
with the change tables on who opened every season but two, both Payton's
suspension.

**`quarterbacks.csv` -- 1,212 quarterback-team-seasons, 2006-2026.** Built
the college way, from the NFL's plays: starts from 2006, `attempts` and
`epa` from 2014 by `lucky_ones`' NFL model (expected points run
20260920-231258). Playoff games count as starts. Two games since 2014 --
one in 2017, one in 2019 -- are counted for starts and left unpriced.

## Rebuilding

```bash
uv run syrm coaches --first 2013 --last 2025 --cache ~/.cache/syrm
uv run syrm staffs --first 2014 --last 2026 --cache ~/.cache/syrm
uv run syrm quarterbacks --first 2026 --last 2026
uv run syrm coaches --league nfl --first 2006 --last 2026 --cache ~/.cache/syrm
```

Writes into `data/`, to be reviewed and committed like any other change.
Only the seasons asked for are replaced and the rest of the file is kept,
so refreshing the season in progress is a one-season run. For `coaches`
the seasons are the articles read, since one article's changes land in two
seasons.

The coaching files come from Wikipedia. `--cache` keeps the fetched
wikitext, so a rerun that only changes the parsing costs no requests.
Requests go 20 titles at a time, 4 seconds apart, identified by this repo's
URL -- the Wikimedia API rate-limits a generic client within a few dozen.

The quarterback file comes from endgame's bucket -- the stored schedules
and the processed play store -- so it needs AWS credentials that can read
it, and the `plays` extra (`uv sync --extra plays`; Python 3.14, which
`lucky-ones` requires). The play-text parser is `say_youll_remember_me.qb`,
the one cassandra's quarterback-availability index uses too.

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
