import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CONNECTIONS, json, LIBRARY, mockBackend, renderApp } from "./helpers";

describe("connections", () => {
  it("shows which apps are connected and the webhook addresses", async () => {
    mockBackend();
    renderApp("/settings");
    const radarr = await screen.findByTestId("connection-radarr");
    expect(radarr).toHaveTextContent("Connected");
    expect(screen.getByTestId("connection-plex")).toHaveTextContent("Not connected (optional)");
    expect(within(radarr).getByLabelText("API key")).toHaveAttribute(
      "placeholder",
      "Saved (leave empty to keep it)",
    );
    expect(screen.getByLabelText("Radarr webhook address")).toHaveValue(
      "http://tailarr:8484/api/webhooks/radarr?secret=s3cret",
    );
    expect(screen.getByTestId("sync-status")).toHaveTextContent(
      "Titles and posters: 9 films matched",
    );
  });

  it("tests a connection and explains problems", async () => {
    const tested: unknown[] = [];
    mockBackend((url, init) => {
      if (url.endsWith("/api/settings/connections/test")) {
        const body = JSON.parse(String(init?.body));
        tested.push(body);
        return body.url.includes("unknown")
          ? json({
              ok: false,
              message: "Tailarr can't find “unknown”. … same custom Docker network …",
              details: "Name or service not known",
            })
          : json({ ok: true, message: "Connected to Plex 1.41.0.", details: null });
      }
      return undefined;
    });
    renderApp("/settings");
    const plex = await screen.findByTestId("connection-plex");
    await userEvent.type(within(plex).getByLabelText("Address"), "http://plex:32400");
    await userEvent.type(within(plex).getByLabelText("Plex token"), "tok");
    await userEvent.click(within(plex).getByRole("button", { name: "Test Plex" }));
    expect(await within(plex).findByText("Connected to Plex 1.41.0.")).toBeInTheDocument();
    expect(tested[0]).toEqual({ service: "plex", url: "http://plex:32400", api_key: "tok" });
    await userEvent.clear(within(plex).getByLabelText("Address"));
    await userEvent.type(within(plex).getByLabelText("Address"), "http://unknown:1");
    await userEvent.click(within(plex).getByRole("button", { name: "Test Plex" }));
    expect(await within(plex).findByRole("alert")).toHaveTextContent("Docker network");
    expect(within(plex).getByText("Show technical details")).toBeInTheDocument();
  });

  it("only sends keys that were typed", async () => {
    let saved: Record<string, unknown> | null = null;
    mockBackend((url, init) => {
      if (url.endsWith("/api/settings/connections") && init?.method === "PUT") {
        saved = JSON.parse(String(init.body));
        return json(CONNECTIONS);
      }
      return undefined;
    });
    renderApp("/settings");
    const sonarr = await screen.findByTestId("connection-sonarr");
    await userEvent.type(within(sonarr).getByLabelText("Address"), "http://sonarr:8989");
    await userEvent.type(within(sonarr).getByLabelText("API key"), "abc");
    await userEvent.click(screen.getByRole("switch", { name: /Ask Plex to refresh/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save connections" }));
    await waitFor(() => expect(saved).not.toBeNull());
    expect(saved).toEqual({
      radarr: { url: "http://radarr:7878" },
      sonarr: { url: "http://sonarr:8989", api_key: "abc" },
      plex: { url: "" },
      plex_refresh: false,
      arr_rescan: true,
      tidy_copies: true,
    });
  });

  it("edits and tests path mappings", async () => {
    let saved: Record<string, unknown> | null = null;
    mockBackend((url, init) => {
      if (url.endsWith("/api/settings/library") && init?.method === "PUT") {
        saved = JSON.parse(String(init.body));
        return json(saved);
      }
      if (url.endsWith("/api/settings/path-mappings/test"))
        return json({
          path: "/data/media/movies/Film (2020)",
          exists: true,
          inside_library: true,
          message: "Found it. Tailarr can use this path.",
        });
      return undefined;
    });
    renderApp("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Add a path mapping" }));
    await userEvent.type(screen.getByLabelText("Path in Radarr, Sonarr or Plex"), "/movies");
    await userEvent.type(screen.getByLabelText("The same folder in Tailarr"), "/data/media/movies");
    await userEvent.click(screen.getByRole("button", { name: "Save folders" }));
    await waitFor(() => expect(saved).not.toBeNull());
    expect(saved).toEqual({
      movies_dir: LIBRARY.movies_dir,
      tv_dir: LIBRARY.tv_dir,
      path_mappings: [{ remote: "/movies", local: "/data/media/movies" }],
    });
    await userEvent.type(screen.getByLabelText(/Test a path/), "/movies/Film (2020)");
    await userEvent.click(screen.getByRole("button", { name: "Test" }));
    expect(await screen.findByText(/Found it/)).toBeInTheDocument();
  });
});
