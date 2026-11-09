import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockBackend, renderApp } from "./helpers";

describe("navigation", () => {
  it("has the five sections in both the sidebar and the phone tab bar", () => {
    mockBackend();
    renderApp();
    const navs = screen.getAllByRole("navigation", { name: "Main" });
    expect(navs).toHaveLength(2);
    for (const nav of navs) {
      const labels = within(nav)
        .getAllByRole("link")
        .map((link) => link.textContent);
      expect(labels).toEqual(["Films", "TV", "Rules", "Queue", "Settings"]);
    }
  });

  it("opens Films by default and moves between pages", async () => {
    mockBackend();
    renderApp("/");
    expect(await screen.findByRole("heading", { level: 1, name: "Films" })).toBeInTheDocument();

    const sidebar = screen.getAllByRole("navigation", { name: "Main" })[0];
    await userEvent.click(within(sidebar).getByRole("link", { name: "Queue" }));
    expect(screen.getByRole("heading", { level: 1, name: "Queue" })).toBeInTheDocument();
    expect(within(sidebar).getByRole("link", { name: "Queue" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("shows the configured Films folder in the empty library", async () => {
    mockBackend();
    renderApp("/films");
    expect(await screen.findByText("/data/media/movies")).toBeInTheDocument();
  });

  it("shows a friendly page for unknown addresses", () => {
    mockBackend();
    renderApp("/nowhere");
    expect(screen.getByText("This page doesn't exist")).toBeInTheDocument();
  });
});
