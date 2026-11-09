# Tailarr

Tailor your media to suit your players.

Tailarr is a self-hosted web app for Unraid that changes what's inside your
MKV files (tracks, default/forced flags, track names, Dolby Vision) without
ever re-encoding. It's a friendly front-end for MKVToolNix and dovi_tool,
made to sit alongside Radarr, Sonarr and Plex.

> **Status:** early development. The app shell, settings and system check
> work; library browsing and file changes are coming stage by stage (see
> `PROGRESS.md`).

## Install on Unraid

1. **Make the image public (one time only).** The repository is private, so
   after the first image is published go to GitHub → your profile →
   **Packages** → `tailarr` → **Package settings** → *Danger Zone* →
   **Change visibility** → **Public**.
2. **Copy the template.** Download `unraid/tailarr.xml` from this repository
   and copy it to your Unraid flash drive as
   `config/plugins/dockerMan/templates-user/my-tailarr.xml`
   (over the network: `\\TOWER\flash\config\plugins\dockerMan\templates-user\`).
3. In Unraid go to **Docker → Add Container**, choose **tailarr** from the
   *Template* list, check the settings and click **Apply**:
   - **Data**: `/mnt/user/data` → `/data`, the same as in Radarr and Sonarr.
   - **Config**: `/mnt/user/appdata/tailarr`.
   - **PUID / PGID / UMASK**: leave as `99` / `100` / `002`.
4. Open `http://<your-server>:8484` and go to **Settings**. Every line in the
   **System check** should have a green tick.

The image is `ghcr.io/benjamincandlin/tailarr:latest` and is rebuilt
automatically every time a change is merged.

## Safety

Tailarr never re-encodes, never changes or deletes an original file without
asking you first, checks free space before making copies, and writes files
with Unraid's permissions. See `CLAUDE.md` for the full rules.
