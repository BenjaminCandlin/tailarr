import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { spaceText } from "@/components/ReplaceOriginalDialog";
import type { RemoveTracksPreview, ReplaceOriginalPreview } from "@/lib/api";

import { FILM_DETAIL, MEDIA, job, json, mockBackend, renderApp } from "./helpers";

const COPY = "Colour Test (2023) WEBDL-2160p DV HDR10 - Tailarr.mkv";

const PREVIEW: RemoveTracksPreview = {
  film_id: 5,
  file: MEDIA.file,
  new_file: COPY,
  exists: false,
  updates_copy: false,
  removed: ["Audio 2: French – Dolby Digital, 5.1, “Français”"],
  kept: ["Video 1 – HEVC (H.265)", "Audio 1: English – Dolby TrueHD Atmos, 7.1"],
  settings: [],
  warnings: [],
  space_needed: 5 * 1024 ** 3,
  free_space: 31 * 1024 ** 3,
  enough_space: true,
};

const REPLACE: ReplaceOriginalPreview = {
  film_id: 5,
  original: MEDIA.file,
  original_size: 4 * 1024 ** 3,
  copy_file: COPY,
  copy_size: 3 * 1024 ** 3,
  hardlinked: true,
  keep_days: 30,
  recycle_folder: "/data/media/movies/Colour Test (2023)/.tailarr-recycle",
};

// The page has both the table (computers) and the cards (phones); the table comes first.
function first(role: string, name: string | RegExp) {
  return screen.getAllByRole(role, { name })[0];
}

async function openFilm() {
  renderApp("/films/5");
  await screen.findByText("2 h 14 min");
}

