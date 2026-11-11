"""The one place where Tailarr runs outside programs (MKVToolNix, MediaInfo, dovi_tool).

Commands are always built as lists of arguments, never as shell strings, so
file names with spaces or odd characters can't cause problems.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolInfo:
    name: str
    label: str
    purpose: str
    version_args: tuple[str, ...]
    required: bool = True


TOOLS: tuple[ToolInfo, ...] = (
    ToolInfo(
        "mkvmerge", "MKVToolNix – mkvmerge", "Reads files and saves new copies", ("--version",)
    ),
    ToolInfo(
        "mkvextract",
        "MKVToolNix – mkvextract",
        "Takes the video out for Dolby Vision removal",
        ("--version",),
    ),
    ToolInfo(
        "mkvpropedit",
        "MKVToolNix – mkvpropedit",
        "Changes track settings without copying",
        ("--version",),
    ),
    ToolInfo("mediainfo", "MediaInfo", "Detects HDR10, HDR10+ and Dolby Vision", ("--version",)),
    ToolInfo("dovi_tool", "dovi_tool", "Removes Dolby Vision information", ("--version",)),
)

_VERSION_RE = re.compile(r"v?(\d+(?:\.\d+)+)")


class ToolError(RuntimeError):
    """A tool couldn't be run or reported an error.

    `message` is plain English for the owner; `details` holds the raw output for
    the "Show technical details" section.
    """

    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.details = details


@dataclass(frozen=True)
class ToolResult:
    returncode: int
    stdout: str
    stderr: str


def find_tool(name: str) -> str | None:
    return shutil.which(name)


def _tool_env() -> dict[str, str]:
    # The tools write track names and file names in the system language's character set.
    # Without a UTF-8 setting (the container default is plain "C") names such as
    # "Français" come out garbled, and mkvmerge's JSON can't even be read.
    env = dict(os.environ)
    env["LC_ALL"] = "C.UTF-8"
    env["LANG"] = "C.UTF-8"
    return env


def run_tool(name: str, args: list[str], timeout: float | None = 60) -> ToolResult:
    """Run a tool and return its output, raising ToolError with a friendly message."""
    path = find_tool(name)
    if path is None:
        raise ToolError(f"The program '{name}' isn't installed in the Tailarr container.")
    try:
        proc = subprocess.run(
            [path, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_tool_env(),
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"'{name}' took too long to respond and was stopped.", str(exc)) from exc
    except OSError as exc:
        raise ToolError(f"'{name}' couldn't be started.", str(exc)) from exc
    result = ToolResult(proc.returncode, proc.stdout, proc.stderr)
    # mkvmerge uses exit code 1 for "finished with warnings", which is a success.
    ok_codes = {0, 1} if name.startswith("mkv") else {0}
    if proc.returncode not in ok_codes:
        raise ToolError(
            f"'{name}' reported a problem (exit code {proc.returncode}).",
            (proc.stdout + "\n" + proc.stderr).strip(),
        )
    return result


def parse_version(output: str) -> str | None:
    match = _VERSION_RE.search(output)
    return match.group(1) if match else None


def tool_version(tool: ToolInfo) -> str | None:
    """Return the tool's version number, or None if it isn't available."""
    try:
        result = run_tool(tool.name, list(tool.version_args), timeout=15)
    except ToolError:
        return None
    return parse_version(result.stdout + "\n" + result.stderr)
