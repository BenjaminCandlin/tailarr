import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import { AppRoutes, makeQueryClient } from "@/App";
import type {
  Episode,
  EpisodeDetail,
  Job,
  Film,
  FilmDetail,
  FilmList,
  Health,
  LibrarySettings,
  Media,
  MediaSummary,
  ShowDetail,
  ShowList,
  Track,
} from "@/lib/api";
import { ThemeProvider } from "@/lib/theme";

export const HEALTH: Health = {
  ok: false,
  version: "0.1.0",
  tools: [
    {
      name: "mkvmerge",
      label: "MKVToolNix – mkvmerge",
      purpose: "Reads files",
      found: true,
      version: "82.0",
      ok: true,
    },
    {
      name: "dovi_tool",
      label: "dovi_tool",
      purpose: "Removes Dolby Vision information",
      found: false,
      version: null,
      ok: false,
    },
  ],
  folders: [
    {
      key: "movies",
      label: "Films folder",
      purpose: "Where your films are",
      path: "/data/media/movies",
      exists: true,
      writable: true,
      required: true,
      ok: true,
    },
    {
      key: "tv",
      label: "TV folder",
      purpose: "Where your TV shows are",
      path: "/data/media/tv",
      exists: false,
      writable: false,
      required: true,
      ok: false,
    },
    {
      key: "work",
      label: "Work folder (optional)",
      purpose: "Extra space",
      path: "/work",
      exists: false,
      writable: false,
      required: false,
      ok: true,
    },
  ],
  running_as: { uid: 99, gid: 100, umask: "002" },
};

export const LIBRARY: LibrarySettings = {
  movies_dir: "/data/media/movies",
  tv_dir: "/data/media/tv",
  path_mappings: [],
};

export function summary(extra: Partial<MediaSummary> = {}): MediaSummary {
  return { read: true, error: false, hdr: [], dv_profile: null, resolution: "1080p", ...extra };
}

const DV81 = summary({ hdr: ["Dolby Vision", "HDR10"], dv_profile: "8.1", resolution: "4K" });

function film(id: number, title: string, year: number | null, extra: Partial<Film> = {}): Film {
  return {
    id,
    title,
    year,
    folder_name: year ? `${title} (${year})` : title,
    poster_url: null,
    size: 1024 ** 3 * id,
    added_at: `2026-0${id}-01T12:00:00Z`,
    file_count: 1,
    main_file: `${title}.mkv`,
    is_mkv: true,
    media: summary(),
    ...extra,
  };
}

export const FILMS: FilmList = {
  root: "/data/media/movies",
  films: [
    film(3, "Ärger im Paradies", 2020, {
      media: summary({ hdr: ["HDR10+", "HDR10"], resolution: "4K" }),
    }),
    film(1, "Bright Lights", 2019, {
      poster_url: "/api/films/1/poster?v=1",
      media: summary({ hdr: ["HDR10"], resolution: "4K" }),
    }),
    film(5, "Colour Test", 2023, { file_count: 2, media: DV81 }),
    film(2, "The Long Weekend", 1999, { folder_name: "The Long Weekend (1999) {tmdb-10001}" }),
    film(4, "Old Home Video", 1995, {
      is_mkv: false,
      main_file: "Old Home Video.mp4",
      media: summary({ read: false, resolution: null }),
    }),
  ],
  reading: { running: false, done: 0, total: 0 },
  scan: {
    running: false,
    started_at: "2026-11-09T10:00:00Z",
    finished_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    film_count: 5,
    error: null,
  },
};

