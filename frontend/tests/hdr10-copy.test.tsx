import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Hdr10CopyPreview, Media } from "@/lib/api";

import { MEDIA, job, json, mockBackend, renderApp } from "./helpers";

const COPY = "Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10.mkv";

const PREVIEW: Hdr10CopyPreview = {
  file: MEDIA.file,
  new_file: COPY,
  exists: false,
  dv_profile: "8.1",
  blu_ray_layers: false,
  result: ["HDR10"],
  kept: ["Audio 1: English – Dolby TrueHD Atmos, 7.1", "Audio 2: French – Dolby Digital, 5.1"],
  kept_counts: { video: 0, audio: 2, subtitles: 0 },
  removed: [],
  settings: [],
  warnings: [],
  chapters: 12,
  attachments: 1,
  uses_work_folder: false,
  space: [
    {
      label: "the disk with your films",
      needed: 9 * 1024 ** 3,
      free: 31 * 1024 ** 3,
      enough: true,
    },
  ],
  enough_space: true,
};

async function openFilm() {
  renderApp("/films/5");
  await screen.findByText("2 h 14 min");
}

async function askForCopy() {
  await userEvent.click(screen.getByRole("button", { name: "Make an HDR10 copy…" }));
  return screen.findByRole("dialog", { name: "Make a copy without Dolby Vision?" });
}

