/**
 * Accessibility check of every main page with axe-core, in both themes: no serious or
 * critical problems (contrast, labels, names, structure).
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const PAGES: { name: string; path: string; ready: (page: Page) => Promise<void> }[] = [
  {
    name: "Films",
    path: "/films",
    ready: (p) => expect(p.getByRole("list", { name: "Films" })).toBeVisible(),
  },
  {
    name: "Film detail",
    path: "/films",
    ready: async (p) => {
      await p.getByRole("list", { name: "Films" }).getByRole("link", { name: /Bright Lights/ }).click();
      await expect(p.getByText("What's inside")).toBeVisible();
      await expect(p.getByTestId("hdr-note")).toBeVisible();
    },
  },
  {
    name: "TV",
    path: "/tv",
    ready: (p) => expect(p.getByRole("list", { name: "Shows" })).toBeVisible(),
  },
  {
    name: "Show",
    path: "/tv",
    ready: async (p) => {
      await p.getByRole("list", { name: "Shows" }).getByRole("link", { name: /Another Show/ }).click();
      await expect(p.getByRole("heading", { name: "Season 1" })).toBeVisible();
    },
  },
  {
    name: "Rules",
    path: "/rules",
    ready: (p) => expect(p.getByRole("heading", { level: 1, name: "Rules" })).toBeVisible(),
  },
  {
    name: "Rule editor",
    path: "/rules/new?example=1",
    ready: (p) => expect(p.getByLabel("Rule name")).toBeVisible(),
  },
  {
    name: "Queue",
    path: "/queue",
    ready: (p) => expect(p.getByRole("heading", { level: 1, name: "Queue" })).toBeVisible(),
  },
  {
    name: "Activity",
    path: "/activity",
    ready: (p) => expect(p.getByRole("heading", { level: 1, name: "Activity log" })).toBeVisible(),
  },
  {
    name: "Settings",
    path: "/settings",
    ready: (p) => expect(p.getByTestId("connection-radarr")).toBeVisible(),
  },
];

for (const theme of ["dark", "light"] as const) {
  for (const { name, path, ready } of PAGES) {
    test(`${name} page has no serious accessibility problems (${theme})`, async ({ page }) => {
      await page.addInitScript((t) => localStorage.setItem("tailarr-theme", t), theme);
      await page.goto(path);
      await ready(page);
      const results = await new AxeBuilder({ page }).analyze();
      const serious = results.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => `${n.html.slice(0, 160)} → ${n.failureSummary ?? ""}`).join(" | ")})`);
      expect(serious, serious.join("\n")).toEqual([]);
    });
  }
}

test("the skip link jumps to the page", async ({ page }) => {
  await page.goto("/films");
  await expect(page.getByRole("heading", { level: 1, name: "Films" })).toBeVisible();
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to the page" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
});