export const FILM_DETAIL: FilmDetail = {
  ...FILMS.films[2],
  folder: "/data/media/movies/Colour Test (2023)",
  backdrop_url: null,
  tmdb_id: null,
  imdb_id: null,
  files: [
    {
      name: "Colour Test (2023) WEBDL-2160p DV HDR10.mkv",
      size: 4 * 1024 ** 3,
      modified_at: "2026-05-01T12:00:00Z",
      is_mkv: true,
      is_copy: false,
      is_main: true,
      hardlinked: true,
      media: DV81,
      copy_of: null,
      can_replace_original: false,
    },
    {
      name: "Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10.mkv",
      size: 1024 ** 3,
      modified_at: "2026-05-02T12:00:00Z",
      is_mkv: true,
      is_copy: true,
      is_main: false,
      hardlinked: false,
      media: summary({ hdr: ["HDR10"], resolution: "4K" }),
      copy_of: null,
      can_replace_original: false,
    },
  ],
};

export function track(id: number, extra: Partial<Track>): Track {
  return {
    id,
    uid: String(9000 + id),
    type: "audio",
    codec: "AAC",
    codec_id: "A_AAC",
    language: "eng",
    language_name: "English",
    name: "",
    default: false,
    forced: false,
    enabled: true,
    hearing_impaired: false,
    visual_impaired: false,
    commentary: false,
    original: false,
    width: null,
    height: null,
    resolution: null,
    frame_rate: null,
    bit_depth: null,
    hdr: null,
    channels: null,
    channel_layout: null,
    sample_rate: null,
    picture_based: null,
    ...extra,
  };
}

const DV81_HDR = {
  formats: ["Dolby Vision", "HDR10"],
  dv_profile: "8.1",
  dv_fallback: "HDR10",
  dv_dual_layer: false,
  can_remove_dv: true,
};

export const MEDIA: Media = {
  file: "Colour Test (2023) WEBDL-2160p DV HDR10.mkv",
  size: 4 * 1024 ** 3,
  read_at: "2026-11-10T10:00:00Z",
  error: null,
  error_details: null,
  container: "Matroska",
  title: "",
  duration: 8040,
  resolution: "4K",
  hdr: DV81_HDR,
  hdr_checked: true,
  chapters: 12,
  attachments: [{ name: "cover.jpg", mime_type: "image/jpeg", size: 1000 }],
  tracks: [
    track(0, {
      type: "video",
      codec: "HEVC (H.265)",
      codec_id: "V_MPEGH/ISO/HEVC",
      language: "und",
      language_name: "Unknown language",
      width: 3840,
      height: 2160,
      resolution: "4K",
      frame_rate: "23.976",
      bit_depth: 10,
      hdr: DV81_HDR,
      default: true,
    }),
    track(1, {
      codec: "Dolby TrueHD Atmos",
      codec_id: "A_TRUEHD",
      channel_layout: "7.1",
      name: "TrueHD Atmos 7.1",
      default: true,
      original: true,
    }),
    track(2, {
      codec: "Dolby Digital",
      channel_layout: "5.1",
      language: "fre",
      language_name: "French",
      name: "Français",
    }),
    track(3, {
      type: "subtitles",
      codec: "PGS",
      picture_based: true,
      name: "English (Forced)",
      forced: true,
    }),
    track(4, {
      type: "subtitles",
      codec: "SRT",
      picture_based: false,
      name: "English SDH",
      hearing_impaired: true,
    }),
  ],
};

type Handler = (url: string, init?: RequestInit) => Response | undefined;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Fake backend: answers the standard endpoints, with optional overrides. */
export function mockBackend(handler?: Handler) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const custom = handler?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/api/health")) return json(HEALTH);
    if (url.endsWith("/api/settings/library")) return json(LIBRARY);
    if (url.endsWith("/api/settings/recycle"))
      return json({ keep_days: 30, file_count: 0, total_size: 0 });
    if (url.endsWith("/api/jobs/counts")) return json({ running: 0, queued: 0 });
    if (url.endsWith("/api/jobs"))
      return json({ jobs: [], counts: { running: 0, queued: 0 }, groups: [] });
    if (url.endsWith("/api/languages")) return json(LANGUAGES);
    if (url.endsWith("/api/films")) return json(FILMS);
    if (url.endsWith("/api/films/5")) return json(FILM_DETAIL);
    if (url.includes("/api/films/5/media")) {
      const file = new URL(url, "http://x").searchParams.get("file") ?? MEDIA.file;
      return json({ ...MEDIA, file });
    }
    return json({ detail: "Not found" }, 404);
  });
}

