"""Reading coaching facts out of Wikipedia's football articles.

Two sources, both in wikitext:

- **A season article's coaching changes.** College ("2019 NCAA Division I
  FBS football season", "Coaching changes"): one table of preseason and
  in-season changes, one of changes announced during the season that take
  effect after it, each row naming the team, the coach leaving, a date,
  why, and who replaced him. NFL ("2019 NFL season", a "Head coach..."
  section): an off-season table of every change since the last season and
  an in-season table of this season's firings, with the date only in the
  notes. The NFL tables change shape over the years -- 2007-2009 name
  their columns by season ("2008 Coach", "2007 Coach(es)"), and later
  ones open each row with a header cell and span the interim column when
  there was none -- so the columns are found by what their headers say.
- **A team-season article's infobox** ("2019 LSU Tigers football team",
  "2019 Kansas City Chiefs season"): `head_coach` (the NFL's is `coach`),
  `off_coach` and `def_coach`; in college, each with a `*_year` field
  saying which season at the school it is.

Not imported by the package: nothing here is needed to read the bundled
data, and fetching is `sync`'s business. Fetching uses only the standard
library, and identifies itself the way the Wikimedia API asks, with a URL
to this project -- a generic user agent gets rate limited within a few
dozen requests.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from .types import (
    END_OF_SEASON,
    FIRED,
    HEALTH,
    IN_SEASON,
    INTERIM_REPLACED,
    LEFT_FOR_JOB,
    NCAAFB,
    NFL,
    OFFSEASON,
    OTHER,
    RESIGNED,
    RETIRED,
)

API = "https://en.wikipedia.org/w/api.php"
RAW = "https://en.wikipedia.org/w/index.php"
USER_AGENT = (
    "say-youll-remember-me/0.1 (https://github.com/NathanDeMaria/say-youll-remember-me)"
)
# Titles per API request, and the pause between requests. The API allows 50
# titles, but a request that large is what drew the rate limit here.
BATCH = 20
PAUSE_SECONDS = 4.0

MONTHS: tuple[str, ...] = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def season_article(season: int, league: str = NCAAFB) -> str:
    if league == NFL:
        return f"{season} NFL season"
    return f"{season} NCAA Division I FBS football season"


def team_season_article(team: str, season: int, league: str = NCAAFB) -> str:
    if league == NFL:
        return f"{season} {team} season"
    return f"{season} {team} football team"


# --- fetching ---------------------------------------------------------------


def _get(url: str, data: bytes | None = None) -> str:
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def _cache_path(cache: Path, title: str, kind: str) -> Path:
    safe = re.sub(r"[^\w\-. ']", "_", title)
    return cache / kind / f"{safe}.wiki"


def fetch_article(title: str, cache: Path | None = None) -> str | None:
    """The whole article's wikitext, or None if there's no such article."""
    if cache is not None:
        path = _cache_path(cache, title, "article")
        if path.exists():
            return path.read_text(encoding="utf-8")
    query = urllib.parse.urlencode({"title": title, "action": "raw"})
    try:
        text = _get(f"{RAW}?{query}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    if cache is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return text


def fetch_leads(
    titles: Sequence[str], cache: Path | None = None
) -> dict[str, str | None]:
    """Each article's opening section -- where the infobox is -- by the title asked for.

    Batched through the API, following redirects, so "2019 FIU Panthers
    football team" finds the article whatever it is filed under. None for a
    title with no article. Backs off and retries when the API answers with
    a rate-limit page instead of JSON.
    """
    found: dict[str, str | None] = {}
    todo = []
    for title in titles:
        path = _cache_path(cache, title, "lead") if cache is not None else None
        if path is not None and path.exists():
            text = path.read_text(encoding="utf-8")
            found[title] = text or None
        else:
            todo.append(title)
    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        body = urllib.parse.urlencode(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "rvsection": 0,
                "format": "json",
                "redirects": 1,
                "titles": "|".join(batch),
            }
        ).encode()
        for attempt in range(8):
            try:
                query = json.loads(_get(API, data=body))["query"]
                break
            except (json.JSONDecodeError, KeyError):
                time.sleep(30 * (attempt + 1))
        else:
            raise RuntimeError(
                f"Wikipedia kept refusing the batch starting {batch[0]!r}"
            )
        asked_as: dict[str, str] = {}
        for hop in query.get("normalized", []) + query.get("redirects", []):
            asked_as[hop["to"]] = asked_as.get(hop["from"], hop["from"])
        for page in query["pages"].values():
            revisions = page.get("revisions")
            text = revisions[0]["slots"]["main"]["*"] if revisions else None
            found[asked_as.get(page["title"], page["title"])] = text
        for title in batch:
            found.setdefault(title, None)
            if cache is not None:
                path = _cache_path(cache, title, "lead")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(found[title] or "", encoding="utf-8")
        time.sleep(PAUSE_SECONDS)
    return found


# --- cleaning wikitext ------------------------------------------------------

_REF = re.compile(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", re.S)
_BREAK = re.compile(r"<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")
_SORTNAME = re.compile(r"\{\{\s*sortname\s*\|([^|}]*)\|([^|}]*)[^}]*\}\}", re.I)
_LINK = re.compile(r"\[\[([^\]|]*)(?:\|([^\]]*))?\]\]")
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_DISAMBIGUATOR = re.compile(r"\s*\((?:American football|[^)]*coach[^)]*|born \d+)\)$")


def plain(text: str) -> str:
    """Wikitext down to what a reader sees: links to labels, `sortname` to names."""
    text = _REF.sub("", text)
    text = _BREAK.sub(" / ", text)
    text = _TAG.sub("", text)
    text = _SORTNAME.sub(lambda m: f"{m.group(1).strip()} {m.group(2).strip()}", text)
    text = _LINK.sub(lambda m: m.group(2) or _DISAMBIGUATOR.sub("", m.group(1)), text)
    while _TEMPLATE.search(text):
        text = _TEMPLATE.sub("", text)
    text = text.replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", text).strip(" /")


def link_target(text: str) -> str | None:
    """The first link's target, which is the article the cell points at."""
    match = _LINK.search(text)
    return match.group(1).strip() if match else None


