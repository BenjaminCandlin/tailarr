"""Finding the shows, seasons and episodes in the TV folder.

Like the film scan, this only lists folders and reads file sizes/dates; it never
opens the video files. The layout Sonarr uses is expected:

    TV folder / Show (Year) / Season 01 / Show (Year) - S01E01 - Title.mkv

Video files directly in a show's folder count too (their season comes from the
file name). Copies Tailarr made ("… - HDR10.mkv", "… - Tailarr.mkv") are kept
with the episode they were made from.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, col, delete, select

from ..core.paths import is_inside
from .artwork import find_backdrop, find_poster
from .models import Episode, EpisodeFile, Show
from .naming import TEMP_PREFIX, is_video, sort_key
from .scanner import FoundFile, LibraryFolderMissingError, LibraryScanner, _stat_file
from .tv_naming import parse_episode, parse_show_folder, season_of_folder, strip_copy_suffix

log = logging.getLogger(__name__)

TV_SCAN_STATUS_KEY = "tv_scan"
_SKIP_FOLDERS = {"@eadir", "#recycle", "lost+found", "$recycle.bin", "system volume information"}
# Sub-folders of a show that hold extras, not episodes.
_EXTRA_FOLDERS = {"extras", "featurettes", "behind the scenes", "deleted scenes", "trailers"}


@dataclass
class FoundEpisode:
    key: str
    folder: str
    season: int | None
    episode: int | None
    episode_end: int | None
    title: str
    files: list[FoundFile] = field(default_factory=list)

    @property
    def main_file(self) -> FoundFile:
        originals = [f for f in self.files if not f.is_copy] or self.files
        return max(originals, key=lambda f: (f.is_mkv, f.size))


@dataclass
class FoundShow:
    folder: str
    folder_name: str
    episodes: list[FoundEpisode]
    poster: tuple[str, float] | None
    backdrop: tuple[str, float] | None


def _videos(folder: Path, root: Path) -> tuple[list[FoundFile], list[os.DirEntry[str]]]:
    """The video files in one folder, and its sub-folders."""
    files: list[FoundFile] = []
    folders: list[os.DirEntry[str]] = []
    try:
        entries = list(os.scandir(folder))
    except OSError as error:
        log.warning("Couldn't read %s: %s", folder, error)
        return files, folders
    for entry in entries:
        if entry.name.startswith(".") or entry.name.casefold() in _SKIP_FOLDERS:
            continue
        try:
            if entry.is_dir():
                if is_inside(entry.path, root):
                    folders.append(entry)
                continue
        except OSError:
            continue
        if not is_video(entry.name) or entry.name.startswith(TEMP_PREFIX):
            continue
        if not is_inside(entry.path, root):
            continue
        stat = _stat_file(entry)
        if stat is not None:
            files.append(
                FoundFile(entry.name, entry.path, stat.st_size, stat.st_mtime, stat.st_nlink)
            )
    return files, folders


def _group(files: list[FoundFile], folder: Path, folder_season: int | None) -> list[FoundEpisode]:
    episodes: dict[str, FoundEpisode] = {}
    # Originals first, so a copy joins its original's episode.
    for f in sorted(files, key=lambda f: (f.is_copy, f.name.casefold())):
        base = strip_copy_suffix(Path(f.name).stem)
        key = f"{folder}/{base}"
        episode = episodes.get(key)
        if episode is None:
            parsed = parse_episode(f.name, folder_season)
            season = parsed.season if parsed.season is not None else folder_season
            episode = episodes[key] = FoundEpisode(
                key=key,
                folder=str(folder),
                season=season,
                episode=parsed.episode,
                episode_end=parsed.episode_end,
                title=parsed.title,
            )
        episode.files.append(f)
    return list(episodes.values())


def _scan_show(folder: Path, root: Path) -> FoundShow | None:
    files, subfolders = _videos(folder, root)
    episodes = _group(files, folder, None)
    for sub in subfolders:
        season = season_of_folder(sub.name)
        if season is None and sub.name.casefold() in _EXTRA_FOLDERS:
            continue
        if season is None:
            continue  # not a season folder (extras, artwork, …)
        season_files, _ = _videos(Path(sub.path), root)
        episodes += _group(season_files, Path(sub.path), season)
    if not episodes:
        return None
    try:
        names = [e.name for e in os.scandir(folder)]
    except OSError:
        names = []

    def art(name: str | None) -> tuple[str, float] | None:
        if name is None:
            return None
        path = folder / name
        if not is_inside(path, root):
            return None
        try:
            return str(path), path.stat().st_mtime
        except OSError:
            return None

    return FoundShow(
        folder=str(folder),
        folder_name=folder.name,
        episodes=episodes,
        poster=art(find_poster(names, None)),
        backdrop=art(find_backdrop(names, None)),
    )


def find_shows(root: Path) -> list[FoundShow]:
    if not root.is_dir():
        raise LibraryFolderMissingError(
            f"Tailarr can't find your TV folder at {root}. Check the TV folder in Settings, "
            "and that the /data share is added to the container."
        )
    shows: list[FoundShow] = []
    for entry in os.scandir(root):
        if entry.name.startswith(".") or entry.name.casefold() in _SKIP_FOLDERS:
            continue
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue
        if not is_inside(entry.path, root):
            continue
        found = _scan_show(Path(entry.path), root)
        if found:
            shows.append(found)
    return shows


def _save_show(session: Session, item: FoundShow, show: Show | None) -> Show:
    title, year, tvdb, tmdb, imdb = parse_show_folder(item.folder_name)
    show = show or Show(folder=item.folder, folder_name="", title="", sort_title="")
    show.folder_name = item.folder_name
    show.title = title
    show.sort_title = sort_key(title)
    show.year = year
    show.tvdb_id, show.tmdb_id, show.imdb_id = tvdb, tmdb, imdb
    show.poster_path, show.poster_mtime = item.poster or (None, None)
    show.backdrop_path, show.backdrop_mtime = item.backdrop or (None, None)
    show.size = sum(f.size for e in item.episodes for f in e.files)
    show.added_at = max(f.mtime for e in item.episodes for f in e.files)
    show.season_count = len({e.season for e in item.episodes if e.season})
    show.episode_count = len(item.episodes)
    session.add(show)
    session.flush()

    existing = {
        e.key: e for e in session.exec(select(Episode).where(Episode.show_id == show.id)).all()
    }
    session.exec(delete(EpisodeFile).where(col(EpisodeFile.show_id) == show.id))  # type: ignore[arg-type]
    seen: set[str] = set()
    for found in item.episodes:
        seen.add(found.key)
        episode = existing.get(found.key) or Episode(show_id=show.id, key=found.key, folder="")  # type: ignore[arg-type]
        main = found.main_file
        episode.folder = found.folder
        episode.season, episode.episode = found.season, found.episode
        episode.episode_end, episode.title = found.episode_end, found.title
        episode.main_file = main.name
        episode.size = sum(f.size for f in found.files)
        episode.added_at = main.mtime
        episode.file_count = len(found.files)
        session.add(episode)
        session.flush()
        for f in sorted(found.files, key=lambda f: (f.is_copy, f.name.casefold())):
            session.add(
                EpisodeFile(
                    episode_id=episode.id,  # type: ignore[arg-type]
                    show_id=show.id,  # type: ignore[arg-type]
                    name=f.name,
                    path=f.path,
                    size=f.size,
                    mtime=f.mtime,
                    is_mkv=f.is_mkv,
                    is_copy=f.is_copy,
                    links=f.links,
                )
            )
    for key, episode in existing.items():
        if key not in seen:
            session.delete(episode)
    return show


def _delete_show(session: Session, show: Show) -> None:
    session.exec(delete(EpisodeFile).where(col(EpisodeFile.show_id) == show.id))  # type: ignore[arg-type]
    session.exec(delete(Episode).where(col(Episode.show_id) == show.id))  # type: ignore[arg-type]
    session.delete(show)


def save_shows(session: Session, found: list[FoundShow]) -> int:
    existing = {show.folder: show for show in session.exec(select(Show)).all()}
    seen: set[str] = set()
    for item in found:
        seen.add(item.folder)
        _save_show(session, item, existing.get(item.folder))
    for folder, show in existing.items():
        if folder not in seen:
            _delete_show(session, show)
    session.commit()
    return len(found)


def show_folder_of(path: str, root: Path) -> Path | None:
    """The show folder (first level below the TV folder) holding `path`."""
    if not is_inside(path, root):
        return None
    real_root = Path(os.path.realpath(root))
    relative = Path(os.path.realpath(path)).relative_to(real_root)
    if not relative.parts:
        return None
    return Path(root) / relative.parts[0]


def rescan_show_folder(session: Session, folder: str, root: Path) -> Show | None:
    """Update one show after Tailarr added, replaced or removed a file in it."""
    show_folder = show_folder_of(folder, root)
    if show_folder is None:
        return None
    existing = session.exec(select(Show).where(Show.folder == str(show_folder))).first()
    found = _scan_show(show_folder, root)
    if found is None:
        if existing is not None:
            _delete_show(session, existing)
            session.commit()
        return None
    show = _save_show(session, found, existing)
    session.commit()
    session.refresh(show)
    return show


class TvScanner(LibraryScanner):
    status_key = TV_SCAN_STATUS_KEY
    label = "tv"
    missing_message = "Tailarr couldn't read your TV folder ({error})."

    def find_and_save(self, session: Session, root: Path) -> int:
        return save_shows(session, find_shows(root))
