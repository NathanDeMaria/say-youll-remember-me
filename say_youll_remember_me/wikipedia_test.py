"""Reading wikitext, on the shapes the college and NFL articles actually use."""

from .types import (
    END_OF_SEASON,
    FIRED,
    HEALTH,
    IN_SEASON,
    INTERIM_REPLACED,
    LEFT_FOR_JOB,
    NFL,
    OFFSEASON,
    OTHER,
    RESIGNED,
    RETIRED,
)
from .wikipedia import (
    coaching_changes,
    date_of,
    parse_table,
    plain,
    reason_of,
    staff,
    team_of,
)


def test_plain_reads_like_the_page() -> None:
    assert plain("{{sortname|Chris|Ash}}") == "Chris Ash"
    assert plain("{{sortname|Glenn|Spencer|dab=American football}} (bowl)") == (
        "Glenn Spencer (bowl)"
    )
    assert plain("[[Bob Davie (American football)|Bob Davie]]") == "Bob Davie"
    assert plain("[[Tom Allen (American football)]]") == "Tom Allen"
    assert plain("Fired<ref>{{cite web|url=x}}</ref>") == "Fired"
    assert plain("[[A B]]<br />[[C D]]") == "A B / C D"


def test_team_of_reads_the_link_not_the_label() -> None:
    assert team_of("[[Rutgers Scarlet Knights football|Rutgers]]") == (
        "Rutgers Scarlet Knights"
    )
    assert team_of("[[2019 Arkansas Razorbacks football team|Arkansas]]") == (
        "Arkansas Razorbacks"
    )
    assert team_of("no link") is None


def test_dates_in_every_spelling() -> None:
    assert date_of("{{dts|2016|12|1}}", 2016) == "2016-12-01"
    assert date_of("{{dts|September 29, 2019}}", 2019) == "2019-09-29"
    assert date_of("December 2, 2019", 2019) == "2019-12-02"
    assert date_of("rowspan=2| December 2", 2014) == "2014-12-02"
    # No year, in January: the offseason after the article's season.
    assert date_of("January 10", 2023) == "2024-01-10"
    assert date_of("", 2020) is None


def test_reasons() -> None:
    assert reason_of("Fired", False) == FIRED
    assert reason_of("Agreed to part ways", False) == FIRED
    assert reason_of("Will not return after the 2021 season", False) == FIRED
    # Where a fired coach landed, not why he left.
    assert (
        reason_of(
            "Hired As Defensive Coordinator/Linebackers Coach by Penn State", False
        )
        == FIRED
    )
    assert reason_of("Hired by Michigan State", False) == LEFT_FOR_JOB
    assert reason_of("Hired by Los Angeles Chargers", False) == LEFT_FOR_JOB
    assert reason_of("Retired", False) == RETIRED
    assert reason_of("Resigned", False) == RESIGNED
    # "head coach" alone is not a job change.
    assert reason_of("Medical clearance of head coach", False) == HEALTH
    assert reason_of("Permanent replacement", False) == INTERIM_REPLACED
    assert reason_of("Fired", True) == INTERIM_REPLACED
    assert reason_of("Hired as tight ends coach by South Carolina", False) == OTHER


TABLE = """{| class="wikitable sortable"
|-
!Team
!Outgoing coach
!Date
!Reason
!Replacement
|-
| [[New Mexico Lobos football|New Mexico]]
| [[Bob Davie (American football)|Bob Davie]]
| rowspan=2|November 25, 2019
| Resigned
| [[Danny Gonzales]]
|-
| [[UNLV Rebels football|UNLV]]
| [[Tony Sanchez (American football)|Tony Sanchez]]
| Resigned
| [[Marcus Arroyo]]
|}"""


def test_a_spanned_cell_fills_the_rows_under_it() -> None:
    rows = parse_table(TABLE)
    assert [plain(r["date"]) for r in rows] == ["November 25, 2019"] * 2
    assert [plain(r["replacement"]) for r in rows] == [
        "Danny Gonzales",
        "Marcus Arroyo",
    ]


ARTICLE = """==Coaching changes==
===Preseason and in-season===
{| class="wikitable sortable"
|-
!Team
!Outgoing coach
!Date
!Reason
!Replacement
|-
| [[Florida State Seminoles football|Florida State]]
| {{sortname|Willie|Taggart}}
| {{dts|November 3, 2019}}
| Fired
| {{sortname|Odell|Haggins}} (Interim)
|-
| [[Florida Atlantic Owls football|Florida Atlantic]]
| {{sortname|Lane|Kiffin}}
| December 7, 2019
| Hired by [[Ole Miss Rebels football|Ole Miss]]
| {{sortname|Glenn|Spencer|dab=American football}} (bowl)
|}

===End of season===
{| class="wikitable sortable"
|-
!Team
!Outgoing coach
!Date
!Reason
!Replacement
|-
| [[Florida State Seminoles football|Florida State]]
| {{sortname|Odell|Haggins}} (interim)
| December 8, 2019
| Permanent replacement
| [[Mike Norvell]]
|}

==Rankings==
"""