def team_of(cell: str) -> str | None:
    """The team a table's first cell names: "Rutgers Scarlet Knights" from its link.

    The link is often to the team's season -- "2019 Rutgers Scarlet Knights
    football team", "2019 Buffalo Bills season" -- and the team is what's
    left without the year and the kind of article.
    """
    target = link_target(cell)
    if target is None:
        return None
    target = re.sub(r"^\d{4} ", "", target)
    return re.sub(r" (?:football( team)?|season)$", "", target).strip()


_DTS = re.compile(r"\{\{\s*dts\s*\|([^}]*)\}\}", re.I)


def date_of(cell: str, page_season: int) -> str | None:
    """An ISO date from a table cell, or None.

    Reads `{{dts|2016|12|1}}`, `{{dts|December 1, 2016}}` and plain
    "December 1, 2016". A date with no year ("December 1") is placed in the
    season the article is about, except January through April, which is the
    offseason after it.
    """
    dts = _DTS.search(cell)
    if dts:
        parts = [p.strip() for p in dts.group(1).split("|") if "=" not in p]
        if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
            return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        cell = " ".join(parts)
    text = plain(cell)
    match = re.search(r"(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:,?\s+(\d{4}))?", text)
    if not match:
        return None
    month = MONTHS.index(match.group(1)) + 1
    year = int(match.group(3)) if match.group(3) else page_season + (month <= 4)
    return f"{year:04d}-{month:02d}-{int(match.group(2)):02d}"


def ordinal(text: str | None) -> int | None:
    """ "3rd" -> 3."""
    if not text:
        return None
    match = re.match(r"\s*(\d+)", plain(text))
    return int(match.group(1)) if match else None


