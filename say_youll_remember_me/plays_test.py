"""Turning games into quarterback rows, on games built by hand. No bucket."""

from lucky_ones.arrow import ArrowPlay
from lucky_ones.epa import PlayEPA
from lucky_ones.game import GamePlays

from .plays import MIN_ATTEMPTS, Game, season_quarterbacks

LSU, AUBURN = "99", "2"


def _play(number: int, offense: str, text: str, game_id: str = "g1") -> ArrowPlay:
    return ArrowPlay(
        league="ncaafb",
        season=2019,
        week=1,
        game_id=game_id,
        play_id=f"{game_id}-{number}",
        play_number=number,
        period=1,
        clock_seconds=900 - number,
        wallclock=None,
        home_score=0,
        away_score=0,
        offense_team_id=offense,
        defense_team_id=AUBURN if offense == LSU else LSU,
        down=1,
        distance=10,
        yardline=75,
        play_type="Pass",
        text=text,
        scoring_play=False,
        is_penalty=False,
        is_turnover=False,
        drive_id=None,
        drive_number=1,
        drive_team_id=offense,
        drive_result=None,
        drive_is_score=False,
    )


def _game(plays: list[ArrowPlay], game_id: str = "g1", priced: bool = True) -> Game:
    return Game(
        game_id=game_id,
        home_team_id=LSU,
        away_team_id=AUBURN,
        plays=plays,
        priced=priced,
    )


# Three spellings, one quarterback each side -- the formats `qb` reads.
GAME = _game(
    [
        _play(1, LSU, "Joe Burrow pass complete to Ja'Marr Chase for 20 yds"),
        _play(2, AUBURN, "(Shotgun) Nix,Bo pass incomplete to Seth Williams"),
        _play(3, LSU, "Joe Burrow pass incomplete to Justin Jefferson"),
        _play(4, AUBURN, "(15:00) Shotgun #10 B.Nix pass complete to #1 A.Schwartz"),
        _play(5, LSU, "Myles Brennan pass complete to Terrace Marshall for 8 yds"),
    ]
)


def _price(bounded: dict[int, float]):
    def price(game: GamePlays) -> list[PlayEPA]:
        return [
            PlayEPA(
                play_id=p.play_id,
                play_number=p.play_number,
                offense_is_home=p.offense_team_id == game.home_team_id,
                expected_points=0.0,
                epa=bounded.get(p.play_number, 0.0),
                bounded=bounded.get(p.play_number, 0.0),
                win_probability=0.5,
                weight=1.0,
            )
            for p in game.plays
        ]

    return price


def _same(team_id: str) -> str | None:
    return team_id


def test_starters_and_their_passes() -> None:
    rows, unplaced = season_quarterbacks(
        2019,
        [GAME],
        canonical=_same,
        price=_price({1: 1.5, 3: -0.5, 2: -0.2, 4: 0.8}),
        source="test",
    )
    assert not unplaced
    by_key = {(r.espn_id, r.player_key): r for r in rows}
    burrow = by_key[(LSU, "burrow j")]
    assert (burrow.team, burrow.starts, burrow.started_week_one) == (
        "LSU Tigers",
        1,
        True,
    )
    assert (burrow.attempts, burrow.epa) == (2, 1.0)
    # Two spellings, one quarterback.
    nix = by_key[(AUBURN, "nix b")]
    assert (nix.starts, nix.attempts, nix.epa) == (1, 2, 0.6)


def test_a_backup_with_a_handful_of_attempts_is_left_out() -> None:
    rows, _ = season_quarterbacks(2019, [GAME], _same, _price({}), "test")
    assert all(r.player_key != "brennan m" for r in rows)
    assert MIN_ATTEMPTS > 1


def test_an_unpriced_season_carries_no_attempts_rather_than_zero() -> None:
    rows, _ = season_quarterbacks(2013, [GAME], _same, None, "espn-pbp")
    assert rows and all(r.attempts is None and r.epa is None for r in rows)
    assert {r.player_key for r in rows} == {"burrow j", "nix b"}


def test_a_team_the_registry_does_not_know_is_reported_not_guessed() -> None:
    rows, unplaced = season_quarterbacks(
        2019, [GAME], lambda t: t if t == LSU else None, None, "espn-pbp"
    )
    assert unplaced == {AUBURN}
    assert {r.espn_id for r in rows} == {LSU}


def test_week_one_is_the_first_game_with_a_start() -> None:
    backup = _game(
        [
            _play(
                1,
                LSU,
                "Myles Brennan pass complete to Terrace Marshall for 8 yds",
                "g0",
            )
        ],
        game_id="g0",
    )
    rows, _ = season_quarterbacks(2019, [backup, GAME], _same, None, "espn-pbp")
    by_key = {(r.espn_id, r.player_key): r for r in rows}
    assert by_key[(LSU, "brennan m")].started_week_one
    assert not by_key[(LSU, "burrow j")].started_week_one
    # Auburn's first game with plays is the second one here.
    assert by_key[(AUBURN, "nix b")].started_week_one


def test_a_game_whose_home_side_is_unknown_counts_starts_but_is_not_priced() -> None:
    unknown = GAME._replace(priced=False)
    rows, _ = season_quarterbacks(2019, [unknown], _same, _price({1: 1.5}), "test")
    burrow = next(r for r in rows if r.player_key == "burrow j")
    assert (burrow.starts, burrow.attempts, burrow.epa) == (1, 0, 0.0)
