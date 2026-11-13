# Contributing to Tailarr

Thanks for helping! Bug reports, ideas and pull requests are all welcome.

## Reporting a problem

Open an issue with what you did, what you expected, and what happened. If a job failed,
include the text from **Show technical details** in the Queue. Please leave out API keys,
your server's address and anything else private.

## How the project is built

`CLAUDE.md` describes the whole project: what Tailarr is, the technology choices, the
look and feel, and how Radarr, Sonarr and Plex are handled. Read its **safety rules**
(section 2) before changing anything. In short, every change must keep these:

- Never re-encode: only MKVToolNix and dovi_tool, no ffmpeg encoding in the app.
- Never change or delete an original file without a confirmed summary (or a rule that is
  explicitly allowed to).
- Write new files under a hidden temporary name, verify them, then rename into place.
- Check free space first; respect PUID/PGID/UMASK; warn before changing hardlinked files.
- Only touch files inside the configured Films and TV folders.
- No secrets in the repository.

The web page is written for people who don't code: plain English, no command options,
a summary before every change.

## Running the tests

You need Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node.js 22, and MKVToolNix,
MediaInfo, ffmpeg and [dovi_tool](https://github.com/quietvoid/dovi_tool) (the tests make
tiny sample MKV files with real tools).

```bash
cd backend && uv sync && uv run pytest
```

```bash
cd frontend && npm ci && npm run lint && npm test && npm run build
```

```bash
cd e2e && npm ci && npx playwright test
```

The browser tests take screenshots at desktop and phone sizes, in dark and light themes,
in `e2e/screenshots/`. Please add tests for anything you change, and include screenshots
in pull requests that change the page.

## Pull requests

- One topic per pull request, with tests.
- Explain what changed and how to check it, in plain English.
- Python: type hints, `ruff check` and `ruff format`. TypeScript: strict, ESLint and
  Prettier (`npm run lint`).
