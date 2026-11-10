"""Poster and backdrop pictures saved in film folders, and small copies for the grid.

Radarr, Plex, Kodi and Emby/Jellyfin all save artwork next to the film with a
handful of well-known names (``poster.jpg``, ``folder.jpg``, ``fanart.jpg`` …).
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from ..core.permissions import apply_umask, dir_mode

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
POSTER_NAMES = ("poster", "folder", "cover", "default", "movie")
BACKDROP_NAMES = ("fanart", "backdrop", "background", "art")

THUMBNAIL_WIDTH = 480  # sharp on phones and in a 6-8 column grid on big screens


def _pick(files: dict[str, str], stems: list[str]) -> str | None:
    for stem in stems:
        for ext in IMAGE_EXTENSIONS:
            real = files.get(f"{stem}{ext}".casefold())
            if real:
                return real
    return None


def find_poster(file_names: list[str], main_file: str | None) -> str | None:
    """Return the poster file name in a folder listing, if there is one."""
    files = {name.casefold(): name for name in file_names}
    stems = list(POSTER_NAMES)
    if main_file:
        video_stem = Path(main_file).stem
        stems += [f"{video_stem}-poster", video_stem]
    return _pick(files, stems)


def find_backdrop(file_names: list[str], main_file: str | None) -> str | None:
    files = {name.casefold(): name for name in file_names}
    stems = list(BACKDROP_NAMES)
    if main_file:
        stems += [f"{Path(main_file).stem}-fanart"]
    return _pick(files, stems)


def thumbnail(source: Path, cache_dir: Path, width: int = THUMBNAIL_WIDTH) -> Path | None:
    """A smaller JPEG copy of a poster, made once and kept in the cache folder.

    Returns None if the picture can't be read (the page then shows a placeholder).
    """
    try:
        stat = source.stat()
    except OSError:
        return None
    key = hashlib.sha1(f"{source}|{stat.st_mtime_ns}|{stat.st_size}|{width}".encode()).hexdigest()
    target = cache_dir / key[:2] / f"{key}.jpg"
    if target.is_file():
        return target

    for folder in (cache_dir, target.parent):
        if not folder.is_dir():
            folder.mkdir(mode=dir_mode(), parents=True, exist_ok=True)
            apply_umask(folder)
    temp = target.with_name(f".tmp-{os.getpid()}-{target.name}")
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((width, width * 3))
            image.convert("RGB").save(temp, "JPEG", quality=82, optimize=True, progressive=True)
        apply_umask(temp)
        temp.replace(target)
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        log.warning("Couldn't make a small copy of %s: %s", source, error)
        with contextlib.suppress(OSError):
            temp.unlink()
        return None
    return target