def reason_of(reason_text: str, outgoing_interim: bool) -> str:
    """The category for why a coach left, from the article's words.

    Order matters. An interim giving way is its own category whatever the
    cell says. A coach whose next job was an assistant's -- "hired as
    defensive coordinator by Penn State" -- was fired, and the article is
    describing where he landed; that is checked before "hired by", which
    otherwise reads it as a coach leaving for a better job. "Agreed to part
    ways" is a firing, and so is an NFL "contract expired": a team that
    wanted him would have extended it. "Head coach" alone is not a job
    change: "medical clearance of head coach" is not one. An NFL coach
    "traded" went to the team that traded for him, which is leaving for a
    job.
    """
    text = reason_text.lower()
    if outgoing_interim or re.search(r"permanent replacement|^replaced", text):
        return INTERIM_REPLACED
    if re.search(r"coordinator|position coach|assistant|analyst|consultant", text):
        return FIRED
    if re.search(
        r"fired|dismiss|terminat|mutual|contract not renewed|not retained|reassign|"
        r"bought out|let go|part(ed)? ways|relieved|not renew|w(ill|ould) not return|"
        r"contract expired|expired contract",
        text,
    ):
        return FIRED
    if re.search(
        r"hired by|hired as head|accepted|to become|left for|took (the )?job|became|"
        r"to take|(resigned|left) to coach|traded",
        text,
    ):
        return LEFT_FOR_JOB
    if re.search(r"retir", text):
        return RETIRED
    if re.search(r"died|death|passed away|health|medical|illness", text):
        return HEALTH
    if re.search(r"resign|stepped down|step down", text):
        return RESIGNED
    return OTHER


# --- tables -----------------------------------------------------------------


def _split_top(text: str, separator: str) -> list[str]:
    """Split on `separator` where it isn't inside [[...]] or {{...}}."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        pair = text[i : i + 2]
        if pair in ("[[", "{{"):
            depth += 1
            i += 2
            continue
        if pair in ("]]", "}}"):
            depth = max(0, depth - 1)
            i += 2
            continue
        if depth == 0 and text.startswith(separator, i):
            parts.append(text[start:i])
            i += len(separator)
            start = i
            continue
        i += 1
    parts.append(text[start:])
    return parts


def _attributes(cell: str) -> tuple[str, str]:
    """A cell's attributes (`rowspan=2`) and its content, split at the first `|`."""
    parts = _split_top(cell, "|")
    if (
        len(parts) > 1
        and "=" in parts[0]
        and "[[" not in parts[0]
        and "{{" not in parts[0]
    ):
        return parts[0], "|".join(parts[1:])
    return "", cell


def parse_table(table: str) -> list[dict[str, str]]:
    """A wikitable's rows as {header: cell wikitext}, spanned cells filled in.

    `!` opens a header cell, which is a column's name until the header row
    is over and the first cell of a row after that -- the NFL articles
    open each row with the team as a header cell (`! scope="row" | ...`).
    A `rowspan` fills the cells below it; a `colspan` fills the ones beside
    it, so a departing coach spanned across an empty "interim" column reads
    in both, and every column after it stays where its header is.
    """
    headers: list[str] = []
    raw_rows: list[list[str]] = []
    current: list[str] | None = None
    header_done = False
    for line in table.splitlines():
        stripped = line.strip()
        if stripped.startswith("{|") or stripped.startswith("|+"):
            continue
        if stripped.startswith("|-") or stripped.startswith("|}"):
            if current:
                raw_rows.append(current)
            current = [] if stripped.startswith("|-") else None
            header_done = header_done or bool(headers)
            continue
        if stripped.startswith("!") and not header_done:
            headers += [
                plain(_attributes(h)[1]).lower() for h in _split_top(stripped[1:], "!!")
            ]
            continue
        if stripped.startswith("|") or stripped.startswith("!"):
            if current is None:
                current = []
            current += _split_top(stripped[1:], "||")
        elif current:
            current[-1] += "\n" + line
    if current:
        raw_rows.append(current)

    rows: list[dict[str, str]] = []
    pending: dict[int, list] = {}  # column -> [rows remaining, content]
    for cells in raw_rows:
        filled: list[str] = []
        queue = list(cells)
        column = 0
        while queue or column in pending:
            if column in pending:
                filled.append(pending[column][1])
                pending[column][0] -= 1
                if pending[column][0] == 0:
                    del pending[column]
            else:
                attributes, content = _attributes(queue.pop(0))
                span = re.search(r"rowspan\s*=\s*\"?(\d+)", attributes)
                wide = re.search(r"colspan\s*=\s*\"?(\d+)", attributes)
                for _ in range(int(wide.group(1)) if wide else 1):
                    if span and int(span.group(1)) > 1:
                        pending[column] = [int(span.group(1)) - 1, content]
                    filled.append(content)
                    column += 1
                continue
            column += 1
        if headers and len(filled) >= 2:
            rows.append(dict(zip(headers, (c.strip() for c in filled))))
    return rows


