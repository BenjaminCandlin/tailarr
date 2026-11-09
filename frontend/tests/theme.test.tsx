import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockBackend, renderApp } from "./helpers";

const isDark = () => document.documentElement.classList.contains("dark");

describe("theme", () => {
  it("is dark by default", () => {
    mockBackend();
    renderApp("/settings");
    expect(isDark()).toBe(true);
    expect(screen.getByRole("radio", { name: /dark/i })).toHaveAttribute("aria-checked", "true");
  });

  it("switches to light and remembers the choice", async () => {
    mockBackend();
    renderApp("/settings");
    await userEvent.click(screen.getByRole("radio", { name: /light/i }));
    expect(isDark()).toBe(false);
    expect(localStorage.getItem("tailarr-theme")).toBe("light");
  });

  it("can follow the device setting", async () => {
    (window as { __prefersLight?: boolean }).__prefersLight = true;
    try {
      mockBackend();
      renderApp("/settings");
      await userEvent.click(screen.getByRole("radio", { name: /match my device/i }));
      expect(isDark()).toBe(false);
      expect(localStorage.getItem("tailarr-theme")).toBe("system");
    } finally {
      (window as { __prefersLight?: boolean }).__prefersLight = false;
    }
  });

  it("starts with a saved choice", () => {
    localStorage.setItem("tailarr-theme", "light");
    mockBackend();
    renderApp("/settings");
    expect(isDark()).toBe(false);
  });
});