def test_coaching_changes_from_a_season_article() -> None:
    rows = coaching_changes(ARTICLE, 2019)
    fsu, fau, norvell = rows
    assert (fsu.team, fsu.table, fsu.midseason, fsu.season, fsu.reason) == (
        "Florida State Seminoles",
        IN_SEASON,
        True,
        2019,
        FIRED,
    )
    assert (fsu.incoming, fsu.incoming_interim) == ("Odell Haggins", True)
    # A December hire matters first for the next season, bowl coach aside.
    assert (fau.midseason, fau.season, fau.reason, fau.incoming) == (
        False,
        2020,
        LEFT_FOR_JOB,
        "Glenn Spencer",
    )
    assert (
        norvell.table,
        norvell.season,
        norvell.outgoing,
        norvell.outgoing_interim,
    ) == (
        END_OF_SEASON,
        2020,
        "Odell Haggins",
        True,
    )
    assert norvell.reason == INTERIM_REPLACED


def test_a_season_article_without_the_section_has_no_changes() -> None:
    assert coaching_changes("==Rankings==\n", 2019) == []


INFOBOX = """{{Infobox NCAA football yearly team
| year = 2014
| head_coach = [[Bill Clark (American football)|Bill Clark]]
| hc_year = 1st
| off_coach =
| oc_year =
| def_coach = [[Robb Smith]] & [[Joe Rossi]] | dc_year= 2nd
| off_scheme = Spread
}}"""

PLAINLIST = """| head_coach = [[Mark Stoops]]
| hc_year = 5th
| off_coach = {{plainlist|
* [[Eddie Gran]]
* [[Darin Hinshaw]]
}}
| oc_year = 1st
| def_coach = Robert Matthews (3rd season; regular season) / \
Bryant Vincent (interim; bowl game)
| dc_year = 3rd
"""


def test_an_empty_field_does_not_read_the_next_one() -> None:
    found = staff(INFOBOX)
    assert (found.offensive_coordinator, found.oc_year) == (None, None)
    assert (found.head_coach, found.hc_year) == ("Bill Clark", 1)


def test_two_fields_on_one_line() -> None:
    found = staff(INFOBOX)
    assert (found.defensive_coordinator, found.dc_year) == ("Robb Smith / Joe Rossi", 2)


def test_a_plainlist_and_notes_on_the_role() -> None:
    found = staff(PLAINLIST)
    assert found.offensive_coordinator == "Eddie Gran / Darin Hinshaw"
    assert found.defensive_coordinator == "Robert Matthews / Bryant Vincent"


# --- the NFL's articles ----------------------------------------------------

NFL_TABLE = """{| class="wikitable sortable plainrowheaders"
|-
! scope="col" | Team
! scope="col" | Departing coach
! scope="col" | Interim coach
! scope="col" | Incoming coach
! scope="col" | Reason for leaving
|-
! scope="row" | [[2019 Arizona Cardinals season|Arizona Cardinals]]
| colspan="2" | {{sortname|Steve|Wilks}}
| {{sortname|Kliff|Kingsbury}}
| rowspan="2" | Fired
|-
! scope="row" | [[2019 Cleveland Browns season|Cleveland Browns]]
| [[Hue Jackson]]
| [[Gregg Williams]]
| [[Freddie Kitchens]]
|}"""


def test_a_row_header_cell_and_a_spanned_column() -> None:
    first, second = parse_table(NFL_TABLE)
    assert team_of(first["team"]) == "Arizona Cardinals"
    # Spanned across the empty interim column, and everything after it
    # stays under its own header.
    assert plain(first["departing coach"]) == plain(first["interim coach"])
    assert plain(first["incoming coach"]) == "Kliff Kingsbury"
    assert plain(second["reason for leaving"]) == "Fired"


