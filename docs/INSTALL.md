# Installing Tailarr

Tailarr runs as one Docker container. It's made for **Unraid** with the
[TRaSH Guides](https://trash-guides.info/File-and-Folder-Structure/) folder layout (one
`/data` share holding downloads and media), but works on any Docker host.

- [What you need](#what-you-need)
- [Install on Unraid](#install-on-unraid)
- [Install with Docker Compose (any server)](#install-with-docker-compose-any-server)
- [First steps](#first-steps)
- [Optional: a work folder for faster HDR10 copies](#optional-a-work-folder-for-faster-hdr10-copies)
- [Updating, and staying on one version](#updating-and-staying-on-one-version)
- [Settings you can give the container](#settings-you-can-give-the-container)
- [Removing Tailarr](#removing-tailarr)

## What you need

- Your films and TV shows as **MKV files**, in folders like Radarr and Sonarr make them:
  `movies/Film (2020)/Film (2020).mkv` and `tv/Show/Season 01/Show - S01E01.mkv`.
- Enough free space next to a film for one copy of it (Tailarr checks before every job).
- Optional: Radarr, Sonarr and Plex, for posters, tidy copies and automatic rules.

Everything Tailarr needs (MKVToolNix, MediaInfo, dovi_tool) is inside the image.

## Install on Unraid

1. **Get the template.** Open Unraid's terminal (the `>_` icon top right) and paste:

   ```bash
   wget -O /boot/config/plugins/dockerMan/templates-user/my-tailarr.xml https://raw.githubusercontent.com/BenjaminCandlin/tailarr/main/unraid/tailarr.xml
   ```

2. Go to **Docker → Add Container** and choose **tailarr** from the *Template* list.
3. Check the settings:
   - **Data**: `/mnt/user/data` → `/data`. Use **exactly the same mapping as Radarr and
     Sonarr**, so the file paths they report are the paths Tailarr sees.
   - **Config**: `/mnt/user/appdata/tailarr` (Tailarr's database and settings).
   - **Work folder (optional)**: leave empty for now (see below).
   - **PUID / PGID / UMASK** (under *Show more settings*): leave as `99` / `100` / `002`,
     Unraid's usual owner and permissions.
   - **Network**: if Radarr, Sonarr and Plex are on a custom Docker network, put Tailarr
     on the same one, so they can find each other by name (`http://radarr:7878`).
4. Click **Apply**, then open `http://<your-server>:8484`.
5. Go to **Settings**. Every line of the **System check** should have a green tick.

## Install with Docker Compose (any server)

```yaml
services:
  tailarr:
    image: ghcr.io/benjamincandlin/tailarr:latest
    container_name: tailarr
    ports:
      - "8484:8484"
    environment:
      - PUID=1000            # the user that should own new files
      - PGID=1000
      - UMASK=002
      # Optional, if your folders aren't /data/media/movies and /data/media/tv:
      # - TAILARR_MOVIES_DIR=/data/media/movies
      # - TAILARR_TV_DIR=/data/media/tv
    volumes:
      - /path/to/appdata/tailarr:/config
      - /path/to/data:/data   # the same mapping as Radarr and Sonarr
      # - /path/to/fast/ssd/tailarr-work:/work   # optional
    restart: unless-stopped
```

Then `docker compose up -d` and open `http://<your-server>:8484`.

## First steps

1. **Settings → Library folders**: check the Films and TV folders (`/data/media/movies`
   and `/data/media/tv` by default). Tailarr only ever looks at, or changes, files inside
   these two folders, never your downloads.
2. **Films**: your films appear (the first read of a big library takes a while, in the
   background). Open one to see its tracks.
3. **Settings → Radarr, Sonarr and Plex** (optional): fill in the address
   (`http://radarr:7878`, `http://sonarr:8989`, `http://plex:32400`) and the API key or
   Plex token, press **Test**, then **Save connections**. You get proper titles and
   posters, and Plex shows new copies straight away.
4. **Webhooks** (optional, needed for automatic rules and tidy copies): in Radarr and
   Sonarr go to Settings → Connect → **+** → **Webhook**, paste the address shown in
   Tailarr's Settings, and tick *On File Import*, *On File Upgrade*, *On Rename* and the
   *On … File Delete* options.
5. **Rules** (optional): start from an example ("If a new film has Dolby Vision, make an
   HDR10 copy"), press **Preview this rule** to see what it would do, save it, and switch
   it on when you're happy.

If paths differ between apps (for example Radarr sees `/movies/...`), add a **path
mapping** in Settings → Library folders and use **Test a path**.

## Optional: a work folder for faster HDR10 copies

Making a copy without Dolby Vision writes two big temporary files. On Unraid's array every
write also updates parity, which is slow. Point **Work folder (optional)** (container path
`/work`) at a folder on a fast SSD, for example `/mnt/cache/tailarr-work`, and only the
finished copy is written to the array. Settings → **Work folder** shows whether it's set
up. Tailarr empties it after every job.

## Updating, and staying on one version

`ghcr.io/benjamincandlin/tailarr:latest` is rebuilt every time a change is merged. On
Unraid, use **Check for Updates** on the Docker page; with Compose,
`docker compose pull && docker compose up -d`.

Every release also has its own image: `…/tailarr:1.0.0` (exactly that version) or
`…/tailarr:1.0` (that version plus small fixes). To stay on one, change the image (Unraid:
the **Repository** field) from `…/tailarr:latest` to `…/tailarr:1.0.0`.

## Settings you can give the container

| Variable | Default | What it does |
|---|---|---|
| `PUID` / `PGID` | `99` / `100` | User and group that own the files Tailarr creates. |
| `UMASK` | `002` | Permissions of new files (002: your other apps can change them). |
| `TAILARR_MOVIES_DIR` | `/data/media/movies` | Starting Films folder (can be changed in Settings). |
| `TAILARR_TV_DIR` | `/data/media/tv` | Starting TV folder (can be changed in Settings). |
| `TAILARR_PORT` | `8484` | The web page's port inside the container. |
| `TAILARR_TRUSTED_PROXIES` | empty | Your reverse proxy's address, if you use one with the login (see the README). |
| `TAILARR_DISABLE_LOGIN` | empty | Set to `1` for one start if you forgot the login password. |

## Removing Tailarr

Stop and remove the container, and delete its config folder (`/mnt/user/appdata/tailarr`).
Copies Tailarr made (`… - HDR10.mkv`, `… - Tailarr.mkv`) are ordinary MKV files and stay
where they are. Hidden `.tailarr-recycle` folders inside film folders hold replaced
originals: put back anything you want from Settings → Recycle folder first, or delete them.
