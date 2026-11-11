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
  /** For copies Tailarr made: the file it was made from. */
  copy_of: string | null;
  /** The original is still there, unchanged, so it can be replaced with this copy. */
  can_replace_original: boolean;
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
  /** The track's unique ID inside the file; used when changing its settings. */
  uid: string;
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

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled" | "interrupted";

export type Job = {
  id: number;
  kind: string;
  title: string;
  subject: string;
  file_name: string;
  film_id: number | null;
  group_id: string | null;
  status: JobStatus;
  step: string;
  step_number: number;
  step_count: number;
  /** 0–100 for the current step, or null when there's no percentage. */
  progress: number | null;
  cancellable: boolean;
  cancel_requested: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
  error: string | null;
  error_details: string | null;
  /** Facts for the page, e.g. { copy: "Film - Tailarr.mkv" } for a new copy. */
  result: Record<string, string> | null;
};

export type JobCounts = { running: number; queued: number };

export type JobList = { jobs: Job[]; counts: JobCounts };

/** The settings wanted for one track; fields left out stay as they are. */
export type TrackChange = {
  uid: string;
  default?: boolean;
  forced?: boolean;
  /** An empty name removes the track's name. */
  name?: string;
};

export type TrackSettingsRequest = { file: string; changes: TrackChange[] };

export type TrackSettingsPreview = {
  film_id: number;
  file: string;
  path: string;
  tracks: { uid: string; label: string; changes: string[] }[];
  hardlinked: boolean;
  free_space: number;
};

export type RemoveTracksRequest = {
  file: string;
  /** Unique IDs of the tracks to leave out of the copy. */
  remove: string[];
  /** Settings for the kept tracks, applied to the copy. */
  changes: TrackChange[];
};

export type RemoveTracksPreview = {
  film_id: number;
  file: string;
  new_file: string;
  /** A Tailarr copy with the new name is already there. */
  exists: boolean;
  /** The file being copied is that Tailarr copy itself: it will be updated. */
  updates_copy: boolean;
  removed: string[];
  kept: string[];
  settings: { label: string; changes: string[] }[];
  warnings: string[];
  space_needed: number;
  free_space: number;
  enough_space: boolean;
};

export type ReplaceOriginalPreview = {
  film_id: number;
  original: string;
  original_size: number;
  copy_file: string;
  copy_size: number;
  hardlinked: boolean;
  keep_days: number;
  recycle_folder: string;
};

export type Hdr10CopyPreview = {
  film_id: number;
  file: string;
  new_file: string;
  /** A Tailarr copy with the new name is already there. */
  exists: boolean;
  dv_profile: string;
  /** UHD Blu-ray style profile 7: an extra picture layer that's left out too. */
  blu_ray_layers: boolean;
  /** What players show the copy as, e.g. ["HDR10"] or ["HDR10+", "HDR10"]. */
  result: string[];
  kept: string[];
  chapters: number;
  attachments: number;
  uses_work_folder: boolean;
  space: { label: string; needed: number; free: number; enough: boolean }[];
  enough_space: boolean;
};

export type RecycleSettings = { keep_days: number; file_count: number; total_size: number };

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
  previewTrackSettings: (id: number | string, body: TrackSettingsRequest) =>
    request<TrackSettingsPreview>(`/api/films/${id}/track-settings/preview`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  changeTrackSettings: (
    id: number | string,
    body: TrackSettingsRequest & { confirmed: true; allow_hardlinked: boolean },
  ) =>
    request<Job>(`/api/films/${id}/track-settings`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  previewRemoveTracks: (id: number | string, body: RemoveTracksRequest) =>
    request<RemoveTracksPreview>(`/api/films/${id}/remove-tracks/preview`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  removeTracks: (
    id: number | string,
    body: RemoveTracksRequest & { confirmed: true; overwrite: boolean },
  ) =>
    request<Job>(`/api/films/${id}/remove-tracks`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  previewReplaceOriginal: (id: number | string, copyFile: string) =>
    request<ReplaceOriginalPreview>(`/api/films/${id}/replace-original/preview`, {
      method: "POST",
      body: JSON.stringify({ copy_file: copyFile }),
    }),
  replaceOriginal: (id: number | string, copyFile: string) =>
    request<Job>(`/api/films/${id}/replace-original`, {
      method: "POST",
      body: JSON.stringify({ copy_file: copyFile, confirmed: true, understood: true }),
    }),
  previewHdr10Copy: (id: number | string, file: string) =>
    request<Hdr10CopyPreview>(`/api/films/${id}/hdr10-copy/preview`, {
      method: "POST",
      body: JSON.stringify({ file }),
    }),
  hdr10Copy: (id: number | string, file: string, overwrite: boolean) =>
    request<Job>(`/api/films/${id}/hdr10-copy`, {
      method: "POST",
      body: JSON.stringify({ file, confirmed: true, overwrite }),
    }),
  recycleSettings: () => request<RecycleSettings>("/api/settings/recycle"),
  saveRecycleSettings: (keepDays: number) =>
    request<RecycleSettings>("/api/settings/recycle", {
      method: "PUT",
      body: JSON.stringify({ keep_days: keepDays }),
    }),
  jobs: () => request<JobList>("/api/jobs"),
  job: (id: number) => request<Job>(`/api/jobs/${id}`),
  jobCounts: () => request<JobCounts>("/api/jobs/counts"),
  cancelJob: (id: number) => request<Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  clearFinishedJobs: () => request<{ removed: number }>("/api/jobs/finished", { method: "DELETE" }),
};
