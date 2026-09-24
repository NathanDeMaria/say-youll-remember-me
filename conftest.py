from collections.abc import Iterator
from pathlib import Path

import pytest
from call_it_what_you_want import default_classifications, default_teams
from call_it_what_you_want.local import ENV_VAR


@pytest.fixture(autouse=True)
def no_local_team_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """
    Read call-it-what-you-want's bundled teams only.

    Its `default_teams` layers whatever the machine running the suite has
    recorded locally on top of what shipped, so a test that resolves a name
    would otherwise pass or fail by whose laptop it ran on.
    """
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "ciwyw-records"))
    default_teams.cache_clear()
    default_classifications.cache_clear()
    yield
    default_teams.cache_clear()
    default_classifications.cache_clear()
