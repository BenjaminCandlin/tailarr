import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { HEALTH, LIBRARY, json, mockBackend, renderApp } from "./helpers";

describe("settings page", () => {
  it("shows the system check in plain English", async () => {
    mockBackend();
    renderApp("/settings");
    expect(await screen.findByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText(/version 82.0/)).toBeInTheDocument();
    expect(screen.getByText(/Not installed/)).toBeInTheDocument();
    expect(screen.getByText(/This folder can't be found/)).toBeInTheDocument();
    expect(screen.getByText("Not set up. That's fine.")).toBeInTheDocument();
  });

  it("says All good when everything works", async () => {
    mockBackend((url) =>
      url.endsWith("/api/health")
        ? json({ ...HEALTH, ok: true, tools: [HEALTH.tools[0]], folders: [HEALTH.folders[0]] })
        : undefined,
    );
    renderApp("/settings");
    expect(await screen.findByText("All good")).toBeInTheDocument();
  });

  it("warns when permissions don't match Unraid's usual ones", async () => {
    mockBackend((url) =>
      url.endsWith("/api/health")
        ? json({ ...HEALTH, running_as: { uid: 0, gid: 0, umask: "022" } })
        : undefined,
    );
    renderApp("/settings");
    expect(await screen.findByText(/Unraid normally uses user 99/)).toBeInTheDocument();
  });

  it("saves new folders", async () => {
    let saved: unknown;
    mockBackend((url, init) => {
      if (url.endsWith("/api/settings/library") && init?.method === "PUT") {
        saved = JSON.parse(String(init.body));
        return json(saved);
      }
      return undefined;
    });
    renderApp("/settings");
    const films = await screen.findByLabelText("Films folder");
    const button = screen.getByRole("button", { name: "Save folders" });
    expect(button).toBeDisabled();
    await userEvent.clear(films);
    await userEvent.type(films, "/data/media/films");
    await userEvent.click(button);
    expect(saved).toEqual({ ...LIBRARY, movies_dir: "/data/media/films" });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved.");
  });

  it("explains why folders were refused", async () => {
    mockBackend((url, init) =>
      init?.method === "PUT" && url.endsWith("/api/settings/library")
        ? json(
            {
              detail: [
                {
                  msg: "Value error, The Films folder and the TV folder must be separate folders.",
                },
              ],
            },
            422,
          )
        : undefined,
    );
    renderApp("/settings");
    const tv = await screen.findByLabelText("TV folder");
    await userEvent.clear(tv);
    await userEvent.type(tv, "/data/media/movies");
    await userEvent.click(screen.getByRole("button", { name: "Save folders" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The Films folder and the TV folder must be separate folders.");
    expect(within(alert).queryByText(/Value error/)).toBeNull();
  });
});

describe("work folder", () => {
  it("explains how to add one when it isn't set up", async () => {
    mockBackend();
    renderApp("/settings");
    expect(await screen.findByTestId("work-folder-status")).toHaveTextContent("Not set up");
    expect(screen.getByText(/Container Path/)).toBeInTheDocument();
  });
});
