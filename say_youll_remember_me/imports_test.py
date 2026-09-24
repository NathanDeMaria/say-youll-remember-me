"""Reading the data pulls in call-it-what-you-want and nothing else. Keep it that way.

A serving image that wants to know whether a team changed coaches shouldn't
carry an HTTP client to find out. That holds only while nothing on the import
path of `say_youll_remember_me` reaches for the modules that fetch --
`wikipedia` and `sync` -- which is easy to break with one top-level import.
"""

import subprocess
import sys

_FETCHING = (
    "say_youll_remember_me.wikipedia",
    "say_youll_remember_me.sync",
    "urllib.request",
)
_THIRD_PARTY_ALLOWED = ("call_it_what_you_want",)


def test_importing_the_package_fetches_nothing() -> None:
    checked = ", ".join(repr(m) for m in _FETCHING)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys\n"
            "import say_youll_remember_me\n"
            f"print(','.join(m for m in ({checked},) if m in sys.modules))\n",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "", (
        f"importing say_youll_remember_me pulled in {result.stdout.strip()}. "
        "Import the fetching modules where they're used, not from the package."
    )


def test_importing_the_package_pulls_in_nothing_third_party() -> None:
    allowed = ", ".join(repr(m) for m in _THIRD_PARTY_ALLOWED)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, sysconfig, pathlib\n"
            f"allowed = ({allowed},)\n"
            "before = set(sys.modules)\n"
            "import say_youll_remember_me\n"
            "site = pathlib.Path(sysconfig.get_paths()['purelib'])\n"
            "leaked = set()\n"
            "for name in set(sys.modules) - before:\n"
            "    module = sys.modules[name]\n"
            "    path = getattr(module, '__file__', None)\n"
            "    root = name.split('.')[0]\n"
            "    ours = root in ('say_youll_remember_me', *allowed)\n"
            "    if path and pathlib.Path(path).is_relative_to(site) and not ours:\n"
            "        leaked.add(root)\n"
            "print(','.join(sorted(leaked)))\n",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "", f"importing pulled in {result.stdout.strip()}"
