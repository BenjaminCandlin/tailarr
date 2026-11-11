import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { changesFrom } from "@/components/TrackSettingsEditor";
import type { TrackSettingsPreview } from "@/lib/api";

import { FILM_DETAIL, MEDIA, job, json, mockBackend, renderApp, track } from "./helpers";

const PREVIEW: TrackSettingsPreview = {
  file: MEDIA.file,
  path: `/data/media/movies/Colour Test (2023)/${MEDIA.file}`,
  tracks: [
    { uid: "9001", label: "Audio 1: English", changes: ["Stop it being the default"] },
    { uid: "9002", label: "Audio 2: French", changes: ["Make it the default"] },
  ],
  hardlinked: false,
  free_space: 31 * 1024 ** 3,
};

// The page has both the table (computers) and the cards (phones); CSS shows one.
// The table comes first.
function first(role: string, name: string | RegExp) {
  return screen.getAllByRole(role, { name })[0];
}

function audioSwitch(name: string) {
  return first("switch", `Default: ${name}`);
}

describe("changing track settings", () => {
  it("works out only what differs from the file", () => {
    const tracks = [
      track(1, { default: true, name: "Main" }),
      track(2, { type: "subtitles", forced: false }),
    ];
    expect(changesFrom(tracks, {})).toEqual([]);
    expect(
      changesFrom(tracks, {
        "9001": { default: true, name: " Main " },
        "9002": { forced: true, default: false },
      }),
    ).toEqual([{ uid: "9002", forced: true }]);
    expect(changesFrom(tracks, { "9001": { default: false, name: "" } })).toEqual([
      { uid: "9001", default: false, name: "" },
    ]);
  });

  it("turning a default on turns the others of that kind off, and can be undone", async () => {
    mockBackend();
    renderApp("/films/5");
    await screen.findByText("2 h 14 min");
    expect(screen.queryByTestId("save-bar")).not.toBeInTheDocument();

    await userEvent.click(audioSwitch("Audio 2: French"));
    expect(audioSwitch("Audio 2: French")).toBeChecked();
    expect(audioSwitch("Audio 1: English")).not.toBeChecked();
    // Subtitles aren't affected by an audio change.
    expect(first("switch", "Forced: Subtitles 1: English")).toBeChecked();
    const bar = screen.getByTestId("save-bar");
    expect(bar).toHaveTextContent("2 tracks changed, not saved yet");

    await userEvent.click(within(bar).getByRole("button", { name: "Undo changes" }));
    expect(audioSwitch("Audio 1: English")).toBeChecked();
    expect(screen.queryByTestId("save-bar")).not.toBeInTheDocument();
  });

  it("forced is only a switch for subtitles", async () => {
    mockBackend();
    renderApp("/films/5");
    await screen.findByText("2 h 14 min");
    expect(screen.queryByRole("switch", { name: /^Forced: Audio/ })).not.toBeInTheDocument();
    expect(first("switch", "Forced: Subtitles 2: English")).not.toBeChecked();
  });

  it("renames a track", async () => {
    mockBackend();
    renderApp("/films/5");
    await screen.findByText("2 h 14 min");
    const audio = screen.getByRole("region", { name: /Audio/ });
    await userEvent.click(
      within(audio).getAllByRole("button", { name: "Rename Audio 2: French" })[0],
    );
    const box = screen.getByRole("textbox", { name: "Name of Audio 2: French" });
    await userEvent.clear(box);
    await userEvent.type(box, "French 5.1{Enter}");
    expect(within(audio).getByTestId("track-2")).toHaveTextContent("French 5.1");
    expect(screen.getByTestId("save-bar")).toHaveTextContent("1 track changed");
  });

  it("shows a summary, then saves and follows the job", async () => {
    const bodies: Record<string, unknown>[] = [];
    let polls = 0;
    mockBackend((url, init) => {
      if (url.endsWith("/track-settings/preview")) {
        bodies.push(JSON.parse(String(init?.body)));
        return json(PREVIEW);
      }
      if (url.endsWith("/api/films/5/track-settings")) {
        bodies.push(JSON.parse(String(init?.body)));
        return json(job(), 202);
      }
      if (url.endsWith("/api/jobs/42")) {
        polls += 1;
        return json(
          polls < 2
            ? job({ status: "running", step: "Saving the changes", step_number: 2, step_count: 3 })
            : job({ status: "done", message: "2 tracks changed." }),
        );
      }
      return undefined;
    });
    renderApp("/films/5");
    await screen.findByText("2 h 14 min");
    await userEvent.click(audioSwitch("Audio 2: French"));
    await userEvent.click(screen.getByRole("button", { name: "Save track changes" }));

    const dialog = await screen.findByRole("dialog", { name: "Change the original file?" });
    expect(within(dialog).getByTestId("summary-file")).toHaveTextContent(MEDIA.file);
    const list = within(dialog).getByRole("list", { name: "What will change" });
    expect(list).toHaveTextContent("Audio 1: English");
    expect(list).toHaveTextContent("Make it the default");
    expect(dialog).toHaveTextContent("31.0 GB free");
    expect(dialog).not.toHaveTextContent("also in your downloads");
    expect(bodies[0]).toEqual({
      file: MEDIA.file,
      changes: [
        { uid: "9001", default: false },
        { uid: "9002", default: true },
      ],
    });

    await userEvent.click(within(dialog).getByRole("button", { name: "Change the original file" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(bodies[1]).toMatchObject({ confirmed: true, allow_hardlinked: false });
    expect(
      await screen.findByText("Track changes saved", {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(screen.getByText("2 tracks changed.")).toBeInTheDocument();
    // The choices are now the file's own, so nothing is left to save.
    expect(screen.queryByTestId("save-bar")).not.toBeInTheDocument();
  });

  it("needs 'I understand' for a hardlinked file", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockBackend((url, init) => {
      if (url.endsWith("/track-settings/preview")) return json({ ...PREVIEW, hardlinked: true });
      if (url.endsWith("/api/films/5/track-settings")) {
        bodies.push(JSON.parse(String(init?.body)));
        return json(job(), 202);
      }
      if (url.endsWith("/api/jobs/42")) return json(job({ status: "running" }));
      return undefined;
    });
    renderApp("/films/5");
    await screen.findByText("2 h 14 min");
    await userEvent.click(audioSwitch("Audio 2: French"));
    await userEvent.click(screen.getByRole("button", { name: "Save track changes" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("This file is also in your downloads");
    const confirm = within(dialog).getByRole("button", { name: "Change the original file" });
    expect(confirm).toBeDisabled();
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /I understand/ }));
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() => expect(bodies[0]).toMatchObject({ allow_hardlinked: true }));
    // While the job runs the switches can't be changed.
    expect(await screen.findByText("Saving track changes")).toBeInTheDocument();
    expect(audioSwitch("Audio 1: English")).toBeDisabled();
  });

  it("cancel closes the summary without changing anything", async () => {
    let saved = false;
    mockBackend((url) => {
      if (url.endsWith("/track-settings/preview")) return json(PREVIEW);
      if (url.endsWith("/api/films/5/track-settings")) saved = true;
      return undefined;
    });
    renderApp("/films/5");
    await screen.findByText("2 h 14 min");
    await userEvent.click(audioSwitch("Audio 2: French"));
    await userEvent.click(screen.getByRole("button", { name: "Save track changes" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(saved).toBe(false);
    expect(screen.getByTestId("save-bar")).toBeInTheDocument(); // choices kept
  });

  it("explains a failed job and keeps the choices", async () => {
    mockBackend((url) => {
      if (url.endsWith("/track-settings/preview")) return json(PREVIEW);
      if (url.endsWith("/api/films/5/track-settings")) return json(job(), 202);
      if (url.endsWith("/api/jobs/42"))
        return json(
          job({
            status: "failed",
            error: "MKVToolNix couldn't save the changes.",
            error_details: "Error: disk full",
          }),
        );
      return undefined;
    });
    renderApp("/films/5");
    await screen.findByText("2 h 14 min");
    await userEvent.click(audioSwitch("Audio 2: French"));
    await userEvent.click(screen.getByRole("button", { name: "Save track changes" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Change the original file",
      }),
    );
    expect(await screen.findByText("Couldn't save the changes")).toBeInTheDocument();
    expect(screen.getByText("MKVToolNix couldn't save the changes.")).toBeInTheDocument();
    expect(screen.getByText("Show technical details")).toBeInTheDocument();
    expect(screen.getByTestId("save-bar")).toBeInTheDocument();
  });

  it("shows why the summary couldn't be made", async () => {
    mockBackend((url) =>
      url.endsWith("/track-settings/preview")
        ? json(
            { detail: "The tracks in this file have changed since you chose these settings." },
            409,
          )
        : undefined,
    );
    renderApp("/films/5");
    await screen.findByText("2 h 14 min");
    await userEvent.click(audioSwitch("Audio 2: French"));
    await userEvent.click(screen.getByRole("button", { name: "Save track changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("tracks in this file have changed");
  });

  it("files that aren't MKV can't be changed", async () => {
    mockBackend((url) =>
      url.endsWith("/api/films/5")
        ? json({
            ...FILM_DETAIL,
            files: [{ ...FILM_DETAIL.files[0], is_mkv: false }],
          })
        : undefined,
    );
    renderApp("/films/5");
    await screen.findByText("2 h 14 min");
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.getAllByText("Default: yes").length).toBeGreaterThan(0);
  });
});