class ChangeRow(NamedTuple):
    """One row of a season article's coaching-change tables, before team resolution."""

    team: str
    table: str
    season: int
    midseason: bool
    date: str | None
    outgoing: str
    outgoing_interim: bool
    reason: str
    reason_text: str
    incoming: str | None
    incoming_interim: bool


def _column(row: dict[str, str], *names: str) -> str:
    for header, value in row.items():
        if any(name in header for name in names):
            return value
    return ""


def coaching_changes(
    article: str, page_season: int, league: str = NCAAFB
) -> list[ChangeRow]:
    """Every row of a season article's head-coach change tables."""
    if league == NFL:
        return _nfl_changes(article, page_season)
    start = article.find("==Coaching changes==")
    if start < 0:
        return []
    following = re.search(r"\n==[^=]", article[start + 2 :])
    section = (
        article[start : start + 2 + following.start()] if following else article[start:]
    )
    found: list[ChangeRow] = []
    for block in re.split(r"\n===", section):
        heading = block.split("\n", 1)[0].lower()
        table_kind = END_OF_SEASON if "end" in heading else IN_SEASON
        for table in re.findall(r"\{\|.*?\n\|\}", block, re.S):
            for row in parse_table(table):
                team = team_of(_column(row, "team", "school"))
                if team is None:
                    continue
                outgoing_cell = _column(row, "outgoing", "departing", "former")
                reason_cell = _column(row, "reason")
                incoming_cell = _column(
                    row, "replacement", "incoming", "new coach", "successor"
                )
                date = date_of(_column(row, "date"), page_season)
                outgoing = plain(outgoing_cell)
                incoming = plain(incoming_cell) or None
                reason_text = plain(reason_cell)
                reason = reason_of(reason_text, "interim" in outgoing.lower())
                outgoing_interim = reason == INTERIM_REPLACED
                midseason, season = _timing(table_kind, date, page_season)
                found.append(
                    ChangeRow(
                        team=team,
                        table=table_kind,
                        season=season,
                        midseason=midseason,
                        date=date,
                        outgoing=re.sub(
                            r"\s*\(interim[^)]*\)", "", outgoing, flags=re.I
                        ).strip(),
                        outgoing_interim=outgoing_interim,
                        reason=reason,
                        reason_text=reason_text,
                        incoming=re.sub(
                            r"\s*\((?:interim|bowl)[^)]*\)", "", incoming, flags=re.I
                        ).strip()
                        if incoming
                        else None,
                        incoming_interim=bool(
                            incoming and "interim" in incoming.lower()
                        ),
                    )
                )
    return found


# An NFL article's head-coach section: "Head coach/front office changes",
# "Head coaching and general manager changes", and the like.
_NFL_SECTION = re.compile(r"^==[^=\n]*[Cc]oach[^=\n]*==[ \t]*$", re.M)
# Its subheadings, `===`/`====` or a `;` definition line. The one that
# names a front office or general managers ends the coaches' part.
_NFL_SUBHEADING = re.compile(r"\n(?:={3,}[^\n]*|;[^\n]*)")


