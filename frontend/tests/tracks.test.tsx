import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Media } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import { explainHdr, summaryBadges } from "@/lib/hdr";

import { FILMS, MEDIA, json, mockBackend, renderApp, summary } from "./helpers";

function titlesShown() {
  return within(screen.getByRole("list", { name: "Films" }))
    .getAllByRole("link")
    .map((link) => link.querySelector("p")?.textContent);
}

describe("HDR words", () => {
  it("picks short badges for posters", () => {
    const dv = summary({ hdr: ["Dolby Vision", "HDR10"], dv_profile: "8.1", resolution: "4K" });
    expect(summaryBadges(dv).map((b) => b.label)).toEqual(["DV", "4K"]);
    expect(summaryBadges(dv)[0].title).toBe("Dolby Vision profile 8.1");
    expect(summaryBadges(summary({ hdr: ["HDR10+", "HDR10"] })).map((b) => b.label)).toEqual([
      "HDR10+",
    ]);
    expect(summaryBadges(summary({ hdr: ["HDR10"] })).map((b) => b.label)).toEqual(["HDR10"]);
    expect(summaryBadges(summary({ hdr: ["HLG"] })).map((b) => b.label)).toEqual(["HLG"]);
    expect(summaryBadges(summary())).toEqual([]);
    expect(summaryBadges(summary({ read: false, hdr: ["HDR10"] }))).toEqual([]);
  });

  it("explains each kind of picture in plain English", () => {
    const base = {
      dv_dual_layer: false,
      can_remove_dv: false,
      dv_profile: null,
      dv_fallback: null,
    };
    expect(explainHdr(null).title).toBe("Normal picture (SDR)");
    expect(explainHdr({ ...base, formats: ["HDR10"] }).title).toBe("HDR10");
    const p5 = explainHdr({ ...base, formats: ["Dolby Vision"], dv_profile: "5" });
    expect(p5.warning).toBe(true);
    expect(p5.text).toMatch(/wrong colours/);
    const p7 = explainHdr({
      ...base,
      formats: ["Dolby Vision", "HDR10"],
      dv_profile: "7",
      dv_fallback: "HDR10",
      dv_dual_layer: true,
    });
    expect(p7.title).toBe("Dolby Vision profile 7 with HDR10");
    expect(p7.text).toMatch(/UHD Blu-ray/);
    expect(p7.text).not.toMatch(/RPU|BL|EL/);
  });

  it("formats lengths", () => {
    expect(formatDuration(3)).toBe("3 seconds");
    expect(formatDuration(2700)).toBe("45 min");
    expect(formatDuration(8040)).toBe("2 h 14 min");
    expect(formatDuration(7200)).toBe("2 h");
  });
});

