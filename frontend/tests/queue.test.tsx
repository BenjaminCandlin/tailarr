import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { formatElapsed } from "@/lib/format";

import { job, json, mockBackend, renderApp } from "./helpers";

const RUNNING = job({
  id: 1,
  status: "running",
  step: "Saving the changes",
  step_number: 2,
  step_count: 3,
  progress: 40,
  started_at: new Date(Date.now() - 65_000).toISOString(),
});
const WAITING = job({ id: 2, subject: "Bright Lights (2019)", film_id: 1 });
const DONE = job({
  id: 3,
  status: "done",
  message: "2 tracks changed.",
  started_at: "2026-11-11T09:00:00Z",
  finished_at: "2026-11-11T09:00:04Z",
});
const FAILED = job({
  id: 4,
  status: "failed",
  error: "Not enough free space on the disk: needs 48 GB, 31 GB free.",
  error_details: "statvfs: 31 GB",
  finished_at: "2026-11-11T08:00:00Z",
});

describe("queue page", () => {
  it("formats running times", () => {
    expect(formatElapsed(4)).toBe("4 s");
    expect(formatElapsed(125)).toBe("2 min 05 s");
    expect(formatElapsed(3780)).toBe("1 h 03 min");
  });

  it("is empty at first", async () => {
    mockBackend();
    renderApp("/queue");
    expect(await screen.findByText("Nothing in the queue")).toBeInTheDocument();
  });

  it("shows running, waiting and finished jobs", async () => {
    mockBackend((url) => {
      if (url.endsWith("/api/jobs/counts")) return json({ running: 1, queued: 1 });
      if (url.endsWith("/api/jobs"))
        return json({ jobs: [RUNNING, WAITING, DONE, FAILED], counts: { running: 1, queued: 1 } });
      return undefined;
    });
    renderApp("/queue");
    const now = await screen.findByRole("region", { name: /Running and waiting/ });
    const running = within(now).getByTestId("job-1");
    expect(running).toHaveTextContent("Change track settings");
    expect(running).toHaveTextContent("Running");
    expect(running).toHaveTextContent("Saving the changes… (step 2 of 3)");
    expect(within(running).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
    expect(running).toHaveTextContent(/1 min 0\d s/);
    expect(within(running).getByRole("link", { name: "Colour Test (2023)" })).toHaveAttribute(
      "href",
      "/films/5",
    );
    expect(within(now).getByTestId("job-2")).toHaveTextContent("Waiting");

    const finished = screen.getByRole("region", { name: /Finished/ });
    expect(within(finished).getByTestId("job-3")).toHaveTextContent("took 4 s");
    const failed = within(finished).getByTestId("job-4");
    expect(within(failed).getByRole("alert")).toHaveTextContent("needs 48 GB, 31 GB free");
    await userEvent.click(within(failed).getByText("Show technical details"));
    expect(within(failed).getByText("statvfs: 31 GB")).toBeVisible();

    // The Queue menu item shows how many jobs are running or waiting.
    await waitFor(() =>
      expect(screen.getAllByLabelText("2 running or waiting").length).toBeGreaterThan(0),
    );
  });

  it("cancels a job", async () => {
    const cancelled: string[] = [];
    mockBackend((url, init) => {
      if (url.endsWith("/api/jobs/1/cancel") && init?.method === "POST") {
        cancelled.push(url);
        return json({ ...RUNNING, cancel_requested: true });
      }
      if (url.endsWith("/api/jobs"))
        return json({
          jobs: [cancelled.length ? { ...RUNNING, cancel_requested: true } : RUNNING],
          counts: { running: 1, queued: 0 },
        });
      return undefined;
    });
    renderApp("/queue");
    const card = await screen.findByTestId("job-1");
    await userEvent.click(within(card).getByRole("button", { name: "Cancel" }));
    expect(cancelled).toHaveLength(1);
    expect(await within(card).findByText("Stopping…")).toBeInTheDocument();
  });

  it("says when a step can't be stopped", async () => {
    mockBackend((url) =>
      url.endsWith("/api/jobs")
        ? json({ jobs: [{ ...RUNNING, cancellable: false }], counts: { running: 1, queued: 0 } })
        : undefined,
    );
    renderApp("/queue");
    const card = await screen.findByTestId("job-1");
    expect(within(card).queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    expect(card).toHaveTextContent("can't be stopped safely");
  });

  it("clears finished jobs", async () => {
    let cleared = false;
    mockBackend((url, init) => {
      if (url.endsWith("/api/jobs/finished") && init?.method === "DELETE") {
        cleared = true;
        return json({ removed: 2 });
      }
      if (url.endsWith("/api/jobs"))
        return json({ jobs: cleared ? [] : [DONE, FAILED], counts: { running: 0, queued: 0 } });
      return undefined;
    });
    renderApp("/queue");
    await userEvent.click(await screen.findByRole("button", { name: "Clear finished jobs" }));
    expect(await screen.findByText("Nothing in the queue")).toBeInTheDocument();
  });
});