def _nfl_changes(article: str, page_season: int) -> list[ChangeRow]:
    """The NFL article's off-season and in-season head-coach tables.

    Off-season rows are this season's changes; in-season rows are its
    coaches who didn't finish it. Both are `season` = the article's. The
    section also holds the front office's changes, under a `===` heading
    of their own with the same off-season and in-season split beneath it,
    so a front office heading skips everything until the next `===`.
    """
    found: list[ChangeRow] = []
    for match in _NFL_SECTION.finditer(article):
        following = re.search(r"\n==[^=]", article[match.end() :])
        end = match.end() + following.start() if following else len(article)
        section = article[match.end() : end]
        pieces = _NFL_SUBHEADING.split(section)
        headings = _NFL_SUBHEADING.findall(section)
        kind, front_office = OFFSEASON, False
        for index, piece in enumerate(pieces):
            if index:
                heading = headings[index - 1].strip().lower()
                if re.match(r"===[^=]", heading):
                    front_office = False
                if re.search(r"front office|general manager|executive", heading):
                    front_office = True
                kind = IN_SEASON if re.search(r"in[- ]season", heading) else OFFSEASON
            if front_office:
                continue
            for table in re.findall(r"\{\|.*?\n\|\}", piece, re.S):
                found += _nfl_rows(parse_table(table), kind, page_season)
    return found


def _nfl_rows(
    rows: list[dict[str, str]], kind: str, page_season: int
) -> list[ChangeRow]:
    found: list[ChangeRow] = []
    for row in rows:
        if any(re.search(r"position|office holder|\bgm\b", h) for h in row):
            continue  # a front office table
        team = team_of(_column(row, "team"))
        outgoing = _nfl_name(_nfl_coach(row, kind, page_season, incoming=False))
        if team is None or not outgoing:
            continue
        incoming = _nfl_name(_nfl_coach(row, kind, page_season, incoming=True))
        notes = plain(_column(row, "notes", "story"))
        reason_text = plain(_column(row, "reason")) or _first_sentence(notes)
        reason = reason_of(reason_text, False)
        if reason == HEALTH and "leave" in reason_text.lower():
            continue  # a leave of absence, and he came back
        if reason in (RESIGNED, OTHER):
            # "Resigned", with where he went only in the notes: Petrino
            # "resigned after going 3-10 to take job at University of
            # Arkansas".
            told = f"{reason_text}: {_first_sentence(notes)}"
            if reason_of(told, False) == LEFT_FOR_JOB:
                reason_text, reason = told, LEFT_FOR_JOB
        found.append(
            ChangeRow(
                team=team,
                table=kind,
                season=page_season,
                midseason=kind == IN_SEASON,
                date=_nfl_date(" ".join((reason_text, notes)), kind, page_season),
                outgoing=outgoing,
                outgoing_interim=False,
                reason=reason,
                reason_text=reason_text,
                incoming=incoming or None,
                incoming_interim=kind == IN_SEASON,
            )
        )
    return found


def _nfl_coach(row: dict[str, str], kind: str, page_season: int, incoming: bool) -> str:
    """The departing or incoming coach's cell, found by what its header says.

    Off-season, the departing coach is "departing", "former" or last
    season's ("2009 head coach", "2008 coach(es)"), and the incoming one
    "incoming", a "replacement" or this season's ("2010 head coach", "2007
    coach"); an "interim" column there is who finished last season, and
    neither. In-season, the departing coach is this season's ("2010
    coach"), the "ex-coach" or the "coach at start of the season", and the
    incoming one is whichever column says "interim".
    """
    season = page_season - 1 if kind == OFFSEASON else page_season
    for header, value in row.items():
        interim = "interim" in header
        if kind == IN_SEASON and incoming:
            wanted = interim
        elif incoming:
            wanted = not interim and (
                "incoming" in header
                or "replacement" in header
                or header.startswith(f"{page_season} ")
            )
        else:
            wanted = not interim and (
                any(word in header for word in ("departing", "former", "ex-", "start"))
                or header.startswith(f"{season} ")
            )
        if wanted:
            return value
    return ""


def _nfl_name(cell: str) -> str:
    """The first coach a cell names.

    2007-2009 follow the name with his last job ("Bobby Petrino, former
    head coach, ..."), and a cell can name the interim after him ("Bobby
    Petrino; / Emmitt Thomas").
    """
    return re.split(r"[,;/]", plain(cell))[0].strip()


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[a-z0-9)])\. ", text, maxsplit=1)[0]


