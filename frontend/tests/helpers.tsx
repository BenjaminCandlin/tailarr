import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import { AppRoutes, makeQueryClient } from "@/App";
import type { Film, FilmDetail, FilmList, Health, LibrarySettings } from "@/lib/api";
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
    ...extra,
  };
}

export const FILMS: FilmList = {
  root: "/data/media/movies",
  films: [
    film(3, "Ärger im Paradies", 2020),
    film(1, "Bright Lights", 2019, { poster_url: "/api/films/1/poster?v=1" }),
    film(5, "Colour Test", 2023, { file_count: 2 }),
    film(2, "The Long Weekend", 1999, { folder_name: "The Long Weekend (1999) {tmdb-10001}" }),
    film(4, "Old Home Video", 1995, { is_mkv: false, main_file: "Old Home Video.mp4" }),
  ],
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
    },
    {
      name: "Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10.mkv",
      size: 1024 ** 3,
      modified_at: "2026-05-02T12:00:00Z",
      is_mkv: true,
      is_copy: true,
      is_main: false,
      hardlinked: false,
    },
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
    if (url.endsWith("/api/films")) return json(FILMS);
    if (url.endsWith("/api/films/5")) return json(FILM_DETAIL);
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
