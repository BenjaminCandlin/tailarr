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

export class ApiError extends Error {}

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
  if (!response.ok) throw new ApiError(await errorMessage(response));
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
};
