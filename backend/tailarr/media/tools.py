"""The one place where Tailarr runs outside programs (MKVToolNix, MediaInfo, dovi_tool).

Commands are always built as lists of arguments, never as shell strings, so
file names with spaces or odd characters can't cause problems.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
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


# --------------------------------------------------------------------------- long-running jobs


class ToolCancelled(ToolError):
    """The owner cancelled the job while the tool was running; the tool was stopped."""

    def __init__(self, name: str) -> None:
        super().__init__(f"'{name}' was stopped because the job was cancelled.")


_GUI_PROGRESS = re.compile(r"^#GUI#progress\s+(\d+)%")


def parse_progress(line: str) -> int | None:
    """The percentage in an MKVToolNix '--gui-mode' progress line, e.g. '#GUI#progress 42%'."""
    match = _GUI_PROGRESS.match(line.strip())
    return int(match.group(1)) if match else None


def run_tool_live(
    name: str,
    args: list[str],
    *,
    on_progress: Callable[[int], None] | None = None,
    cancel: threading.Event | None = None,
    timeout: float | None = None,
) -> ToolResult:
    """Run a long tool, reporting progress and stopping it if `cancel` is set.

    MKVToolNix tools are given '--gui-mode' so they print '#GUI#progress N%' lines.
    The tool's own words (stdout and stderr together) are kept for technical details.
    """
    path = find_tool(name)
    if path is None:
        raise ToolError(f"The program '{name}' isn't installed in the Tailarr container.")
    if name.startswith("mkv") and "--gui-mode" not in args:
        args = ["--gui-mode", *args]
    try:
        proc = subprocess.Popen(
            [path, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_tool_env(),
        )
    except OSError as exc:
        raise ToolError(f"'{name}' couldn't be started.", str(exc)) from exc

    stopped: list[str] = []
    finished = threading.Event()

    def watch() -> None:
        # Stop the tool if the job is cancelled or it runs for too long.
        deadline = None if timeout is None else time.monotonic() + timeout
        while not finished.wait(0.2):
            if cancel is not None and cancel.is_set():
                stopped.append("cancelled")
            elif deadline is not None and time.monotonic() > deadline:
                stopped.append("timeout")
            else:
                continue
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
            return

    watcher = threading.Thread(target=watch, name=f"watch-{name}", daemon=True)
    watcher.start()
    lines: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            percent = parse_progress(line)
            if percent is not None:
                if on_progress is not None:
                    on_progress(percent)
                continue
            lines.append(line.rstrip("\n"))
        proc.wait()
    finally:
        finished.set()
        watcher.join()
    output = "\n".join(lines[-200:])  # the end is where errors are
    if stopped and stopped[0] == "cancelled":
        raise ToolCancelled(name)
    if stopped:
        raise ToolError(f"'{name}' took too long and was stopped.", output)
    ok_codes = {0, 1} if name.startswith("mkv") else {0}
    if proc.returncode not in ok_codes:
        raise ToolError(f"'{name}' reported a problem (exit code {proc.returncode}).", output)
    return ToolResult(proc.returncode, output, "")
