# CLAUDE.md — Tailarr

> Read this file at the start of **every** session before doing anything else.
> The owner's working notes, `PROGRESS.md` and `DECISIONS.md`, are the project's
> memory. They live in the **private** repository `BenjaminCandlin/tailarr-notes`
> (this repository is public). If the session has that repository, read both too;
> if not, ask for it to be added (or add it with the session's repository tools).
> Never copy their contents into this public repository.

## 1. What Tailarr is

Tailarr is a self-hosted web app that runs as a Docker container on an
Unraid server next to Radarr, Sonarr and Plex. It is a friendly web front-end
for **MKVToolNix** (plus **dovi_tool**) that changes what is *inside* MKV
files — tracks, flags, names, Dolby Vision metadata — **without ever
re-encoding** video or audio.

Owner: a non-technical user who checks in about once a day. Every screen,
message, summary and pull request must be understandable without coding
knowledge.

### Library layout (TRaSH Guides style)

The owner's Unraid server follows the TRaSH Guides layout: **one `/data`
share** holding downloads and media, with downloads **hardlinked** into the
media folders. Tailarr mounts `/data` **exactly the way Radarr and Sonarr
do** (host `/mnt/user/data` → container `/data`), so file paths in
Radarr/Sonarr webhooks are the same paths Tailarr sees.

| Container path        | Contents                                         |
|-----------------------|--------------------------------------------------|
| `/data`               | The whole data share (same mount as Radarr/Sonarr) |
| `/data/media/movies`  | Films — default **Films folder** setting (one folder per film) |
| `/data/media/tv`      | TV — default **TV folder** setting (`Show/Season NN/episode.mkv`) |
| `/config`             | Tailarr's database, settings, logs               |
| `/work`               | Optional scratch space for big temp files        |

- The Films and TV folders are **settings** (defaults above; can also be
  pre-set with the `TAILARR_MOVIES_DIR` / `TAILARR_TV_DIR` environment
  variables). Tailarr only ever browses or changes files inside these two
  folders — never the downloads folders elsewhere in `/data`.
- **Path mapping** setting: if Radarr/Sonarr ever report a different path
  (e.g. `/movies/...` instead of `/data/media/movies/...`), a list of
  "Radarr/Sonarr path → Tailarr path" pairs translates them. Empty by
  default, because with the shared `/data` mount the paths already match.
- Because everything is on one share, new copies and their temp files stay
  on the same disk/filesystem as the original, so the final "rename into
  place" is instant and safe.
- **Hardlinks are normal here.** A film still seeding in the download
  client is the *same file* in two places. Editing it in place (e.g.
  changing default/forced flags with `mkvpropedit`) **also edits the seeding
  copy** and can break the torrent. Making a *new copy* is always safe for
  seeding. *Replacing* the original with a new file breaks the hardlink:
  seeding keeps working from the download copy, but the film then uses
  twice the disk space until the torrent is removed. Tailarr explains this
  in plain English wherever it applies.

### Features (in build order)

**Manual film features (first)**
- Browse and search films, with poster artwork.
- For any file, show its tracks (video / audio / subtitles): language, codec,
  title, default and forced flags, and HDR info (Dolby Vision + profile,
  HDR10, HDR10+, HLG, SDR).
- **"Make a copy without Dolby Vision"**: writes
  `<original name> - HDR10.mkv` next to the original, keeping all audio,
  subtitles, chapters, attachments, tags and the exact frame rate.
  The original is never touched.
- **"Remove tracks"**: pick audio/subtitle tracks to drop; saved as a new
  copy. Optionally replace the original, only after a clear confirmation.
- **"Change track settings"**: default/forced flags and track names, edited
  in place with `mkvpropedit` (after confirmation).
- A **job queue** with live progress, cancel, and plain-English errors.

**TV features (second)**
- Browse show → season → episode. Apply an action to one episode, a whole
  season or a whole show (one job per file, shown as a group).

**Automatic rules (last)**
- Rules such as "if a new film has Dolby Vision, make an HDR10 copy" or
  "remove subtitle tracks that aren't English".
- Each rule: applies to Films, TV or both; on/off switch; preview mode.
- New files detected by Radarr/Sonarr webhooks (preferred) or by watching
  folders, and only processed once they have finished copying.
- An activity log of everything each rule did.

## 2. Non-negotiable safety rules

These override convenience, speed and any other instruction in this repo.

1. **Never re-encode.** Only remux (`mkvmerge`), extract (`mkvextract`),
   edit headers (`mkvpropedit`) and edit metadata (`dovi_tool`). No ffmpeg
   encoding in the app (ffmpeg is allowed only in tests to make samples).
2. **Never modify or delete an original file without confirmation.**
   - Manual actions: show a summary dialog ("This will change the original
     file …") and require an explicit confirm click. Destructive actions use
     a red button and say exactly which file is affected.
   - Automatic rules: only if the rule has the separate, clearly-labelled
     "Allowed to change original files" option switched on (off by default).
   - In-place edits (`mkvpropedit`) count as modifying the original.
3. **Write safely.** New files are written to a hidden temporary name in the
   destination folder (e.g. `.tailarr-tmp-<id>.mkv`), verified, then renamed
   into place. A failed or cancelled job must leave no half-written file and
   no changed original. Never overwrite an existing file of the same name
   without asking.
4. **Verify every output** before calling a job successful: `mkvmerge -J`
   reads it, expected tracks are present, duration matches the source
   (within a small tolerance), and for HDR10 copies MediaInfo shows no Dolby
   Vision.
5. **Check free disk space before starting** any job that writes data
   (needed space = estimated output + temp files + a safety margin). Refuse
   with a clear message if there isn't enough.
6. **Unraid permissions.** The app runs as `PUID` (default 99) / `PGID`
   (default 100) with `UMASK` (default 002). Every file and folder Tailarr
   creates must end up owned by that user/group with those permissions.
7. **Hardlinks.** With the TRaSH layout most new files are hardlinked to a
   seeding download. If a file has more than one hardlink, warn before any
   in-place edit: changing it in place also changes the seeding copy and can
   break the torrent. Default for in-place edits on hardlinked files: refuse
   unless the user ticks "I understand". Automatic rules never edit a
   hardlinked file in place unless the rule explicitly allows it.
8. **Dolby Vision safety.** Refuse "remove Dolby Vision" for profile 5 (it has
   no HDR10 base layer, so the picture would show wrong colours). Explain
   why in plain English.
9. **Paths stay inside the library.** Reject any path outside the
   configured Films and TV folders (and `/work` for temp files), after
   resolving `..` and symlinks. The rest of `/data` (downloads, torrents) is
   off limits even though it is mounted.
10. **No secrets in the repo.** API keys for Radarr/Sonarr/Plex live only in
    the database under `/config`.

## 3. Technology choices (and why)

The guiding principle: **as few moving parts as possible**, one container,
one process, no external services.

| Area | Choice | Why |
|------|--------|-----|
| Backend language | **Python 3.12** | Readable, excellent for running command-line tools (`subprocess`) and reading their JSON output. Easy to test. |
| Web framework | **FastAPI** + Uvicorn | Small, modern, automatic request validation and API docs; serves the built UI too, so it's one program. |
| Database | **SQLite** (via SQLModel) in `/config/tailarr.db` | A single file, nothing to install or run, easy to back up with Unraid's appdata backup. |
| Job queue | Built-in background worker in the same process, jobs stored in SQLite | No Redis/Celery to set up. Jobs survive restarts (interrupted jobs are marked "interrupted", temp files cleaned up). One job at a time by default — disks are the bottleneck. |
| MKV tools | `mkvmerge`, `mkvextract`, `mkvpropedit` (MKVToolNix official repo) | The standard tools, exactly what the owner already uses. `mkvmerge -J` gives track info as JSON; `--gui-mode` gives progress lines. |
| Dolby Vision | `dovi_tool` (pinned release binary) | The method the owner has proven: extract → `dovi_tool remove`/`demux` → remux. |
| HDR detection | `mediainfo` (JSON output) + `dovi_tool info` | MediaInfo reliably reports DV profile, HDR10, HDR10+ and HLG; `mkvmerge` alone does not. |
| Frontend | **React + TypeScript + Vite** | The most widely used modern UI stack: lots of ready-made, polished components; fast builds. Built into static files the backend serves. |
| Styling / components | **Tailwind CSS** + **shadcn/ui** (Radix) + **lucide** icons | Gives polished, accessible switches, checkboxes, dialogs, drawers and tables out of the box; dark/light theming via CSS variables; responsive (phone/PC) with simple class names. |
| Data fetching | TanStack Query | Handles loading states, caching and polling the queue for live progress with very little code. |
| Live progress | Polling every 1–2 s while jobs run | Simpler and more reliable behind Unraid reverse proxies than WebSockets. |
| Folder watching | `watchdog` with a periodic re-scan fallback | inotify isn't fully reliable on Unraid `/mnt/user` shares, so a timed scan backs it up. |
| Radarr/Sonarr/Plex APIs | `httpx` | Posters, path info, rescans, Plex refresh. |
| Tests | **pytest** (backend, using real MKVToolNix on generated sample files), **Vitest** + Testing Library (UI parts), **Playwright** (whole app in desktop *and* phone sizes, with screenshots) | Real tools on real (tiny) files catch real problems. |
| Container | Debian slim base, MKVToolNix + MediaInfo from apt, dovi_tool from GitHub release; small entrypoint script that applies PUID/PGID/UMASK | Familiar to Unraid users (same env vars as linuxserver.io images). |
| Publishing | GitHub Actions → GitHub Container Registry `ghcr.io/benjamincandlin/tailarr` | Free; builds and publishes automatically on every merge to `main`. See "Public image" below. |
| Unraid | Template XML in `unraid/tailarr.xml` | Downloaded once onto the Unraid flash drive (see `docs/INSTALL.md`); fields pre-filled. |

### Public repository, private notes

- The code, image (`ghcr.io/benjamincandlin/tailarr`, public package) and
  Unraid template are public, so anyone can install Tailarr and suggest
  improvements. The install guide is `docs/INSTALL.md`; contributors read
  `CONTRIBUTING.md`.
- The owner's progress notes and decisions (which include answers about their
  own server) are in the private `tailarr-notes` repository. Update them there,
  in a separate commit/pull request on that repository.
- Never commit personal details: real server addresses, API keys, the owner's
  email, or notes about their library. Use made-up examples.

Default web port: **8484** (configurable).

### Planned folder structure

```
backend/            Python app (FastAPI)
  tailarr/
    api/            HTTP endpoints
    core/           settings, paths, permissions, disk space
    media/          mkvmerge/mediainfo/dovi_tool wrappers, track model
    jobs/           queue, worker, job types
    library/        film & TV scanning, posters
    rules/          rule model, matching, preview, triggers (later)
  tests/
frontend/           React app
  src/components/   shared UI (TrackTable, ConfirmDialog, Badge, ...)
  src/pages/        Films, TV, Rules, Queue, Settings
  tests/
e2e/                Playwright tests + screenshots
tests/samples/      script that generates tiny sample MKVs (not committed)
docker/             Dockerfile helpers, entrypoint
unraid/             Unraid template
.github/workflows/  CI (tests) and image publishing
```

## 4. Look and feel (designed from Stage 1, not bolted on)

**Feel:** at home next to Radarr, Sonarr and Plex — dark, calm, poster-led.

- **Theme:** dark by default; Light and "Match my device" options in
  Settings. Colours defined once as CSS variables (shadcn theme tokens).
  Background near-black slate, cards one step lighter, one accent colour
  (**teal**, distinct from Radarr yellow, Sonarr blue and Plex orange) used
  for primary buttons and active items. Red only for destructive actions.
- **Layout:** left **sidebar** with icons + labels: Films, TV, Rules, Queue
  (with a running-jobs count badge), Settings. On phones the sidebar becomes
  a **bottom tab bar** (5 icons) so everything is one thumb-tap away.
- **Library pages:** poster grid (2 columns on phones, up to 6–8 on wide
  screens) with a search box and filters (e.g. "Has Dolby Vision"). Small
  badges on posters: `DV`, `HDR10`, `HDR10+`, `4K`. A list view toggle for
  dense browsing.
- **Detail page:** backdrop/poster header, file name and size, HDR badges,
  then **track tables** grouped Video / Audio / Subtitles. Each row: a
  "Keep" checkbox, language (full name, e.g. "English"), codec in friendly
  form ("Dolby TrueHD Atmos 7.1"), title, and **Default** / **Forced**
  toggles. On phones each track becomes a compact card with the same
  controls.
- **Actions** are big, plain-English buttons with a one-line explanation:
  - "Make a copy without Dolby Vision" — *For TVs/players that show
    Dolby Vision with the wrong colours. Your original stays as it is.*
  - "Save a copy without the unticked tracks"
  - "Save track changes" (flags/names)
- **Before any job:** a **summary sheet** (dialog on PC, slide-up drawer on
  phone) listing in plain words what will happen, which file(s) will be
  created or changed, space needed vs. free, and whether the original is
  touched. Confirm / Cancel.
- **Queue page:** each job shows title, step ("Extracting video… 2 of 4"),
  a progress bar, elapsed time and Cancel. Failed jobs show a plain-English
  error ("Not enough free space on the disk: needs 48 GB, 31 GB free") with
  a "Show technical details" expander for the raw tool output.
- **Language:** never show raw command options. Use "Dolby Vision", not
  "RPU"; "Forced subtitles (only shown for foreign-language parts)", etc.
  Short helper text under every option.
- **Accessibility:** keyboard usable, visible focus, sufficient contrast in
  both themes, touch targets ≥ 44px on phones.
- Every stage that adds UI must include Playwright screenshots at desktop
  (1440×900) and phone (iPhone-size) widths, in dark and light themes, and
  check there's no horizontal scrolling on phones.

## 5. How Radarr, Sonarr and Plex treat extra copies (planned approach)

- **Plex:** a second file in the same film folder
  (`Film (2020).mkv` + `Film (2020) - HDR10.mkv`) is shown as **one film with
  two versions** ("Play Version" menu). TV episodes keep the `S01E02` part in
  the name, so Plex also groups them as versions of the same episode. This
  is why copies go **next to the original by default**.
- **Radarr / Sonarr:** they track exactly one file per film/episode. An
  extra file in the folder is normally ignored, but:
  - When they **upgrade** a file they delete the old original, leaving our
    copy behind, now made from an older release.
  - When they **rename** files, our copy keeps its old name.
- **Safest approach (to build in Stages 8–10):**
  1. Tailarr records every copy it makes (source path, size, date) in its
     database and writes a small "made by Tailarr" tag inside the copy.
  2. Using Radarr/Sonarr webhooks (Upgrade, File Delete, Rename events),
     Tailarr removes stale copies of upgraded files (they are Tailarr's own
     files, not originals; setting, on by default) and, if a rule says so,
     makes a fresh copy from the new file. Renamed originals → copy renamed
     to match.
  3. After any change, Tailarr asks Radarr/Sonarr to rescan and Plex to
     refresh that item (optional, if connected).
  4. Setting to put copies in a separate folder instead (e.g. a
     `/data/media/movies-hdr10` folder used as a separate Plex library), for anyone who
     prefers Radarr/Sonarr never to see them.
  5. Tailarr's own folder watcher always ignores Tailarr's temp files and
     copies, so it never processes its own output in a loop.
- **To verify on the real server** (owner, in Stage 8): that Radarr/Sonarr
  don't try to import the `- HDR10` copy during a rescan.
- **Paths:** Tailarr mounts `/data` like Radarr/Sonarr, so webhook paths
  match directly. The path-mapping table (with a "test" button that checks
  the translated path exists) covers setups where they differ.
- **Upgrades and hardlinks:** when Radarr/Sonarr upgrade a film, the new
  file arrives hardlinked to its download. A rule that makes an HDR10 copy
  is unaffected (copies are separate files).

## 6. Build plan

Each stage is small, ends with something the owner can see and test, and
has automated tests. **One stage per session, done completely.**

### Stage 0 — Planning (done)
CLAUDE.md, empty PROGRESS.md and DECISIONS.md.

### Stage 1 — Foundations: app shell, design, Docker (done)
- Backend skeleton (FastAPI) serving the React app and a `/api/health`
  endpoint reporting versions of mkvmerge, mkvextract, mkvpropedit,
  mediainfo, dovi_tool, and whether the Films folder, TV folder and
  `/config` exist and are writable.
- Settings storage with the Films folder / TV folder settings (defaults
  `/data/media/movies` and `/data/media/tv`) and path checks that keep
  everything inside them.
- Frontend skeleton with the full design system: theme tokens, dark/light/
  system switch, sidebar + phone bottom bar, empty placeholder pages for
  Films / TV / Rules / Queue / Settings. Settings page shows the health info.
- Dockerfile with MKVToolNix, MediaInfo, dovi_tool; entrypoint applying
  PUID/PGID/UMASK.
- Sample-file generator (`tests/samples/make_samples.py`): tiny (2–3 s,
  low-resolution) MKVs: SDR H.264 with several audio/subtitle languages and
  forced subs; HEVC HDR10; HEVC HDR10+; Dolby Vision profile 8.1; profile 5;
  profile 7 (dual-track); 23.976, 25 and 29.97 fps; files with chapters and
  attachments; a fake TRaSH-style `/data` tree (`media/movies`, `media/tv`,
  `torrents/...`) including a hardlinked "seeding" file.
- GitHub Actions: run all tests on every PR; build and publish the image to
  GHCR on merge to `main`; Unraid template.
- **Owner checks:** make the image public (one-time step above), install on
  Unraid from the template, open the web page, see the sidebar, switch
  dark/light, open Settings and see green ticks for each tool and folder.
  Try it on a phone.

### Stage 2 — Film library
- Scan the Films folder (cached in SQLite, quick re-scan button), poster grid and
  list view, search, sort (title / date added / size).
- Posters from local artwork files in the film folder (`poster.jpg`,
  `folder.jpg`, …), otherwise a tasteful placeholder (Radarr posters come in
  Stage 8).
- **Owner checks:** Films page shows your films; search finds a title; works
  on phone.

### Stage 3 — Track viewer
- Film detail page: file info and HDR badges; track tables (Video / Audio /
  Subtitles) with friendly language and codec names; chapters count.
- HDR detection for DV (with profile), HDR10, HDR10+, HLG, SDR; HDR badges
  on library posters; "Has Dolby Vision" filter.
- **Owner checks:** open a few films you know; tracks and HDR info match
  what Plex / MKVToolNix show.

### Stage 4 — Job queue + change track settings
- Job engine: queue stored in SQLite, one worker, progress parsing, cancel,
  restart recovery, temp-file clean-up, plain-English errors with technical
  details, disk-space check, permissions on output.
- Queue page with live progress and history.
- First job type: **change default/forced flags and track names in place**
  (`mkvpropedit`), with summary + confirmation and the hardlink warning.
- **Owner checks:** change a default subtitle on one film, watch the job
  finish, confirm in Plex (after a refresh) that the default changed.

### Stage 5 — Remove tracks
- Untick tracks → "Save a copy without the unticked tracks" (new file named
  `<original> - Tailarr.mkv`; exact naming decided and logged then).
- After a successful copy: optional "Replace the original with this copy"
  with a strong confirmation; original moved to a Tailarr recycle folder
  (kept N days, configurable) rather than deleted outright.
- **Owner checks:** remove a foreign audio track from one film, play the
  copy, then try "replace original" on a test film.

### Stage 6 — Make a copy without Dolby Vision
- Steps: `mkvextract` video + timestamps → `dovi_tool remove` (profile 8)
  or `dovi_tool demux` base layer (profile 7) → `mkvmerge` with
  `--timestamps` and the correct `--default-duration`, all other tracks,
  chapters, attachments, tags, track names/languages/flags and colour
  metadata copied from the original. Refuse profile 5.
- Output `<original name> - HDR10.mkv`; verify no DV remains, HDR10
  metadata kept, frame rate/duration/track list match.
- Temp files in `/work` if mounted, otherwise in the destination folder.
- **Owner checks:** make an HDR10 copy of one DV film, play it on the device
  that had colour problems, check audio/subs/chapters are all there.

### Stage 7 — TV library and batch actions
- Show → season → episode browsing with posters; detail page reuses track
  viewer and all actions.
- Batch: apply an action to a season or whole show. Track choices are made
  by rule-like selections ("remove all non-English subtitles", "make DV
  episodes into HDR10 copies") because track numbers differ per episode.
  Summary lists every file affected; jobs grouped in the queue.
- **Owner checks:** HDR10 copies for one season; remove a subtitle language
  across a show.

### Stage 8 — Connections: Radarr, Sonarr, Plex
- Settings for URL + API key (with "Test" buttons), path-mapping editor.
- Posters/backdrops and proper titles from Radarr/Sonarr.
- After jobs: trigger Radarr/Sonarr rescan and Plex refresh (optional).
- Tracking of Tailarr-made copies; webhook endpoint (secret-protected) to
  handle upgrades, deletes and renames as described in section 5.
- **Owner checks:** connect your apps; posters appear; upgrade/rename tests
  from the checklist in that PR.

### Stage 9 — Rules and preview
- Rule builder in plain English: "When a new [Film / Episode / Either]
  is added, if [it has Dolby Vision / it has subtitles not in English / …],
  then [make an HDR10 copy / remove those tracks / set default …]".
- On/off switch, scope, "Allowed to change original files" (off by default).
- **Preview**: run a rule against the library (or chosen items) and see
  exactly what it would do, without changing anything. "Run now" button.
- **Owner checks:** create your two example rules, preview them, run one.

### Stage 10 — Automatic triggers and activity log
- Radarr/Sonarr "On Import/Upgrade" webhooks trigger rules for the new file.
- Optional folder watching with periodic re-scan fallback.
- "Finished copying" check: file size and modified time unchanged for a
  configurable time (default 60 s) and file readable by `mkvmerge -J`.
- Each file processed once per rule (remembered by path + size + date).
- Activity log page: every rule action, success/failure, links to jobs.
- **Owner checks:** add a film in Radarr; Tailarr makes the HDR10 copy by
  itself and the log shows it.

### Stage 11 — Polish and hardening
- Optional login (username/password), CSRF protection, webhook secret.
- Empty states, onboarding hints, help text review, accessibility pass,
  performance on large libraries (thousands of files).
- User README with install and usage guide; version 1.0 release tag.

## 7. Way of working (for every session)

1. **Start:** read `CLAUDE.md`, and `PROGRESS.md` / `DECISIONS.md` from the
   private `tailarr-notes` repository. Check that the
   previous stage's PR has been merged into `main`; start from latest `main`.
2. **Branch:** never commit to `main`. Use a branch named after the stage,
   e.g. `stage-3-track-viewer`. If the session environment assigns a
   specific branch name, use that one and put the stage name in the PR
   title.
3. **Scope:** do exactly one stage, completely. Don't start the next one.
4. **Decide independently.** Make sensible choices; record notable ones in
   `DECISIONS.md` in `tailarr-notes` (date, decision, why, alternatives). Only stop for
   something genuinely undecidable; collect all questions and put them at
   the end of the summary and PR description.
5. **Tests:** write automated tests for everything built (backend with real
   tools on generated sample files, UI with Vitest, flows with Playwright on
   desktop + phone). All tests must pass before finishing. Never skip or
   disable a test to get green.
6. **Update `PROGRESS.md`** in `tailarr-notes`: done, next, known issues.
7. **Pull request** with: what was built, how to check it (step-by-step in
   plain English), questions, and screenshots where there is UI.
8. **Finish** with a short plain-English summary for the owner: what you
   built, how to check it works, anything you need from them, what the next
   stage is.

### Running things (for developers)

```bash
# Backend tests (needs mkvtoolnix, mediainfo, ffmpeg and dovi_tool)
cd backend && uv sync && uv run pytest
# Frontend: lint, unit tests, build
cd frontend && npm ci && npm run lint && npm test && npm run build
# Browser tests on desktop + phone, with screenshots in e2e/screenshots/
cd e2e && npm ci && npx playwright test
# Sample files on their own
python3 tests/samples/make_samples.py /tmp/samples
# Image smoke test (after docker build -t tailarr .)
docker/smoke-test.sh tailarr
```

- CI sets `TAILARR_REQUIRE_ALL_TOOLS=1`, so a missing tool fails tests
  instead of skipping them.
- Dolby Vision / HDR10+ samples are made by inserting metadata into tiny
  x265 encodes (`tests/samples/make_samples.py`), using real dovi_tool RPU
  test files from `tests/samples/fixtures/`. There is also a true dual-layer
  profile 7 sample (BL+EL+RPU in one track, woven together with `dovi_tool mux`),
  so `dovi_tool` is needed to build the samples.
- Keep `DOVI_TOOL_VERSION` the same in `Dockerfile` and
  `.github/workflows/ci.yml`.

### Coding conventions
- Python: type hints, `ruff` for lint/format, `pytest`. All external tool
  calls go through one wrapper module (`media/tools.py`) that builds
  argument lists (never shell strings), captures output, parses progress
  and turns failures into friendly errors.
- TypeScript: strict mode, ESLint + Prettier. Shared components for anything
  used twice (ConfirmSummary, TrackTable, HdrBadge, ProgressBar).
- Plain-English UI text lives with components; technical details only behind
  "Show technical details".
- Keep the image small and the app light (it shares a home server).