describe("films page HDR badges and filter", () => {
  it("shows DV, HDR10+, HDR10 and 4K badges on posters", async () => {
    mockBackend();
    renderApp("/films");
    const card = await screen.findByRole("link", { name: /^Colour Test/ });
    expect(within(card).getByText("Dolby Vision profile 8.1")).toBeInTheDocument();
    expect(within(card).getByText("DV")).toBeInTheDocument();
    expect(within(card).getByText("4K")).toBeInTheDocument();
    const arger = screen.getByRole("link", { name: /^Ärger im Paradies/ });
    expect(within(arger).getByText("HDR10+")).toBeInTheDocument();
    const bright = screen.getByRole("link", { name: /Bright Lights/ });
    expect(within(bright).getByText("HDR10")).toBeInTheDocument();
  });

  it("filters to films with Dolby Vision", async () => {
    mockBackend();
    renderApp("/films");
    const filter = await screen.findByRole("combobox", { name: "Show" });
    await userEvent.selectOptions(filter, "Has Dolby Vision");
    expect(titlesShown()).toEqual(["Colour Test"]);
    expect(screen.getByText("1 film found")).toBeInTheDocument();
    // One film hasn't been read yet, so the owner knows the list may grow.
    expect(screen.getByText(/still reading the details of 1 film/)).toBeInTheDocument();

    await userEvent.selectOptions(filter, "No HDR");
    expect(titlesShown()).toEqual(["The Long Weekend"]);
    await userEvent.selectOptions(filter, "Any HDR");
    expect(titlesShown()).toEqual(["Ärger im Paradies", "Bright Lights", "Colour Test"]);
    await userEvent.selectOptions(filter, "4K");
    expect(titlesShown()).toHaveLength(3);
  });

  it("explains an empty filter and can show everything again", async () => {
    mockBackend((url) =>
      url.endsWith("/api/films")
        ? json({ ...FILMS, films: FILMS.films.filter((f) => f.title !== "Colour Test") })
        : undefined,
    );
    renderApp("/films?show=dv");
    expect(await screen.findByText("No films: Has Dolby Vision")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show all films" }));
    expect(titlesShown()).toHaveLength(4);
  });

  it("shows progress while film details are being read", async () => {
    mockBackend((url) =>
      url.endsWith("/api/films")
        ? json({ ...FILMS, reading: { running: true, done: 120, total: 330 } })
        : undefined,
    );
    renderApp("/films");
    expect(await screen.findByText("Reading film details… 120 of 330")).toBeInTheDocument();
  });
});

describe("film page tracks", () => {
  it("shows the tracks grouped with friendly names", async () => {
    mockBackend();
    renderApp("/films/5");
    expect(await screen.findByText("2 h 14 min")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument(); // chapters
    expect(screen.getByText("1 picture")).toBeInTheDocument();
    expect(screen.getByTestId("hdr-note")).toHaveTextContent("Dolby Vision profile 8.1 with HDR10");

    const audio = screen.getByRole("region", { name: /Audio/ });
    const atmos = within(audio).getByTestId("track-1");
    expect(atmos).toHaveTextContent("English");
    expect(atmos).toHaveTextContent("Dolby TrueHD Atmos · 7.1");
    expect(within(atmos).getByRole("switch", { name: "Default: Audio 1: English" })).toBeChecked();
    expect(within(atmos).getByText("Original language")).toBeInTheDocument();
    expect(within(audio).getByTestId("track-2")).toHaveTextContent("French");

    const subs = screen.getByRole("region", { name: /Subtitles/ });
    const forced = within(subs).getByTestId("track-3");
    expect(forced).toHaveTextContent("PGS (picture-based)");
    expect(
      within(forced).getByRole("switch", { name: "Forced: Subtitles 1: English" }),
    ).toBeChecked();
    expect(within(subs).getByTestId("track-4")).toHaveTextContent("SDH");

    const video = screen.getByRole("region", { name: /Video/ });
    expect(within(video).getByTestId("track-0")).toHaveTextContent("3840 × 2160 · 23.976 fps");
    // No raw tool words.
    expect(document.body.textContent).not.toMatch(/A_TRUEHD|dvhe|RPU/);
  });

  it("switches between the film's files", async () => {
    const calls: string[] = [];
    mockBackend((url) => {
      if (url.includes("/media")) calls.push(url);
      return undefined;
    });
    renderApp("/films/5");
    const choice = await screen.findByRole("combobox", { name: "File" });
    await screen.findByText("2 h 14 min");
    await userEvent.selectOptions(
      choice,
      "Copy: Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10.mkv",
    );
    await screen.findByText("2 h 14 min");
    expect(calls.at(-1)).toContain(encodeURIComponent(" - HDR10.mkv").replace(/%20/g, "+"));
  });

  it("warns about Dolby Vision profile 5", async () => {
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
    renderApp("/films/5");
    const note = await screen.findByTestId("hdr-note");
    expect(note).toHaveTextContent("Dolby Vision profile 5");
    expect(note).toHaveTextContent("can't make a copy without Dolby Vision");
  });

  it("explains a file that can't be read, with technical details and a retry", async () => {
    const broken: Media = {
      ...MEDIA,
      error: "Tailarr couldn't read the tracks in this file.",
      error_details: "Error: the file could not be opened",
      tracks: [],
      hdr: null,
    };
    let refreshed = false;
    mockBackend((url) => {
      if (!url.includes("/media")) return undefined;
      if (url.includes("refresh=true")) {
        refreshed = true;
        return json(MEDIA);
      }
      return json(broken);
    });
    renderApp("/films/5");
    expect(await screen.findByText("Tailarr couldn't look inside this file")).toBeInTheDocument();
    expect(screen.getByText("Show technical details")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("2 h 14 min")).toBeInTheDocument();
    expect(refreshed).toBe(true);
  });
});
