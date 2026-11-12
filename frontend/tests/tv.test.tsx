import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { actionOf, missingChoice } from "@/components/BatchDialog";
import { groupCounts } from "@/components/JobGroupCard";
import type { BatchPreview, BatchRequest } from "@/lib/api";

import {
  EPISODE_DETAIL,
  MEDIA,
  SHOWS,
  SHOW_DETAIL,
  job,
  json,
  mockBackend,
  renderApp,
} from "./helpers";

function tvBackend(extra?: (url: string, init?: RequestInit) => Response | undefined) {
  return mockBackend((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/api/tv")) return json(SHOWS);
    if (url.endsWith("/api/tv/shows/2")) return json(SHOW_DETAIL);
    if (url.endsWith("/api/episodes/12")) return json(EPISODE_DETAIL);
    if (url.includes("/api/episodes/12/media"))
      return json({ ...MEDIA, file: EPISODE_DETAIL.files[0].name });
    return undefined;
  });
}

const PREVIEW: BatchPreview = {
  title: "Save a copy keeping only English subtitles: Another Show, Season 1",
  action: "Save a copy keeping only English subtitles",
  scope: "Another Show, Season 1",
  changes_originals: false,
  files: [
    {
      episode_id: 12,
      label: "S01E02 – Middle",
      file: "Another Show (2022) - S01E02 - Middle.mkv",
      will_run: true,
      lines: ["Leave out Subtitles 2: French – SubRip (text)"],
      reason: null,
      hardlinked: false,
      new_file: "Another Show (2022) - S01E02 - Middle - Tailarr.mkv",
    },
    {
      episode_id: 13,
      label: "S01E03 – End",
      file: "Another Show (2022) - S01E03 - End.mkv",
      will_run: false,
      lines: [],
      reason: "Nothing to remove: every track is one you want to keep.",
      hardlinked: false,
      new_file: null,
    },
  ],
  will_run: 1,
  skipped: 1,
  hardlinked_skipped: 0,
  space: [{ label: "the disk with your files", needed: 2e9, free: 5e11, enough: true }],
  enough_space: true,
};

describe("TV pages", () => {
  it("lists shows and searches them", async () => {
    tvBackend();
    renderApp("/tv");
    const list = await screen.findByRole("list", { name: "Shows" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/2 shows · 7 episodes/)).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox", { name: "Search shows" }), "test");
    await waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(1));
    expect(within(list).getByRole("link", { name: /Test Show/ })).toBeInTheDocument();
  });

  it("filters shows with Dolby Vision", async () => {
    tvBackend();
    renderApp("/tv?show=dv");
    const list = await screen.findByRole("list", { name: "Shows" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByRole("link", { name: /Another Show/ })).toBeInTheDocument();
  });

  it("explains an empty TV folder", async () => {
    tvBackend((url) => (url.endsWith("/api/tv") ? json({ ...SHOWS, shows: [] }) : undefined));
    renderApp("/tv");
    expect(await screen.findByText("No TV shows found")).toBeInTheDocument();
    expect(screen.getByText(/Season 01/)).toBeInTheDocument();
  });

  it("shows seasons and episodes", async () => {
    tvBackend();
    renderApp("/tv/shows/2");
    expect(await screen.findByRole("heading", { name: /Another Show/ })).toBeInTheDocument();
    const season = screen.getByRole("list", { name: "Season 1 episodes" });
    const rows = within(season).getAllByRole("link");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("S01E01");
    expect(rows[0]).toHaveTextContent("Has a Tailarr copy");
    expect(rows[1]).toHaveAttribute("href", "/tv/episodes/12");
    expect(screen.getByText("3 episodes with Dolby Vision")).toBeInTheDocument();
  });

  it("shows an episode with its tracks and actions", async () => {
    tvBackend();
    renderApp("/tv/episodes/12");
    expect(await screen.findByRole("heading", { name: "Middle" })).toBeInTheDocument();
    expect(screen.getByText("Another Show · S01E02")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Another Show/ })).toHaveAttribute(
      "href",
      "/tv/shows/2",
    );
    expect(await screen.findByText("What's inside")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Make an HDR10 copy/ })).toBeInTheDocument();
  });
});