describe("making a copy without Dolby Vision", () => {
  it("is offered for Dolby Vision files, with a plain explanation", async () => {
    mockBackend();
    await openFilm();
    const action = screen.getByTestId("dv-action");
    expect(action).toHaveTextContent("Make a copy without Dolby Vision");
    expect(action).toHaveTextContent("show Dolby Vision with the wrong colours");
    expect(action).toHaveTextContent("Your original stays as it is.");
  });

  it("isn't offered for files without Dolby Vision", async () => {
    mockBackend((url) =>
      url.includes("/media") ? json({ ...MEDIA, hdr: null } satisfies Media) : undefined,
    );
    await openFilm();
    expect(screen.queryByTestId("dv-action")).not.toBeInTheDocument();
  });

  it("explains why profile 5 can't be done", async () => {
    const p5: Media = {
      ...MEDIA,
      hdr: {
        formats: ["Dolby Vision"],
        dv_profile: "5",
        dv_fallback: null,
        dv_dual_layer: false,
        can_remove_dv: false,
      },
    };
    mockBackend((url) => (url.includes("/media") ? json(p5) : undefined));
    await openFilm();
    expect(screen.getByTestId("dv-not-possible")).toHaveTextContent(
      "profile 5 has no HDR10 picture underneath",
    );
    expect(screen.queryByRole("button", { name: "Make an HDR10 copy…" })).toBeNull();
  });

  it("shows a summary, makes the copy and offers to show it", async () => {
    const bodies: unknown[] = [];
    let polls = 0;
    mockBackend((url, init) => {
      if (url.endsWith("/hdr10-copy/preview")) {
        bodies.push(JSON.parse(String(init?.body)));
        return json({ ...PREVIEW, blu_ray_layers: true, dv_profile: "7" });
      }
      if (url.endsWith("/api/films/5/hdr10-copy")) {
        bodies.push(JSON.parse(String(init?.body)));
        return json(job({ kind: "hdr10_copy" }), 202);
      }
      if (url.endsWith("/api/jobs/42")) {
        polls += 1;
        return json(
          polls < 2
            ? job({
                status: "running",
                step: "Removing Dolby Vision",
                step_number: 3,
                step_count: 6,
              })
            : job({
                status: "done",
                message: `HDR10 copy saved as “${COPY}”.`,
                result: { copy: COPY, source: MEDIA.file },
              }),
        );
      }
      return undefined;
    });
    await openFilm();
    const dialog = await askForCopy();
    expect(within(dialog).getByTestId("hdr10-new-file")).toHaveTextContent(COPY);
    const steps = within(dialog).getByRole("list", { name: "What happens" });
    expect(steps).toHaveTextContent("profile 7");
    expect(steps).toHaveTextContent("together with the extra Blu-ray picture layer");
    expect(steps).toHaveTextContent("nothing is re-encoded");
    expect(steps).toHaveTextContent("show the copy as HDR10");
    expect(steps).toHaveTextContent(
      "Everything else comes across: 2 audio tracks, no subtitle tracks, 12 chapters, 1 attachment",
    );
    expect(within(dialog).getByTestId("hdr10-space")).toHaveTextContent(
      "Disk space on the disk with your films: needs up to 9.0 GB, 31.0 GB free.",
    );
    expect(dialog).not.toHaveTextContent(/RPU|enhancement|BL\b|EL\b/);
    expect(bodies[0]).toEqual({ file: MEDIA.file });

    await userEvent.click(within(dialog).getByRole("button", { name: "Make the HDR10 copy" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(bodies[1]).toEqual({ file: MEDIA.file, confirmed: true, overwrite: false });
    expect(await screen.findByText("HDR10 copy saved", {}, { timeout: 4000 })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show the copy" }));
    expect(screen.getByRole("combobox", { name: "File" })).toHaveValue(COPY);
  });

  it("asks before replacing an existing HDR10 copy", async () => {
    const bodies: unknown[] = [];
    mockBackend((url, init) => {
      if (url.endsWith("/hdr10-copy/preview")) return json({ ...PREVIEW, exists: true });
      if (url.endsWith("/api/films/5/hdr10-copy")) {
        bodies.push(JSON.parse(String(init?.body)));
        return json(job({ kind: "hdr10_copy" }), 202);
      }
      if (url.endsWith("/api/jobs/42")) return json(job({ status: "running" }));
      return undefined;
    });
    await openFilm();
    const dialog = await askForCopy();
    expect(dialog).toHaveTextContent("An HDR10 copy is already there.");
    const confirm = within(dialog).getByRole("button", { name: "Make the HDR10 copy" });
    expect(confirm).toBeDisabled();
    await userEvent.click(
      within(dialog).getByRole("checkbox", { name: "Replace the existing copy" }),
    );
    await userEvent.click(confirm);
    await waitFor(() => expect(bodies[0]).toMatchObject({ overwrite: true }));
    expect(await screen.findByText("Making the HDR10 copy")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Make an HDR10 copy…" })).toBeDisabled();
  });

  it("won't start without enough space, and says where", async () => {
    mockBackend((url) =>
      url.endsWith("/hdr10-copy/preview")
        ? json({
            ...PREVIEW,
            uses_work_folder: true,
            space: [
              {
                label: "the work folder",
                needed: 9 * 1024 ** 3,
                free: 2 * 1024 ** 3,
                enough: false,
              },
              PREVIEW.space[0],
            ],
            enough_space: false,
          })
        : undefined,
    );
    await openFilm();
    const dialog = await askForCopy();
    expect(dialog).toHaveTextContent("Not enough free space on the work folder");
    expect(dialog).toHaveTextContent("Working files go in the work folder");
    expect(within(dialog).getByRole("button", { name: "Make the HDR10 copy" })).toBeDisabled();
  });

  it("explains a refusal from the server", async () => {
    mockBackend((url) =>
      url.endsWith("/hdr10-copy/preview")
        ? json({ detail: "This file has no Dolby Vision, so there's nothing to remove." }, 400)
        : undefined,
    );
    await openFilm();
    await userEvent.click(screen.getByRole("button", { name: "Make an HDR10 copy…" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("nothing to remove");
  });

  it("removes Dolby Vision and tracks in one go", async () => {
    const bodies: { remove?: string[]; confirmed?: boolean }[] = [];
    mockBackend((url, init) => {
      if (url.endsWith("/hdr10-copy/preview")) {
        bodies.push(JSON.parse(String(init?.body)));
        return json({
          ...PREVIEW,
          kept: ["Audio 1: English – Dolby TrueHD Atmos, 7.1"],
          kept_counts: { video: 0, audio: 1, subtitles: 0 },
          removed: ["Audio 2: French – Dolby Digital, 5.1"],
        });
      }
      if (url.endsWith("/hdr10-copy")) {
        bodies.push(JSON.parse(String(init?.body)));
        return json(job({ id: 8, kind: "hdr10_copy" }), 202);
      }
      return undefined;
    });
    await openFilm();
    const frenchKeep = screen.getAllByRole("checkbox", { name: "Keep Audio 2: French" })[0];
    await userEvent.click(frenchKeep);
    await userEvent.click(screen.getByRole("checkbox", { name: /Also remove Dolby Vision/ }));
    await userEvent.click(
      screen.getByRole("button", { name: "Save an HDR10 copy with these changes" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Make an HDR10 copy with these changes?",
    });
    expect(within(dialog).getByLabelText("Also left out")).toHaveTextContent("Audio 2: French");
    // Only what's kept is described as coming across.
    expect(within(dialog).getByTestId("hdr10-kept")).toHaveTextContent(
      "Comes across (everything except the tracks left out below): 1 audio track, no subtitle tracks",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Make the copy" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[0].remove).toHaveLength(1);
    expect(bodies[1]).toMatchObject({ confirmed: true, remove: bodies[0].remove });
  });
});
