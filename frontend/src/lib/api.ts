/** Talking to the Tailarr backend. */

export type ToolStatus = {
  name: string;
  label: string;
  purpose: string;
  found: boolean;
  version: string | null;
  ok: boolean;
};

export type FolderStatus = {
  key: string;
  label: string;
  purpose: string;
  path: string;
  exists: boolean;
  writable: boolean;
  required: boolean;
  ok: boolean;
};

export type Health = {
  ok: boolean;
  version: string;
  tools: ToolStatus[];
  folders: FolderStatus[];
  running_as: { uid: number; gid: number; umask: string };
};

export type PathMapping = { remote: string; local: string };

export type LibrarySettings = {
  movies_dir: string;
  tv_dir: string;
  path_mappings: PathMapping[];
};

export type ScanStatus = {
  running: boolean;
  started_at: string | null;
  finished_at: string | null;
  film_count: number | null;
  error: string | null;
};

/** Headline facts about one file, for badges and filters. */
export type MediaSummary = {
  /** False: Tailarr hasn't read this file's details yet. */
  read: boolean;
  error: boolean;
  /** "Dolby Vision", "HDR10+", "HDR10", "HLG". Empty means a normal (SDR) picture. */
  hdr: string[];
  dv_profile: string | null;
  resolution: string | null;
};

export type ReadingStatus = { running: boolean; done: number; total: number };

export type Film = {
  id: number;
  title: string;
  year: number | null;
  folder_name: string;
  poster_url: string | null;
  size: number;
  added_at: string;
  file_count: number;
  main_file: string | null;
  is_mkv: boolean;
  media: MediaSummary;
};

export type FilmList = {
  root: string;
  films: Film[];
  scan: ScanStatus;
  reading: ReadingStatus;
};

export type FilmFile = {
  name: string;
  size: number;
  modified_at: string;
  is_mkv: boolean;
  is_copy: boolean;
  is_main: boolean;
  hardlinked: boolean;
  media: MediaSummary;
};

export type FilmDetail = Film & {
  folder: string;
  backdrop_url: string | null;
  tmdb_id: number | null;
  imdb_id: string | null;
  files: FilmFile[];
};

export type Hdr = {
  formats: string[];
  dv_profile: string | null;
  /** What players without Dolby Vision show: "HDR10", "SDR", "HLG", or null (wrong colours). */
  dv_fallback: string | null;
  dv_dual_layer: boolean;
  can_remove_dv: boolean;
};

export type TrackType = "video" | "audio" | "subtitles";

export type Track = {
  id: number;
  type: TrackType;
  codec: string;
  codec_id: string;
  language: string;
  language_name: string;
  name: string;
  default: boolean;
  forced: boolean;
  enabled: boolean;
  hearing_impaired: boolean;
  visual_impaired: boolean;
  commentary: boolean;
  original: boolean;
  width: number | null;
  height: number | null;
  resolution: string | null;
  frame_rate: string | null;
  bit_depth: number | null;
  hdr: Hdr | null;
  channels: number | null;
  channel_layout: string | null;
  sample_rate: number | null;
  picture_based: boolean | null;
};

export type Attachment = { name: string; mime_type: string; size: number };

export type Media = {
  file: string;
  size: number;
  read_at: string;
  error: string | null;
  error_details: string | null;
  container: string | null;
  title: string | null;
  duration: number | null;
  resolution: string | null;
  hdr: Hdr | null;
  hdr_checked: boolean;
  tracks: Track[];
  chapters: number;
  attachments: Attachment[];
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
  }
}

type ValidationItem = { msg?: string };

/** Turn a backend error into a sentence the owner can understand. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item: ValidationItem) => (item.msg ?? "").replace(/^Value error, /, ""))
        .filter(Boolean)
        .join(" ");
    }
  } catch {
    // fall through
  }
  return `Something went wrong (error ${response.status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("Couldn't reach Tailarr. Is the container running?");
  }
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  librarySettings: () => request<LibrarySettings>("/api/settings/library"),
  saveLibrarySettings: (settings: LibrarySettings) =>
    request<LibrarySettings>("/api/settings/library", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  films: () => request<FilmList>("/api/films"),
  film: (id: number | string) => request<FilmDetail>(`/api/films/${id}`),
  filmMedia: (id: number | string, file: string, refresh = false) =>
    request<Media>(
      `/api/films/${id}/media?${new URLSearchParams({ file, ...(refresh ? { refresh: "true" } : {}) })}`,
    ),
  rescanFilms: () => request<ScanStatus>("/api/films/scan", { method: "POST" }),
};
