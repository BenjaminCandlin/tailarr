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
};

export type FilmList = { root: string; films: Film[]; scan: ScanStatus };

export type FilmFile = {
  name: string;
  size: number;
  modified_at: string;
  is_mkv: boolean;
  is_copy: boolean;
  is_main: boolean;
  hardlinked: boolean;
};

export type FilmDetail = Film & {
  folder: string;
  backdrop_url: string | null;
  tmdb_id: number | null;
  imdb_id: string | null;
  files: FilmFile[];
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
  rescanFilms: () => request<ScanStatus>("/api/films/scan", { method: "POST" }),
};