export function renderApp(path = "/films") {
  return render(
    <ThemeProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

export function job(extra: Partial<Job> = {}): Job {
  return {
    id: 42,
    kind: "track_settings",
    title: "Change track settings",
    subject: "Colour Test (2023)",
    file_name: MEDIA.file,
    film_id: 5,
    episode_id: null,
    group_id: null,
    status: "queued",
    step: "",
    step_number: 0,
    step_count: 0,
    progress: null,
    cancellable: true,
    cancel_requested: false,
    created_at: "2026-11-11T10:00:00Z",
    started_at: null,
    finished_at: null,
    message: null,
    error: null,
    error_details: null,
    result: null,
    ...extra,
  };
}

export const LANGUAGES = [
  { code: "eng", name: "English", common: true },
  { code: "fre", name: "French", common: true },
  { code: "spa", name: "Spanish", common: true },
  { code: "wel", name: "Welsh", common: false },
];

const READ_DV: MediaSummary = {
  read: true,
  error: false,
  hdr: ["Dolby Vision", "HDR10"],
  dv_profile: "8.1",
  resolution: "4K",
};
const READ_SDR: MediaSummary = {
  read: true,
  error: false,
  hdr: [],
  dv_profile: null,
  resolution: "1080p",
};

export const SHOWS: ShowList = {
  root: "/data/media/tv",
  scan: {
    running: false,
    started_at: "2026-11-11T10:00:00Z",
    finished_at: "2026-11-11T10:00:01Z",
    film_count: 2,
    error: null,
  },
  reading: { running: false, done: 0, total: 0 },
  shows: [
    {
      id: 2,
      title: "Another Show",
      year: 2022,
      folder_name: "Another Show (2022)",
      poster_url: null,
      size: 3_000_000_000,
      added_at: "2026-11-10T10:00:00Z",
      season_count: 1,
      episode_count: 3,
      media: { ...READ_DV, dv_profile: null },
      dv_episodes: 3,
    },
    {
      id: 1,
      title: "Test Show",
      year: null,
      folder_name: "Test Show",
      poster_url: null,
      size: 1_000_000_000,
      added_at: "2026-11-09T10:00:00Z",
      season_count: 2,
      episode_count: 4,
      media: READ_SDR,
      dv_episodes: 0,
    },
  ],
};

function episode(id: number, label: string, title: string, media = READ_DV): Episode {
  return {
    id,
    season: 1,
    episode: id,
    episode_end: null,
    label,
    title,
    main_file: `Another Show (2022) - ${label} - ${title}.mkv`,
    is_mkv: true,
    size: 1_000_000_000,
    added_at: "2026-11-10T10:00:00Z",
    file_count: 1,
    has_copy: false,
    media,
  };
}

export const SHOW_DETAIL: ShowDetail = {
  ...SHOWS.shows[0],
  folder: "/data/media/tv/Another Show (2022)",
  backdrop_url: null,
  tvdb_id: null,
  seasons: [
    {
      season: 1,
      label: "Season 1",
      size: 3_000_000_000,
      episodes: [
        { ...episode(11, "S01E01", "Start"), has_copy: true },
        episode(12, "S01E02", "Middle"),
        episode(13, "S01E03", "End"),
      ],
    },
  ],
};

export const EPISODE_DETAIL: EpisodeDetail = {
  ...episode(12, "S01E02", "Middle"),
  show_id: 2,
  show_title: "Another Show",
  show_year: 2022,
  poster_url: null,
  backdrop_url: null,
  folder: "/data/media/tv/Another Show (2022)/Season 01",
  files: [{ ...FILM_DETAIL.files[0], name: "Another Show (2022) - S01E02 - Middle.mkv" }],
};
