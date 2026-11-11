from __future__ import annotations

import pytest

from tailarr.media.tools import TOOLS, ToolError, parse_version, run_tool, tool_version


def test_parse_version() -> None:
    assert parse_version("mkvmerge v82.0 ('I'm The President') 64-bit") == "82.0"
    assert parse_version("MediaInfo Command line,\nMediaInfoLib - v24.01") == "24.01"
    assert parse_version("dovi_tool 2.3.1") == "2.3.1"
    assert parse_version("nothing here") is None


def test_missing_tool_gives_friendly_error() -> None:
    with pytest.raises(ToolError) as err:
        run_tool("definitely-not-a-real-tool", [])
    assert "isn't installed" in err.value.message


def test_failure_keeps_technical_details(tmp_path) -> None:
    with pytest.raises(ToolError) as err:
        run_tool("mkvmerge", ["-J", str(tmp_path / "missing.mkv")])
    assert "reported a problem" in err.value.message
    assert err.value.details  # raw output kept for "Show technical details"


def test_names_with_spaces_and_quotes_are_safe(tmp_path, samples_dir) -> None:
    import shutil

    odd = tmp_path / 'Film\'s "Name" $(rm -rf) (2020).mkv'
    shutil.copyfile(samples_dir / "files" / "sdr_2997.mkv", odd)
    result = run_tool("mkvmerge", ["-J", str(odd)])
    assert '"recognized": true' in result.stdout


@pytest.mark.parametrize("name", ["mkvmerge", "mkvextract", "mkvpropedit", "mediainfo"])
def test_mkvtoolnix_and_mediainfo_versions(name: str) -> None:
    tool = next(t for t in TOOLS if t.name == name)
    assert tool_version(tool) is not None


def test_parse_progress() -> None:
    from tailarr.media.tools import parse_progress

    assert parse_progress("#GUI#progress 42%") == 42
    assert parse_progress("#GUI#progress 100%\n") == 100
    assert parse_progress("Progress: 42%") is None
    assert parse_progress("#GUI#begin_scanning_playlists") is None


def test_run_tool_live_reports_mkvmerge_progress(samples_dir, tmp_path) -> None:
    from tailarr.media.tools import run_tool_live

    seen: list[int] = []
    result = run_tool_live(
        "mkvmerge",
        ["-o", str(tmp_path / "out.mkv"), str(samples_dir / "files" / "sdr_multi.mkv")],
        on_progress=seen.append,
    )
    assert result.returncode in (0, 1)
    assert seen and seen[-1] == 100
    assert "#GUI#progress" not in result.stdout  # progress lines aren't kept as output
    assert (tmp_path / "out.mkv").stat().st_size > 0


def test_run_tool_live_errors_and_cancel(tmp_path) -> None:
    import threading
    import time

    from tailarr.media.tools import ToolCancelled, run_tool_live

    with pytest.raises(ToolError) as err:
        run_tool_live("mkvmerge", ["-o", str(tmp_path / "x.mkv"), str(tmp_path / "missing.mkv")])
    assert "exit code 2" in err.value.message
    assert err.value.details  # mkvmerge's own explanation is kept

    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    begun = time.monotonic()
    with pytest.raises(ToolCancelled):
        run_tool_live("sleep", ["30"], cancel=cancel)
    assert time.monotonic() - begun < 5

    with pytest.raises(ToolError) as err:
        run_tool_live("sleep", ["30"], timeout=0.3)
    assert "took too long" in err.value.message
