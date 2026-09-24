from typing import NamedTuple

# Leagues. Only college football is on file so far; the files live under a
# directory per league so another one is a new directory, not a new schema.
NCAAFB = "ncaafb"

# Why a head coach's tenure ended, as a category. The text it was read from
# is kept beside it (`CoachChange.reason_text`), because the line between
# "resigned" and "fired" is a judgement, and a category that turned out to be
# wrong should be fixable from the file rather than by scraping again.
FIRED = "fired"
LEFT_FOR_JOB = "left_for_job"
RESIGNED = "resigned"
RETIRED = "retired"
HEALTH = "health"
# An interim coach giving way to the permanent hire. Not a departure of the
# coach who opened the season -- that one is its own row -- so it is kept
# apart rather than folded into "other".
INTERIM_REPLACED = "interim_replaced"
OTHER = "other"
REASONS = (FIRED, LEFT_FOR_JOB, RESIGNED, RETIRED, HEALTH, INTERIM_REPLACED, OTHER)

# Which of a Wikipedia season article's two coaching tables a change came
# from. "In-season" also carries preseason changes and the December hires a
# school makes before its bowl game; "end of season" is changes announced
# during the season that take effect after it.
IN_SEASON = "in_season"
END_OF_SEASON = "end_of_season"
TABLES = (IN_SEASON, END_OF_SEASON)


class CoachChange(NamedTuple):
    """
    One head-coaching change: `outgoing` stopped being `team`'s head coach,
    for `reason`, and `incoming` took over.

    `season` is the season the change first matters for. A mid-season
    firing is that season -- the interim coaches the rest of it -- and a
    change after the regular season is the next one, even when an interim
    or the new hire coaches the bowl game in between.

    `midseason` is a coach who didn't finish the regular season: gone by
    November 20. `season` is then the one he didn't finish.
    `outgoing_interim` marks a row where the coach leaving was himself an
    interim, which is what `INTERIM_REPLACED` rows usually are. To ask why
    the coach who opened a season is gone, skip those -- or use
    `departure`, which does.

    `date` is ISO, or None where the article gave none. `source` is the
    article the row was read from.
    """

    espn_id: str
    team: str
    season: int
    table: str
    midseason: bool
    date: str | None
    outgoing: str
    outgoing_interim: bool
    reason: str
    reason_text: str
    incoming: str | None
    incoming_interim: bool
    source: str


class CoachingStaff(NamedTuple):
    """
    Who ran a team in one season, from the team-season article's infobox.

    The `*_year` fields are each coach's season at the school, as the
    article numbers them: 1 is a first-year coordinator. None where the
    infobox didn't say. A shared role (co-coordinators) is written with the
    names joined by " / ".
    """

    espn_id: str
    team: str
    season: int
    head_coach: str | None
    hc_year: int | None
    offensive_coordinator: str | None
    oc_year: int | None
    defensive_coordinator: str | None
    dc_year: int | None
    source: str


class QuarterbackSeason(NamedTuple):
    """
    One quarterback's season with one team, from ESPN play-by-play.

    `starts` counts the games he started -- threw the team's early passes,
    not the most of them. `started_week_one` is whether he started the
    team's first game. `attempts` and `epa` are every pass attempt credited
    to him and their summed expected points added, bounded per play the
    way the EPA index cassandra reads is; None before the expected points
    fit covers a season.

    `player_key` is the name reduced to "last first-initial", which is what
    matches one quarterback across the play text's three spellings of a
    name -- and across schools, for a transfer. It can collide for two
    quarterbacks with the same surname and initial.
    """

    espn_id: str
    team: str
    season: int
    player: str
    player_key: str
    starts: int
    started_week_one: bool
    attempts: int | None
    epa: float | None
    source: str

    @property
    def epa_per_attempt(self) -> float | None:
        if not self.attempts or self.epa is None:
            return None
        return self.epa / self.attempts
