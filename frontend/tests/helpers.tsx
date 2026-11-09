import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import { AppRoutes, makeQueryClient } from "@/App";
import type { Health, LibrarySettings } from "@/lib/api";
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