NFL_ARTICLE = """==Head coaching and front office changes==
===Head coaches===
====Off-season====
{| class="wikitable"
|-
! Team
! Departing coach
! Interim coach
! Incoming coach
! Reason for leaving
! Notes
|-
| [[2019 Cincinnati Bengals season|Cincinnati Bengals]]
| colspan="2" | {{sortname|Marvin|Lewis}}
| {{sortname|Zac|Taylor}}
| Mutual decision
| Lewis and the Bengals agreed to part ways on December 31.
|-
| [[2019 Tennessee Titans season|Tennessee Titans]]
| colspan="2" | [[Mike Mularkey]]
| [[Mike Vrabel]]
| Resigned
| Mularkey resigned on January 12 to take the job at a university.
|}
====In-season====
{| class="wikitable"
|-
! Team
! Departing coach
! Reason for leaving
! Interim replacement
! Notes
|-
| [[2019 Washington Redskins season|Washington Redskins]]
| [[Jay Gruden]]
| Fired
| [[Bill Callahan (American football coach)|Bill Callahan]]
| After an 0–5 start, Gruden was fired on October 7.
|-
| [[2019 Indianapolis Colts season|Indianapolis Colts]]
| [[Chuck Pagano]]
| Medical leave
| [[Bruce Arians]]
| Pagano took leave for treatment and returned for the last game.
|}
===Front office===
;Offseason
{| class="wikitable"
|-
! Team
! Position
! 2018 office holder
! Reason for leaving
! 2019 replacement
|-
| [[2019 New York Jets season|New York Jets]]
| GM
| [[Mike Maccagnan]]
| Fired
| [[Joe Douglas]]
|}

==Stadiums==
"""


def test_nfl_coaching_changes() -> None:
    changes = coaching_changes(NFL_ARTICLE, 2019, NFL)
    assert [(c.team, c.table, c.midseason, c.season) for c in changes] == [
        ("Cincinnati Bengals", OFFSEASON, False, 2019),
        ("Tennessee Titans", OFFSEASON, False, 2019),
        ("Washington Redskins", IN_SEASON, True, 2019),
    ]
    bengals, titans, washington = changes
    assert (bengals.outgoing, bengals.incoming, bengals.reason) == (
        "Marvin Lewis",
        "Zac Taylor",
        FIRED,
    )
    # A date with no year, in an off-season table, is the winter before.
    assert bengals.date == "2018-12-31"
    # "Resigned" in the cell, the job he left for in the notes.
    assert titans.reason == LEFT_FOR_JOB
    assert titans.reason_text.startswith("Resigned: Mularkey resigned")
    # The in-season table names the interim as the incoming coach.
    assert (washington.outgoing, washington.incoming) == ("Jay Gruden", "Bill Callahan")
    assert washington.incoming_interim
    assert washington.date == "2019-10-07"


def test_the_2007_to_2009_columns() -> None:
    """Named by season, the incoming coach followed by where he came from."""
    article = """==Head coach/front office changes==
===Head coach===
;Offseason
{| class="wikitable"
|-
! Team
! 2007 Coach
! Former Coach
! Reason for leaving
! Notes
|-
| [[2007 Atlanta Falcons season|Atlanta Falcons]]
| [[Bobby Petrino]], former head coach, [[Louisville Cardinals football|Louisville]]
| [[Jim L. Mora|Jim Mora]]
| Fired
| Hired in 2004.
|}
;In-season
{| class="wikitable"
|-
! Team
! Coach at start of the season
! Interim coach
! Reason for leaving
! Notes
|-
| [[2007 Atlanta Falcons season|Atlanta Falcons]]
| [[Bobby Petrino]]
| [[Emmitt Thomas]]
| Resigned
| Petrino resigned after going 3–10 to take job at Arkansas.
|}
"""
    offseason, in_season = coaching_changes(article, 2007, NFL)
    assert (offseason.outgoing, offseason.incoming) == ("Jim Mora", "Bobby Petrino")
    assert (in_season.outgoing, in_season.incoming) == (
        "Bobby Petrino",
        "Emmitt Thomas",
    )
    assert in_season.reason == LEFT_FOR_JOB


def test_nfl_reasons() -> None:
    assert reason_of("Contract expired", False) == FIRED
    assert reason_of("Traded", False) == LEFT_FOR_JOB
    assert reason_of("Resigned to coach the University of Alabama", False) == (
        LEFT_FOR_JOB
    )
    # Not "to coach" somewhere else: he isn't coming back.
    assert reason_of("Fisher would not return to coach the team in 2011", False) == (
        FIRED
    )


def test_an_nfl_team_season_link() -> None:
    assert team_of("[[2019 Buffalo Bills season|Buffalo Bills]]") == "Buffalo Bills"


def test_the_nfl_infobox_calls_the_head_coach_coach() -> None:
    lead = """{{Infobox NFL team season
| team            = Washington Redskins
| coach           = [[Jay Gruden]] (fired on October 7, 0-5 record)<br>[[Bill Callahan (American football coach)|Bill Callahan]] (interim, 3-8 record)
| off_coach       = [[Kevin O'Connell (American football)|Kevin O'Connell]]
| def_coach       = [[Greg Manusky]]
}}"""  # noqa: E501
    found = staff(lead, NFL)
    assert found.head_coach == "Jay Gruden / Bill Callahan"
    assert found.offensive_coordinator == "Kevin O'Connell"
    assert found.defensive_coordinator == "Greg Manusky"
    assert (found.hc_year, found.oc_year, found.dc_year) == (None, None, None)