describe("removing tracks", () => {
  it("has a Keep tick for audio and subtitles, but not video", async () => {
    mockBackend();
    await openFilm();
    expect(first("checkbox", "Keep Audio 1: English")).toBeChecked();
    expect(first("checkbox", "Keep Subtitles 2: English")).toBeChecked();
    expect(screen.queryByRole("checkbox", { name: /Keep Video/ })).not.toBeInTheDocument();
  });

  it("unticking a track offers a copy instead of changing the original", async () => {
    mockBackend();
    await openFilm();
    await userEvent.click(first("checkbox", "Keep Audio 2: French"));
    const bar = screen.getByTestId("save-bar");
    expect(bar).toHaveTextContent("1 track left out");
    expect(bar).toHaveTextContent("Your original stays as it is");
    expect(
      within(bar).getByRole("button", { name: "Save a copy without the unticked tracks" }),
    ).toBeInTheDocument();
    expect(within(bar).queryByRole("button", { name: "Save track changes" })).toBeNull();

    // Setting changes are counted too, and Undo puts everything back.
    await userEvent.click(first("switch", "Forced: Subtitles 2: English"));
    expect(bar).toHaveTextContent("1 track left out, 1 track changed");
    await userEvent.click(within(bar).getByRole("button", { name: "Undo changes" }));
    expect(first("checkbox", "Keep Audio 2: French")).toBeChecked();
    expect(screen.queryByTestId("save-bar")).not.toBeInTheDocument();
  });

  it("shows a summary, makes the copy and offers what to do next", async () => {
    const bodies: Record<string, unknown>[] = [];
    let polls = 0;
    mockBackend((url, init) => {
      if (url.endsWith("/remove-tracks/preview")) {
        bodies.push(JSON.parse(String(init?.body)));
        return json({
          ...PREVIEW,
          settings: [{ label: "Subtitles 2: English", changes: ["Mark it as forced"] }],
          warnings: ["None of the audio tracks left is marked as the default."],
        });
      }
      if (url.endsWith("/api/films/5/remove-tracks")) {
        bodies.push(JSON.parse(String(init?.body)));
        return json(job({ kind: "remove_tracks" }), 202);
      }
      if (url.endsWith("/api/jobs/42")) {
        polls += 1;
        return json(
          polls < 2
            ? job({ status: "running", step: "Making the copy", step_number: 2, progress: 40 })
            : job({
                status: "done",
                message: `Copy saved as “${COPY}” (1 track left out).`,
                result: { copy: COPY, source: MEDIA.file },
              }),
        );
      }
      if (url.endsWith("/replace-original/preview")) return json(REPLACE);
      return undefined;
    });
    await openFilm();
    await userEvent.click(first("checkbox", "Keep Audio 2: French"));
    await userEvent.click(first("switch", "Forced: Subtitles 2: English"));
    // A change to a track that's left out isn't sent.
    await userEvent.click(first("switch", "Default: Audio 2: French"));
    await userEvent.click(
      screen.getByRole("button", { name: "Save a copy without the unticked tracks" }),
    );

    const dialog = await screen.findByRole("dialog", { name: "Make a copy without these tracks?" });
    expect(within(dialog).getByTestId("summary-new-file")).toHaveTextContent(COPY);
    expect(within(dialog).getByRole("list", { name: "Left out of the copy" })).toHaveTextContent(
      "Audio 2: French",
    );
    expect(dialog).toHaveTextContent("Also changed in the copy");
    expect(dialog).toHaveTextContent("None of the audio tracks left is marked as the default.");
    expect(dialog).toHaveTextContent("needs up to 5.0 GB, 31.0 GB free");
    expect(bodies[0]).toEqual({
      file: MEDIA.file,
      remove: ["9002"],
      changes: [
        { uid: "9001", default: false },
        { uid: "9004", forced: true },
      ],
    });

    await userEvent.click(within(dialog).getByRole("button", { name: "Make the copy" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(bodies[1]).toMatchObject({ confirmed: true, overwrite: false, remove: ["9002"] });
    expect(await screen.findByText("Copy saved", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByTestId("save-bar")).not.toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Replace the original with this copy…" }),
    );
    const replace = await screen.findByRole("dialog", {
      name: "Replace the original with this copy?",
    });
    expect(await within(replace).findByTestId("replace-copy")).toHaveTextContent(COPY);
    expect(within(replace).getByTestId("replace-original")).toHaveTextContent(MEDIA.file);
  });

  it("asks before replacing an existing copy", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockBackend((url, init) => {
      if (url.endsWith("/remove-tracks/preview")) return json({ ...PREVIEW, exists: true });
      if (url.endsWith("/api/films/5/remove-tracks")) {
        bodies.push(JSON.parse(String(init?.body)));
        return json(job({ kind: "remove_tracks", status: "running" }), 202);
      }
      if (url.endsWith("/api/jobs/42")) return json(job({ status: "running" }));
      return undefined;
    });
    await openFilm();
    await userEvent.click(first("checkbox", "Keep Audio 2: French"));
    await userEvent.click(
      screen.getByRole("button", { name: "Save a copy without the unticked tracks" }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("A copy with this name is already there.");
    const confirm = within(dialog).getByRole("button", { name: "Make the copy" });
    expect(confirm).toBeDisabled();
    await userEvent.click(
      within(dialog).getByRole("checkbox", { name: "Replace the existing copy" }),
    );
    await userEvent.click(confirm);
    await waitFor(() => expect(bodies[0]).toMatchObject({ overwrite: true }));
    // While the copy is being made the choices can't be changed.
    expect(await screen.findByText("Making the copy")).toBeInTheDocument();
    expect(first("checkbox", "Keep Audio 1: English")).toBeDisabled();
  });

  it("won't start without enough disk space", async () => {
    mockBackend((url) =>
      url.endsWith("/remove-tracks/preview")
        ? json({ ...PREVIEW, enough_space: false, free_space: 1024 ** 3 })
        : undefined,
    );
    await openFilm();
    await userEvent.click(first("checkbox", "Keep Audio 2: French"));
    await userEvent.click(
      screen.getByRole("button", { name: "Save a copy without the unticked tracks" }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Not enough free space on the disk");
    expect(within(dialog).getByRole("button", { name: "Make the copy" })).toBeDisabled();
  });

  it("updating Tailarr's own copy is said plainly", async () => {
    mockBackend((url) =>
      url.endsWith("/remove-tracks/preview")
        ? json({ ...PREVIEW, exists: true, updates_copy: true, file: COPY })
        : undefined,
    );
    await openFilm();
    await userEvent.click(first("checkbox", "Keep Audio 2: French"));
    await userEvent.click(
      screen.getByRole("button", { name: "Save a copy without the unticked tracks" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Update this copy?" });
    expect(within(dialog).getByRole("button", { name: "Update the copy" })).toBeEnabled();
  });
});

describe("replacing the original", () => {
  it("explains disk space: the whole original is freed, not just the difference", () => {
    const gb = 1024 ** 3;
    const preview = {
      ...REPLACE,
      hardlinked: false,
      original_size: 7.8 * gb,
      copy_size: 7.8 * gb - 1.1 * 1024 ** 2,
    };
    expect(spaceText(preview)).toBe(
      "Right now the original and the copy take up 15.6 GB together. When the recycle folder " +
        "is emptied, the original's 7.8 GB is freed, leaving just the copy. The copy is 1.1 MB " +
        "smaller than the original, because of the tracks you left out.",
    );
    expect(spaceText({ ...preview, hardlinked: true })).toMatch(
      /its 7\.8 GB is only freed once the recycle folder is emptied and the torrent is removed/,
    );
  });

  const withCopy = {
    ...FILM_DETAIL,
    files: [
      FILM_DETAIL.files[0],
      { ...FILM_DETAIL.files[1], name: COPY, copy_of: MEDIA.file, can_replace_original: true },
    ],
  };

  it("needs a clear 'I understand', then follows the job", async () => {
    let replaced = false;
    mockBackend((url, init) => {
      if (url.endsWith("/api/films/5")) return json(withCopy);
      if (url.endsWith("/replace-original/preview")) return json(REPLACE);
      if (url.endsWith("/api/films/5/replace-original") && init?.method === "POST") {
        replaced = true;
        expect(JSON.parse(String(init.body))).toEqual({
          copy_file: COPY,
          confirmed: true,
          understood: true,
        });
        return json(job({ kind: "replace_original" }), 202);
      }
      if (url.endsWith("/api/jobs/42"))
        return json(
          job({
            kind: "replace_original",
            status: "done",
            message: "The original was replaced with the copy.",
          }),
        );
      return undefined;
    });
    await openFilm();
    expect(screen.getByText(`Made from ${MEDIA.file}`)).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Replace the original with this copy…" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Replace the original with this copy?",
    });
    await within(dialog).findByTestId("replace-copy");
    expect(dialog).toHaveTextContent("deleted after 30 days");
    expect(dialog).toHaveTextContent(".tailarr-recycle");
    expect(dialog).toHaveTextContent("The original is also in your downloads");
    const confirm = within(dialog).getByRole("button", { name: "Replace the original" });
    expect(confirm).toBeDisabled();
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /I understand/ }));
    await userEvent.click(confirm);
    expect(await screen.findByText("Original replaced", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(replaced).toBe(true);
    await userEvent.click(screen.getByText("Close", { selector: "button" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("explains why a copy can't replace the original", async () => {
    mockBackend((url) => {
      if (url.endsWith("/api/films/5")) return json(withCopy);
      if (url.endsWith("/replace-original/preview"))
        return json({ detail: "The original file has changed since this copy was made." }, 409);
      return undefined;
    });
    await openFilm();
    await userEvent.click(
      screen.getByRole("button", { name: "Replace the original with this copy…" }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("has changed since");
    expect(within(dialog).getByRole("button", { name: "Replace the original" })).toBeDisabled();
  });

  it("copies Tailarr can't vouch for have no replace button", async () => {
    mockBackend();
    await openFilm();
    expect(screen.queryByRole("button", { name: /Replace the original/ })).toBeNull();
  });
});

describe("recycle setting", () => {
  it("shows what's waiting and saves the keep period", async () => {
    const saved: unknown[] = [];
    mockBackend((url, init) => {
      if (url.endsWith("/api/settings/recycle")) {
        if (init?.method === "PUT") {
          saved.push(JSON.parse(String(init.body)));
          return json({ keep_days: 14, file_count: 2, total_size: 8 * 1024 ** 3 });
        }
        return json({ keep_days: 30, file_count: 2, total_size: 8 * 1024 ** 3 });
      }
      return undefined;
    });
    renderApp("/settings");
    const box = await screen.findByRole("spinbutton", { name: /Keep replaced originals/ });
    expect(screen.getByTestId("recycle-contents")).toHaveTextContent(
      "2 originals waiting, using 8.0 GB",
    );
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    await userEvent.clear(box);
    await userEvent.type(box, "0");
    expect(save).toBeDisabled(); // must be 1 to 365
    await userEvent.clear(box);
    await userEvent.type(box, "14");
    await userEvent.click(save);
    await waitFor(() => expect(saved).toEqual([{ keep_days: 14 }]));
  });
});
