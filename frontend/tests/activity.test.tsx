import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ActivityEntry } from "@/lib/api";

import { json, mockBackend, renderApp } from "./helpers";

const ENTRY: ActivityEntry = {
  id: 1,
  at: new Date(Date.now() - 120_000).toISOString(),
  source: "rule",
  kind: "job-queued",
  message: "Rule “HDR10 copies”: make a copy without dolby vision for Colour Test (2023).",
  ok: true,
  details: null,
  path: "/data/media/movies/Colour Test (2023)/x.mkv",
  job_id: 9,
  rule_id: 3,
  job_status: "failed",
  job_error: "Not enough free space on the disk.",
  film_id: 5,
  episode_id: null,
  rule_name: "HDR10 copies",
};

describe("activity log", () => {
  it("shows what rules and apps did, with links", async () => {
    mockBackend((url) => (url.includes("/api/activity") ? json([ENTRY]) : undefined));
    renderApp("/activity");
    const entry = await screen.findByTestId("activity-1");
    expect(entry).toHaveTextContent("Rule “HDR10 copies”: make a copy");
    expect(entry).toHaveTextContent("Job: Failed");
    expect(entry).toHaveTextContent("Not enough free space on the disk.");
    expect(within(entry).getByRole("link", { name: "Open the film" })).toHaveAttribute(
      "href",
      "/films/5",
    );
    expect(within(entry).getByRole("link", { name: "Rule “HDR10 copies”" })).toHaveAttribute(
      "href",
      "/rules/3",
    );
    expect(within(entry).getByLabelText("Problem")).toBeInTheDocument();
  });

  it("filters to problems only", async () => {
    const urls: string[] = [];
    mockBackend((url) => {
      if (url.includes("/api/activity")) {
        urls.push(url);
        return json([]);
      }
      return undefined;
    });
    renderApp("/activity");
    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Show"), "problems");
    await waitFor(() => expect(urls.at(-1)).toContain("problems=true"));
  });

  it("saves the automatic rules settings", async () => {
    let saved: unknown = null;
    mockBackend((url, init) => {
      if (url.endsWith("/api/settings/automation") && init?.method === "PUT") {
        saved = JSON.parse(String(init.body));
        return json({ ...(saved as object), watch_since: null, waiting: [] });
      }
      return undefined;
    });
    renderApp("/settings");
    const settle = await screen.findByLabelText(/stopped changing for/);
    await userEvent.clear(settle);
    await userEvent.type(settle, "120");
    await userEvent.click(screen.getByRole("switch", { name: /watch the Films and TV folders/ }));
    expect(screen.getByLabelText(/look through the folders every/)).toHaveValue(15);
    const card = settle.closest("form")!;
    await userEvent.click(within(card).getByRole("button", { name: "Save automatic rules" }));
    await waitFor(() =>
      expect(saved).toEqual({ settle_seconds: 120, watch_folders: true, rescan_minutes: 15 }),
    );
  });
});
