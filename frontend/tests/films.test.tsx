import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { formatSize, timeAgo } from "@/lib/format";

import { FILMS, json, mockBackend, renderApp } from "./helpers";

function titlesShown() {
  return within(screen.getByRole("list", { name: "Films" }))
    .getAllByRole("link")
    .map((link) => link.querySelector("p")?.textContent);
}

describe("films library", () => {
  it("shows every film as a poster card, sorted by title", async () => {
    mockBackend();
    renderApp("/films");
    expect(await screen.findByText("Bright Lights")).toBeInTheDocument();
    expect(titlesShown()).toEqual([
      "Ärger im Paradies",
      "Bright Lights",
      "Colour Test",
      "The Long Weekend",
      "Old Home Video",
    ]);
    expect(screen.getByText(/5 films · 15\.0 GB/)).toBeInTheDocument();
    expect(screen.getByText("Last checked 5 minutes ago")).toBeInTheDocument();
    // A film without artwork gets a placeholder; non-MKV files are marked.
    expect(screen.getAllByTestId("poster-placeholder")).toHaveLength(4);
    expect(screen.getByText("Not MKV")).toBeInTheDocument();
  });

  it("searches titles, ignoring case and accents", async () => {
    mockBackend();
    renderApp("/films");
    const search = await screen.findByRole("searchbox", { name: "Search films" });
    await userEvent.type(search, "arger");
    expect(titlesShown()).toEqual(["Ärger im Paradies"]);
    expect(screen.getByText("1 film found")).toBeInTheDocument();

    await userEvent.clear(search);
    await userEvent.type(search, "1999");
    expect(titlesShown()).toEqual(["The Long Weekend"]);
  });

  it("explains when nothing matches and can clear the search", async () => {
    mockBackend();
    renderApp("/films?q=zzz");
    expect(await screen.findByText("No films match “zzz”")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(titlesShown()).toHaveLength(5);
  });

  it("sorts by date added and by size", async () => {
    mockBackend();
    renderApp("/films");
    const sort = await screen.findByRole("combobox", { name: "Sort films" });
    await userEvent.selectOptions(sort, "Recently added");
    expect(titlesShown()[0]).toBe("Colour Test");
    await userEvent.selectOptions(sort, "Largest first");
    expect(titlesShown()).toEqual([
      "Colour Test",
      "Old Home Video",
      "Ärger im Paradies",
      "The Long Weekend",
      "Bright Lights",
    ]);
  });

  it("switches to a list and remembers the choice", async () => {
    mockBackend();
    renderApp("/films");
    await screen.findByText("Bright Lights");
    await userEvent.click(screen.getByRole("button", { name: "List" }));
    expect(screen.getByRole("button", { name: "List" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByText(/Added /).length).toBeGreaterThan(0);
    expect(localStorage.getItem("tailarr-films-view")).toBe("list");
  });

  it("asks Tailarr to look for new films", async () => {
    let scans = 0;
    mockBackend((url, init) => {
      if (url.endsWith("/api/films/scan") && init?.method === "POST") {
        scans += 1;
        return json({ ...FILMS.scan, running: true }, 202);
      }
      return undefined;
    });
    renderApp("/films");
    await userEvent.click(await screen.findByRole("button", { name: /Check for new films/ }));
    expect(scans).toBe(1);
  });

  it("explains a missing Films folder and links to Settings", async () => {
    mockBackend((url) =>
      url.endsWith("/api/films")
        ? json({
            ...FILMS,
            films: [],
            scan: { ...FILMS.scan, error: "Tailarr can't find your Films folder at /nope." },
          })
        : undefined,
    );
    renderApp("/films");
    expect(await screen.findByText("Tailarr can't see your films")).toBeInTheDocument();
    expect(screen.getByText(/can't find your Films folder at \/nope/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Settings" })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("says when the folder has no films", async () => {
    mockBackend((url) => (url.endsWith("/api/films") ? json({ ...FILMS, films: [] }) : undefined));
    renderApp("/films");
    expect(await screen.findByText("No films found")).toBeInTheDocument();
    expect(screen.getByText("/data/media/movies")).toBeInTheDocument();
  });

  it("shows a friendly message during the very first scan", async () => {
    mockBackend((url) =>
      url.endsWith("/api/films")
        ? json({ ...FILMS, films: [], scan: { ...FILMS.scan, running: true, finished_at: null } })
        : undefined,
    );
    renderApp("/films");
    expect(await screen.findByText("Looking for your films…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Checking…/ })).toBeDisabled();
  });

  it("warns when the last check failed but keeps showing films", async () => {
    mockBackend((url) =>
      url.endsWith("/api/films")
        ? json({ ...FILMS, scan: { ...FILMS.scan, error: "Couldn't read the folder." } })
        : undefined,
    );
    renderApp("/films");
    expect(await screen.findByRole("alert")).toHaveTextContent("The last check didn't work.");
    expect(screen.getByText("Bright Lights")).toBeInTheDocument();
  });
});

describe("film page", () => {
  it("opens from the library and lists the files", async () => {
    mockBackend();
    renderApp("/films");
    await userEvent.click(await screen.findByRole("link", { name: /Colour Test/ }));
    expect(await screen.findByRole("heading", { level: 1, name: /Colour Test/ })).toBeVisible();
    expect(screen.getByText("Main file")).toBeInTheDocument();
    expect(screen.getByText("Copy made by Tailarr")).toBeInTheDocument();
    expect(screen.getByText("Also in your downloads")).toBeInTheDocument();
    expect(screen.getByText(/still seeding/)).toBeInTheDocument();
  });

  it("explains when a film has gone", async () => {
    mockBackend((url) =>
      url.endsWith("/api/films/77")
        ? json({ detail: "This film isn't in your library any more." }, 404)
        : undefined,
    );
    renderApp("/films/77");
    expect(await screen.findByText("Film not found")).toBeInTheDocument();
    expect(screen.getByText("This film isn't in your library any more.")).toBeInTheDocument();
  });
});

describe("formatting", () => {
  it("formats sizes and times in plain words", () => {
    expect(formatSize(512)).toBe("512 bytes");
    expect(formatSize(1536)).toBe("1.5 KB");
    expect(formatSize(48.2 * 1024 ** 3)).toBe("48.2 GB");
    expect(formatSize(3.5 * 1024 ** 4)).toBe("3.5 TB");
    const now = Date.parse("2026-11-09T12:00:00Z");
    expect(timeAgo("2026-11-09T11:59:30Z", now)).toBe("just now");
    expect(timeAgo("2026-11-09T11:59:00Z", now)).toBe("1 minute ago");
    expect(timeAgo("2026-11-09T09:00:00Z", now)).toBe("3 hours ago");
    expect(timeAgo("2026-11-07T12:00:00Z", now)).toBe("2 days ago");
  });
});

describe("changing many films", () => {
  it("chooses films with tick boxes, then previews the change", async () => {
    const sent: { film_ids: number[] }[] = [];
    mockBackend((url, init) => {
      if (url.endsWith("/api/films/batch/preview")) {
        sent.push(JSON.parse(String(init?.body)));
        return json({
          title: "x",
          action: "Make a copy without Dolby Vision (HDR10 copy)",
          scope: "2 films",
          changes_originals: false,
          files: [],
          will_run: 0,
          skipped: 0,
          hardlinked_skipped: 0,
          flagged: 0,
          copies: 0,
          space: [],
          enough_space: true,
        });
      }
      return undefined;
    });
    renderApp("/films");
    await userEvent.click(await screen.findByRole("button", { name: /Choose films to change/ }));
    const boxes = screen.getAllByRole("checkbox", { name: /^Select / });
    expect(boxes.length).toBeGreaterThan(1);
    // While choosing, cards don't open the film.
    expect(within(screen.getByRole("list", { name: "Films" })).queryAllByRole("link")).toHaveLength(
      0,
    );
    await userEvent.click(boxes[0]);
    expect(boxes[0]).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("selection-bar")).toHaveTextContent("1 film selected");
    await userEvent.click(screen.getByRole("button", { name: /^Select all/ }));
    expect(screen.getByTestId("selection-bar")).toHaveTextContent(`${boxes.length} films selected`);
    await userEvent.click(screen.getByRole("button", { name: "Deselect all" }));
    expect(screen.getByRole("button", { name: /^Change 0 films/ })).toBeDisabled();
    await userEvent.click(boxes[0]);
    await userEvent.click(boxes[1]);
    await userEvent.click(screen.getByRole("button", { name: "Change 2 films…" }));
    const dialog = await screen.findByRole("dialog", { name: "Change 2 films" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Show what will happen" }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].film_ids).toHaveLength(2);
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByTestId("selection-bar")).toBeNull();
  });
});
