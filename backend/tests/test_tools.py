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
