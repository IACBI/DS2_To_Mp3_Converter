"""The CLI must finish with a legacy or ASCII output encoding instead of crashing on the banner."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ds2_fixtures import SP_FORMAT, make_ds2, random_payload


SCRIPT = Path(__file__).resolve().parent.parent / "ds2_to_mp3.py"


def run_cli(args, encoding, cwd):
    env = dict(os.environ, PYTHONIOENCODING=encoding)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd, env=env, capture_output=True, timeout=120,
    )


@pytest.mark.parametrize("encoding", ["cp1254", "ascii"])
def test_convert_survives_non_unicode_console(tmp_path, encoding):
    pytest.importorskip("lameenc")
    pytest.importorskip("mutagen")
    src = tmp_path / "rec.DS2"
    src.write_bytes(make_ds2([(0, random_payload(1))], SP_FORMAT))
    out = tmp_path / "out"

    result = run_cli([str(src), "-o", str(out)], encoding, tmp_path)

    assert result.returncode == 0, result.stderr.decode("ascii", "replace")
    assert b"Traceback" not in result.stdout + result.stderr
    assert (out / "rec_converted.mp3").exists()


@pytest.mark.parametrize("encoding", ["cp1254", "ascii"])
def test_help_survives_non_unicode_console(tmp_path, encoding):
    result = run_cli(["--help"], encoding, tmp_path)

    assert result.returncode == 0
    assert b"Traceback" not in result.stdout + result.stderr