def _nfl_date(text: str, kind: str, page_season: int) -> str | None:
    """The first date the notes give, placed in its year.

    A date without a year is in the months around the season it describes:
    an off-season change from August on happened the year before the
    article's season, an in-season one from January on the year after.
    """
    match = re.search(r"(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:,?\s+(\d{4}))?", text)
    if not match:
        return None
    month = MONTHS.index(match.group(1)) + 1
    if match.group(3):
        year = int(match.group(3))
    elif kind == OFFSEASON:
        year = page_season - (month >= 8)
    else:
        year = page_season + (month < 8)
    return f"{year:04d}-{month:02d}-{int(match.group(2)):02d}"


def _timing(table_kind: str, date: str | None, page_season: int) -> tuple[bool, int]:
    """Whether a change came mid-season, and the season it first matters for.

    Mid-season is a coach who didn't finish the regular season: gone by
    November 20, the last weekend before most regular seasons end. That
    season is the one the change first matters for. A preseason change
    (spring or summer of the article's year) matters for that season too.
    Anything after the regular season -- the late-November firings, the
    December hires, the whole end-of-season table -- first matters for the
    next one; an interim who only coaches the bowl game doesn't count.
    """
    if table_kind != IN_SEASON or date is None or int(date[:4]) != page_season:
        return False, page_season + 1
    month, day = int(date[5:7]), int(date[8:10])
    midseason = month in (9, 10) or (month == 11 and day <= 20)
    preseason = 2 <= month <= 8
    return midseason, page_season if (midseason or preseason) else page_season + 1


class StaffRow(NamedTuple):
    head_coach: str | None
    hc_year: int | None
    offensive_coordinator: str | None
    oc_year: int | None
    defensive_coordinator: str | None
    dc_year: int | None


def _field(infobox: str, key: str) -> str | None:
    """One infobox field's raw value, or None if the infobox doesn't have it."""
    # Horizontal whitespace only around the `=`: `\s` would carry an empty
    # field's match onto the next line and read that field's value as this
    # one's. A field may also follow another on the same line.
    match = re.search(rf"(?:^[ \t]*\||\|)[ \t]*{key}[ \t]*=[ \t]*(.*)$", infobox, re.M)
    if not match:
        return None
    # Two fields written on one line -- "Robb Smith | dc_year = 2nd" -- end
    # this one at the next field's name, but only outside links and
    # templates, whose own `|name=` parameters are part of the value.
    parts = _split_top(match.group(1), "|")
    kept = []
    for part in parts:
        if kept and re.match(r"\s*\w+\s*=", part):
            break
        kept.append(part)
    value = "|".join(kept).strip()
    # A list spread over the lines that follow: {{plainlist| * A * B }}.
    if value.lower().startswith("{{plainlist"):
        items = []
        for line in infobox[match.end() :].splitlines()[1:]:
            if line.strip().startswith("}}") or line.strip().startswith("|"):
                break
            if line.strip().startswith("*"):
                items.append(line.strip()[1:])
        value = "<br>".join(items)
    return value


def staff(lead: str, league: str = NCAAFB) -> StaffRow:
    """Head coach and coordinators, and their seasons at the school, from an infobox.

    The NFL's infobox calls the head coach `coach` and numbers nobody's
    seasons, so its `*_year` fields are None.
    """

    def name(key: str) -> str | None:
        value = _field(lead, key)
        if not value:
            return None
        # "(3rd season; regular season)", "(interim; bowl game)": notes on
        # the role, not part of the name.
        names = re.sub(r"\s*\([^)]*(?:\)|$)", "", plain(value))
        names = names.replace(" & ", " / ").replace(" and ", " / ")
        return re.sub(r"(?:\s*/\s*)+", " / ", names).strip(" /") or None

    return StaffRow(
        head_coach=name("coach" if league == NFL else "head_coach"),
        hc_year=ordinal(_field(lead, "hc_year")),
        offensive_coordinator=name("off_coach"),
        oc_year=ordinal(_field(lead, "oc_year")),
        defensive_coordinator=name("def_coach"),
        dc_year=ordinal(_field(lead, "dc_year")),
    )