describe("batch actions", () => {
  it("turns choices into an action", () => {
    const start = {
      kind: "remove_tracks" as const,
      overwrite: false,
      audioMode: "all" as const,
      audioLanguages: ["eng"],
      subtitleMode: "all" as const,
      subtitleLanguages: ["eng"],
      removeCommentary: false,
      defaultAudio: null,
      defaultSubtitles: "keep" as const,
      defaultSubtitleLanguage: null,
    };
    expect(missingChoice(start)).toMatch(/Choose which/);
    expect(missingChoice({ ...start, subtitleMode: "only", subtitleLanguages: [] })).toMatch(
      /subtitle language/,
    );
    expect(actionOf({ ...start, subtitleMode: "only" })).toEqual({
      type: "remove_tracks",
      audio: { mode: "all", languages: [] },
      subtitles: { mode: "only", languages: ["eng"] },
      remove_commentary: false,
      overwrite: false,
    });
    expect(missingChoice({ ...start, kind: "default_tracks" })).toMatch(/default audio/);
    expect(actionOf({ ...start, kind: "default_tracks", defaultAudio: "fre" })).toEqual({
      type: "default_tracks",
      audio_language: "fre",
      subtitles: "keep",
      subtitle_language: null,
    });
  });

  it("previews a season and starts one job per episode", async () => {
    const sent: BatchRequest[] = [];
    let started = false;
    tvBackend((url, init) => {
      if (url.endsWith("/api/tv/shows/2/batch/preview")) {
        sent.push(JSON.parse(String(init?.body)));
        return json(PREVIEW);
      }
      if (url.endsWith("/api/tv/shows/2/batch")) {
        started = JSON.parse(String(init?.body)).confirmed === true;
        return json({ group_id: "g1", title: PREVIEW.title, jobs: 1 }, 202);
      }
      return undefined;
    });
    renderApp("/tv/shows/2");
    await userEvent.click(await screen.findByRole("button", { name: /Change this season/ }));
    const dialog = await screen.findByRole("dialog", { name: /Change season 1 of Another Show/ });
    await userEvent.click(within(dialog).getByRole("radio", { name: /Save copies without some/ }));
    // English is chosen for subtitles to start with; add French too, then remove it again.
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Add a subtitle language to keep"),
      "fre",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove French" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Show what will happen" }));

    const summary = await screen.findByRole("dialog", { name: "Check before starting" });
    expect(sent[0]).toEqual({
      season: 1,
      action: {
        type: "remove_tracks",
        audio: { mode: "all", languages: [] },
        subtitles: { mode: "only", languages: ["eng"] },
        remove_commentary: false,
        overwrite: false,
      },
      allow_hardlinked: false,
    });
    expect(within(summary).getByTestId("batch-counts")).toHaveTextContent(
      "1 episode will get a copy, 1 skipped.",
    );
    expect(within(summary).getByText(/Leave out Subtitles 2: French/)).toBeInTheDocument();
    expect(within(summary).getByText(/Nothing to remove/)).toBeInTheDocument();
    await userEvent.click(within(summary).getByRole("button", { name: "Make 1 copy" }));
    expect(await screen.findByText("1 job added to the queue")).toBeInTheDocument();
    expect(started).toBe(true);
    expect(screen.getByRole("link", { name: /Open the Queue/ })).toHaveAttribute("href", "/queue");
  });

  it("asks before changing seeding originals", async () => {
    const sent: BatchRequest[] = [];
    tvBackend((url, init) => {
      if (url.endsWith("/batch/preview")) {
        const body = JSON.parse(String(init?.body)) as BatchRequest;
        sent.push(body);
        return json({
          ...PREVIEW,
          action: "Make the default French audio",
          changes_originals: true,
          files: [
            { ...PREVIEW.files[0], lines: ["Audio 2: French: Make it the default"] },
            {
              ...PREVIEW.files[1],
              hardlinked: true,
              will_run: body.allow_hardlinked,
              reason: body.allow_hardlinked ? null : "Also in your downloads (still seeding)",
            },
          ],
          will_run: body.allow_hardlinked ? 2 : 1,
          hardlinked_skipped: body.allow_hardlinked ? 0 : 1,
          space: [],
        });
      }
      return undefined;
    });
    renderApp("/tv/shows/2");
    await userEvent.click(await screen.findByRole("button", { name: /Change the whole show/ }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("radio", { name: /Choose the default audio/ }));
    expect(within(dialog).getByRole("button", { name: "Show what will happen" })).toBeDisabled();
    await userEvent.selectOptions(within(dialog).getByLabelText("Default audio"), "fre");
    await userEvent.click(within(dialog).getByRole("button", { name: "Show what will happen" }));
    const summary = await screen.findByRole("dialog", { name: "Check before starting" });
    expect(within(summary).getByText(/This changes the original files/)).toBeInTheDocument();
    const confirm = within(summary).getByRole("button", { name: "Change 1 original file" });
    expect(confirm.className).toMatch(/destructive/);
    await userEvent.click(within(summary).getByRole("checkbox", { name: /change seeding/ }));
    await waitFor(() => expect(sent.at(-1)?.allow_hardlinked).toBe(true));
    expect(sent[0].season).toBeNull();
    expect(
      await within(summary).findByRole("button", { name: "Change 2 original files" }),
    ).toBeInTheDocument();
  });
});

describe("queue groups", () => {
  it("counts a group's jobs", () => {
    expect(
      groupCounts([
        job({ id: 1, status: "done" }),
        job({ id: 2, status: "failed" }),
        job({ id: 3, status: "running" }),
        job({ id: 4, status: "queued" }),
      ]),
    ).toBe("1 of 4 done · 1 failed · 1 running · 1 waiting");
  });

  it("shows jobs of a season together, and can cancel the rest", async () => {
    let cancelled = false;
    const jobs = [
      job({ id: 1, status: "running", group_id: "g1", episode_id: 12, film_id: null }),
      job({ id: 2, status: "queued", group_id: "g1", episode_id: 13, film_id: null }),
      job({ id: 3, status: "done", film_id: 5 }),
    ];
    mockBackend((url, init) => {
      if (url.endsWith("/api/jobs"))
        return json({
          jobs,
          counts: { running: 1, queued: 1 },
          groups: [{ id: "g1", title: "Make HDR10 copies: Another Show", created_at: "" }],
        });
      if (url.endsWith("/api/jobs/groups/g1/cancel") && init?.method === "POST") {
        cancelled = true;
        return json({ cancelled: 2 });
      }
      return undefined;
    });
    renderApp("/queue");
    const group = await screen.findByTestId("group-g1");
    expect(within(group).getByText("Make HDR10 copies: Another Show")).toBeInTheDocument();
    expect(within(group).getByTestId("group-counts")).toHaveTextContent(
      "0 of 2 done · 1 running · 1 waiting",
    );
    expect(within(group).getByTestId("job-1")).toBeInTheDocument();
    expect(within(group).getAllByRole("link")[0]).toHaveAttribute("href", "/tv/episodes/12");
    await userEvent.click(within(group).getByRole("button", { name: "Cancel the rest" }));
    await waitFor(() => expect(cancelled).toBe(true));
    const finished = screen.getByRole("region", { name: /Finished/ });
    expect(within(finished).getByTestId("job-3")).toBeInTheDocument();
  });
});
