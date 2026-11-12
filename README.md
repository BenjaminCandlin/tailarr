# Tailarr

Tailor your media to suit your players.

Tailarr is a self-hosted web app for Unraid that changes what's inside your MKV files
(tracks, default/forced flags, track names, Dolby Vision) **without ever re-encoding**.
It's a friendly front-end for MKVToolNix and dovi_tool, made to sit alongside Radarr,
Sonarr and Plex.

Version 1.0.

## What it does

- **Browse** your films and TV shows (show → season → episode) with posters, and see
  what's inside every file: video, audio and subtitle tracks in plain words ("Dolby
  TrueHD Atmos 7.1", "English, forced"), chapters, and HDR (Dolby Vision with its
  profile, HDR10, HDR10+, HLG).
- **Make a copy without Dolby Vision** (`Film - HDR10.mkv`), for TVs and players that
  show Dolby Vision with the wrong colours. Profile 5 is refused (it would show wrong
  colours).
- **Save a copy without some tracks** (`Film - Tailarr.mkv`): untick the audio or
  subtitle tracks you don't want.
- **Change track settings** (default / forced / names) in the file itself.
- **Replace the original with a copy**, with the original kept in a hidden recycle
  folder for 30 days.
- **Change a whole season or show at once**, choosing by language ("keep only English
  subtitles", "make Dolby Vision episodes into HDR10 copies").
- **Rules** that run by themselves for new films and episodes ("If a new film has
  Dolby Vision, make an HDR10 copy"), with a preview first.
- **Radarr, Sonarr and Plex**: proper titles and posters, Plex shows new copies
  straight away, and Tailarr's copies follow Radarr/Sonarr upgrades and renames.

## Safety

- Nothing is ever re-encoded: only MKVToolNix and dovi_tool are used.
- Original files are never changed without you confirming a summary first (a red
  button says exactly which file). Rules only change originals if you switch on
  "Allowed to change original files" for that rule (off by default), and never replace
  an original with a copy.
- New files are written under a hidden temporary name, checked, then renamed into
  place. A failed or cancelled job leaves nothing behind.
- Free disk space is checked before every job.
- Files still seeding in your download client (hardlinked) are never changed in place
  unless you tick "I understand".
- Tailarr only touches files inside the Films and TV folders you choose, never your
  downloads.

## Install on Unraid

1. **Make the image public (one time only).** The repository is private, so after the
   first image is published go to GitHub → your profile → **Packages** → `tailarr` →
   **Package settings** → *Danger Zone* → **Change visibility** → **Public**.
2. **Copy the template.** Download `unraid/tailarr.xml` from this repository and copy it
   to your Unraid flash drive as
   `config/plugins/dockerMan/templates-user/my-tailarr.xml`
   (over the network: `\\TOWER\flash\config\plugins\dockerMan\templates-user\`).
3. In Unraid go to **Docker → Add Container**, choose **tailarr** from the *Template*
   list, check the settings and click **Apply**:
   - **Data**: `/mnt/user/data` → `/data`, the same as in Radarr and Sonarr.
   - **Config**: `/mnt/user/appdata/tailarr`.
   - **PUID / PGID / UMASK**: leave as `99` / `100` / `002`.
   - Put Tailarr on the same custom Docker network as Radarr, Sonarr and Plex, so they
     can find each other by container name.
4. Open `http://<your-server>:8484` and go to **Settings**. Every line in the
   **System check** should have a green tick.

The image is `ghcr.io/benjamincandlin/tailarr:latest` and is rebuilt automatically every
time a change is merged. To update, use **Check for Updates** on Unraid's Docker page.

Optional: add a path `/work` (for example on a cache drive) for HDR10 copies' big
working files; otherwise they're made next to the film.

## First steps

1. **Settings → Library folders**: the Films and TV folders (`/data/media/movies` and
   `/data/media/tv` by default).
2. **Settings → Radarr, Sonarr and Plex** (optional): fill in `http://radarr:7878`,
   `http://sonarr:8989`, `http://plex:32400` with their API keys / token, press **Test**,
   then **Save connections**.
3. **Webhooks** (optional, needed for automatic rules and tidy copies): in Radarr and
   Sonarr, Settings → Connect → + → **Webhook**, paste the address shown in Tailarr's
   Settings, tick *On File Import*, *On File Upgrade*, *On Rename* and the
   *On … File Delete* options.
4. **Films**: open a film to see its tracks, change them, or make copies. You always see
   a summary first.
5. **Rules**: start from one of the examples, press **Preview this rule**, save it, and
   switch it on when you're happy.

## How things work

- **Copies** sit next to the original (`Film (2020).mkv` and
  `Film (2020) - HDR10.mkv`), so Plex shows one film with two versions. Radarr and Sonarr
  ignore them.
- When Radarr/Sonarr **upgrade** a film or episode, Tailarr moves its copies of the old
  file to the recycle folder, and rules make fresh ones from the new file. When they
  **rename** one, the copies are renamed to match.
- **Queue**: one job runs at a time, with progress, cancel, and plain-English errors
  ("Show technical details" for the tools' own words). Jobs started together (a season,
  a rule) are shown as one group. Finished jobs are cleared after 30 days.
- **Activity log** (Rules → Activity log): everything rules did, and what Radarr, Sonarr
  and Plex were told.
- **Recycle folder**: replaced originals and stale copies wait in a hidden
  `.tailarr-recycle` folder inside their own folder for 30 days (Settings → Recycle
  folder), then are deleted.

## Login

Off by default. **Settings → Login** asks for a username and password. If you forget the
password, add the variable `TAILARR_DISABLE_LOGIN` = `1` to the container (Unraid: edit
the container → *Add another Path, Port, Variable…*), start it once, then remove the
variable again.

Tailarr always refuses changes that don't come from its own page, so other websites
can't make your browser change your files. Radarr/Sonarr webhooks use a secret instead.

## Troubleshooting

- **"Tailarr can't find radarr"**: put Tailarr on the same custom Docker network as
  Radarr, or use the server's IP address.
- **Plex doesn't show changes**: Settings → "Recently" says whether Plex was asked. If
  Plex sees your files under another path (for example `/media/movies`), add a **path
  mapping** (Settings → Library folders) and use **Test a path**.
- **A job failed**: open the Queue, read the message, and press "Show technical details"
  for the tools' own words.

## For developers

See `CLAUDE.md` (plan, rules, how to run the tests), `PROGRESS.md` and `DECISIONS.md`.

```bash
cd backend && uv sync && uv run pytest
cd frontend && npm ci && npm run lint && npm test && npm run build
cd e2e && npm ci && npx playwright test
```
