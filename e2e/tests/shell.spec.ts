import { expect, test, type Page } from "@playwright/test";

const PAGES = [
  { path: "/films", heading: "Films" },
  { path: "/tv", heading: "TV" },
  { path: "/rules", heading: "Rules" },
  { path: "/queue", heading: "Queue" },
  { path: "/settings", heading: "Settings" },
];

const isPhone = (page: Page) => (page.viewportSize()?.width ?? 0) < 768;

async function setTheme(page: Page, theme: "dark" | "light") {
  await page.addInitScript(
    (t) => localStorage.setItem("tailarr-theme", t),
    theme,
  );
}

async function expectNoSideways(page: Page) {
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow, "page should not scroll sideways").toBeLessThanOrEqual(0);
}

for (const theme of ["dark", "light"] as const) {
  for (const { path, heading } of PAGES) {
    test(`${heading} page in ${theme} theme`, async ({ page }, testInfo) => {
      await setTheme(page, theme);
      await page.goto(path);
      await expect(
        page.getByRole("heading", { level: 1, name: heading }),
      ).toBeVisible();
      if (path === "/settings")
        await expect(page.getByText(/All good|Needs attention/)).toBeVisible();
      await expect(page.locator("html")).toHaveClass(
        theme === "dark" ? /dark/ : /^(?!.*dark)/,
      );
      await expectNoSideways(page);
      await page.screenshot({
        path: `screenshots/${testInfo.project.name}-${theme}-${heading.toLowerCase()}.png`,
        fullPage: false,
      });
    });
  }
}

test("the right navigation for the screen size", async ({ page }) => {
  await page.goto("/films");
  const sidebar = page.locator("aside nav");
  const tabBar = page.locator("nav").last();
  if (isPhone(page)) {
    await expect(sidebar).toBeHidden();
    await expect(tabBar).toBeVisible();
    // Big enough to tap comfortably.
    for (const link of await tabBar.getByRole("link").all()) {
      const box = await link.boundingBox();
      expect(box!.height).toBeGreaterThanOrEqual(44);
      expect(box!.width).toBeGreaterThanOrEqual(44);
    }
  } else {
    await expect(sidebar).toBeVisible();
    await expect(tabBar).toBeHidden();
  }
});

test("navigating between sections", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/films$/);
  const nav = page
    .getByRole("navigation", { name: "Main" })
    .locator("visible=true");
  for (const { heading } of PAGES) {
    await nav.getByRole("link", { name: heading }).click();
    await expect(
      page.getByRole("heading", { level: 1, name: heading }),
    ).toBeVisible();
  }
});

test("theme choice is remembered after reloading", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.getByRole("radio", { name: /light/i }).click();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await page.reload();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await expect(page.getByRole("radio", { name: /light/i })).toHaveAttribute(
    "aria-checked",
    "true",
  );
});

test("system check finds the sample library folders", async ({ page }) => {
  await page.goto("/settings");
  const folders = page.getByRole("region", { name: "Folders" });
  for (const name of ["Films folder", "TV folder", "Config folder"]) {
    const row = folders.getByRole("listitem").filter({ hasText: name });
    await expect(row.getByLabel("Working")).toBeVisible();
  }
  await expect(
    folders
      .getByRole("listitem")
      .filter({ hasText: "Work folder" })
      .getByLabel(/optional/),
  ).toBeVisible();
});
