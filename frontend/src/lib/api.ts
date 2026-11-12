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
  episode_id: number | null;
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

export type JobGroup = { id: string; title: string; created_at: string };

export type JobList = { jobs: Job[]; counts: JobCounts; groups: JobGroup[] };

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
  original: string;
  original_size: number;
  copy_file: string;
  copy_size: number;
  hardlinked: boolean;
  keep_days: number;
  recycle_folder: string;
  /** An HDR10 copy: replacing the original removes Dolby Vision from the film. */
  loses_dolby_vision: boolean;
  /** "Radarr"/"Sonarr" when connected: it may download a Dolby Vision release again. */
  may_redownload: string | null;
};

export type Hdr10CopyPreview = {
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

/** A film or an episode: every action on files works the same way for both. */
export type ItemRef = { kind: "films" | "episodes"; id: number };

export function itemPath(item: ItemRef): string {
  return `/api/${item.kind}/${item.id}`;
}

export type Show = {
  id: number;
  title: string;
  year: number | null;
  folder_name: string;
  poster_url: string | null;
  size: number;
  added_at: string;
  season_count: number;
  episode_count: number;
  /** Across the episodes: HDR formats found and the best picture size. */
  media: MediaSummary;
  dv_episodes: number;
};

export type ShowList = { root: string; shows: Show[]; scan: ScanStatus; reading: ReadingStatus };

export type Episode = {
  id: number;
  season: number | null;
  episode: number | null;
  episode_end: number | null;
  /** "S01E02", "Special 3", or "" when the file name has no episode number. */
  label: string;
  title: string;
  main_file: string | null;
  is_mkv: boolean;
  size: number;
  added_at: string;
  file_count: number;
  has_copy: boolean;
  media: MediaSummary;
};

export type Season = { season: number | null; label: string; size: number; episodes: Episode[] };

export type ShowDetail = Show & {
  folder: string;
  backdrop_url: string | null;
  tvdb_id: number | null;
  seasons: Season[];
};

export type EpisodeDetail = Episode & {
  show_id: number;
  show_title: string;
  show_year: number | null;
  poster_url: string | null;
  backdrop_url: string | null;
  folder: string;
  files: FilmFile[];
};

export type LanguageChoice = {
  /** "only": keep just these languages; "none": remove them all (subtitles only). */
  mode: "all" | "only" | "none";
  languages: string[];
  keep_unknown?: boolean;
  keep_original?: boolean;
};

export type BatchAction =
  | { type: "hdr10_copy"; overwrite?: boolean }
  | {
      type: "remove_tracks";
      audio: LanguageChoice;
      subtitles: LanguageChoice;
      remove_commentary: boolean;
      overwrite?: boolean;
    }
  | {
      type: "default_tracks";
      audio_language: string | null;
      subtitles: "keep" | "off" | "language";
      subtitle_language: string | null;
    };

export type BatchRequest = {
  /** null: the whole show. */
  season: number | null;
  action: BatchAction;
  allow_hardlinked: boolean;
};

export type BatchFile = {
  episode_id: number;
  label: string;
  file: string;
  will_run: boolean;
  lines: string[];
  reason: string | null;
  hardlinked: boolean;
  new_file: string | null;
};

export type BatchPreview = {
  title: string;
  action: string;
  scope: string;
  changes_originals: boolean;
  files: BatchFile[];
  will_run: number;
  skipped: number;
  hardlinked_skipped: number;
  space: { label: string; needed: number; free: number; enough: boolean }[];
  enough_space: boolean;
};

export type BatchStarted = { group_id: string; title: string; jobs: number };

export type Language = { code: string; name: string; common: boolean };

export type ServiceName = "radarr" | "sonarr" | "plex";

export type Connections = {
  radarr: { url: string; has_key: boolean };
  sonarr: { url: string; has_key: boolean };
  plex: { url: string; has_key: boolean };
  plex_refresh: boolean;
  arr_rescan: boolean;
  tidy_copies: boolean;
  /** Add after Tailarr's own address for Radarr/Sonarr's Webhook connection. */
  webhook_paths: Record<"radarr" | "sonarr", string>;
  sync: {
    running: boolean;
    finished_at: string | null;
    films: number | null;
    shows: number | null;
    errors: Record<string, string> | null;
  };
};

export type ConnectionsInput = {
  radarr: { url: string; api_key?: string };
  sonarr: { url: string; api_key?: string };
  plex: { url: string; api_key?: string };
  plex_refresh: boolean;
  arr_rescan: boolean;
  tidy_copies: boolean;
};

export type ConnectionTest = { ok: boolean; message: string; details: string | null };

export type MappingTest = {
  path: string;
  exists: boolean;
  inside_library: boolean;
  message: string;
};

export type ActivityEntry = {
  id: number;
  at: string;
  source: string;
  kind: string;
  message: string;
  ok: boolean;
  details: string | null;
  path: string | null;
  job_id: number | null;
  rule_id: number | null;
};

export type ConditionType =
  "has_dolby_vision" | "has_hdr10plus" | "is_4k" | "has_audio_not_in" | "has_subtitles_not_in";

export type Condition = { type: ConditionType; languages: string[] };

export type RuleInput = {
  name: string;
  enabled: boolean;
  scope: "films" | "tv" | "both";
  conditions: Condition[];
  action: BatchAction;
  /** Rules never change original files unless this is ticked. */
  allow_originals: boolean;
  /** ...nor seeding (hardlinked) files in place unless this is ticked too. */
  allow_hardlinked: boolean;
};

export type Rule = RuleInput & {
  id: number;
  /** The whole rule in plain English. */
  sentence: string;
  action_text: string;
  changes_originals: boolean;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
};

export type RulePreviewItem = {
  kind: "film" | "episode";
  id: number;
  label: string;
  file: string;
  will_run: boolean;
  lines: string[];
  reason: string | null;
  hardlinked: boolean;
  new_file: string | null;
};

export type RulePreview = {
  sentence: string;
  changes_originals: boolean;
  items: RulePreviewItem[];
  will_run: number;
  skipped: number;
  not_matching: number;
  not_read: number;
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
  media: (item: ItemRef, file: string, refresh = false) =>
    request<Media>(
      `${itemPath(item)}/media?${new URLSearchParams({ file, ...(refresh ? { refresh: "true" } : {}) })}`,
    ),
  rescanFilms: () => request<ScanStatus>("/api/films/scan", { method: "POST" }),
  previewTrackSettings: (item: ItemRef, body: TrackSettingsRequest) =>
    request<TrackSettingsPreview>(`${itemPath(item)}/track-settings/preview`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  changeTrackSettings: (
    item: ItemRef,
    body: TrackSettingsRequest & { confirmed: true; allow_hardlinked: boolean },
  ) =>
    request<Job>(`${itemPath(item)}/track-settings`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  previewRemoveTracks: (item: ItemRef, body: RemoveTracksRequest) =>
    request<RemoveTracksPreview>(`${itemPath(item)}/remove-tracks/preview`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  removeTracks: (
    item: ItemRef,
    body: RemoveTracksRequest & { confirmed: true; overwrite: boolean },
  ) =>
    request<Job>(`${itemPath(item)}/remove-tracks`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  previewReplaceOriginal: (item: ItemRef, copyFile: string) =>
    request<ReplaceOriginalPreview>(`${itemPath(item)}/replace-original/preview`, {
      method: "POST",
      body: JSON.stringify({ copy_file: copyFile }),
    }),
  replaceOriginal: (item: ItemRef, copyFile: string) =>
    request<Job>(`${itemPath(item)}/replace-original`, {
      method: "POST",
      body: JSON.stringify({ copy_file: copyFile, confirmed: true, understood: true }),
    }),
  previewHdr10Copy: (item: ItemRef, file: string) =>
    request<Hdr10CopyPreview>(`${itemPath(item)}/hdr10-copy/preview`, {
      method: "POST",
      body: JSON.stringify({ file }),
    }),
  hdr10Copy: (item: ItemRef, file: string, overwrite: boolean) =>
    request<Job>(`${itemPath(item)}/hdr10-copy`, {
      method: "POST",
      body: JSON.stringify({ file, confirmed: true, overwrite }),
    }),
  shows: () => request<ShowList>("/api/tv"),
  show: (id: number | string) => request<ShowDetail>(`/api/tv/shows/${id}`),
  episode: (id: number | string) => request<EpisodeDetail>(`/api/episodes/${id}`),
  rescanTv: () => request<ScanStatus>("/api/tv/scan", { method: "POST" }),
  previewBatch: (showId: number, body: BatchRequest) =>
    request<BatchPreview>(`/api/tv/shows/${showId}/batch/preview`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  startBatch: (showId: number, body: BatchRequest) =>
    request<BatchStarted>(`/api/tv/shows/${showId}/batch`, {
      method: "POST",
      body: JSON.stringify({ ...body, confirmed: true }),
    }),
  languages: () => request<Language[]>("/api/languages"),
  cancelGroup: (groupId: string) =>
    request<{ cancelled: number }>(`/api/jobs/groups/${groupId}/cancel`, { method: "POST" }),
  connections: () => request<Connections>("/api/settings/connections"),
  saveConnections: (body: ConnectionsInput) =>
    request<Connections>("/api/settings/connections", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  testConnection: (service: ServiceName, url: string, apiKey: string) =>
    request<ConnectionTest>("/api/settings/connections/test", {
      method: "POST",
      body: JSON.stringify({ service, url, api_key: apiKey }),
    }),
  newWebhookSecret: () =>
    request<Connections>("/api/settings/connections/new-secret", { method: "POST" }),
  syncConnections: () => request<unknown>("/api/connections/sync", { method: "POST" }),
  testPathMapping: (path: string) =>
    request<MappingTest>("/api/settings/path-mappings/test", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  activity: (params: { limit?: number; source?: string; rule_id?: number } = {}) =>
    request<ActivityEntry[]>(
      `/api/activity?${new URLSearchParams(
        Object.entries(params)
          .filter(([, v]) => v !== undefined)
          .map(([k, v]) => [k, String(v)]),
      )}`,
    ),
  rules: () => request<Rule[]>("/api/rules"),
  rule: (id: number | string) => request<Rule>(`/api/rules/${id}`),
  createRule: (body: RuleInput) =>
    request<Rule>("/api/rules", { method: "POST", body: JSON.stringify(body) }),
  saveRule: (id: number, body: RuleInput) =>
    request<Rule>(`/api/rules/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  setRuleEnabled: (id: number, enabled: boolean) =>
    request<Rule>(`/api/rules/${id}/enabled`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
  deleteRule: async (id: number) => {
    const response = await fetch(`/api/rules/${id}`, { method: "DELETE" });
    if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  },
  previewRule: (body: RuleInput) =>
    request<RulePreview>("/api/rules/preview", { method: "POST", body: JSON.stringify(body) }),
  runRule: (id: number) =>
    request<{ group_id: string | null; jobs: number }>(`/api/rules/${id}/run`, {
      method: "POST",
      body: JSON.stringify({ confirmed: true }),
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
