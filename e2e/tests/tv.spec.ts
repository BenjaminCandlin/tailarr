import { expect, test, type Page } from "@playwright/test";

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

const shows = (page: Page) => page.getByRole("list", { name: "Shows" });

async function openShow(page: Page, title: string) {
  await page.goto("/tv");
  await shows(page)
    .getByRole("link", { name: new RegExp(title) })
    .click();
  await expect(
    page.getByRole("heading", { level: 1, name: new RegExp(title) }),
  ).toBeVisible();
}

test("the sample shows are listed", async ({ page }) => {
  await page.goto("/tv");
  await expect(shows(page).getByRole("link")).toHaveCount(2);
  await expect(page.getByText(/^2 shows · 8 episodes · /)).toBeVisible();
  const another = shows(page).getByRole("link", { name: /Another Show/ });
  await expect(another.locator("img")).toBeVisible();
  await expect(another).toContainText("1 season · 3 episodes");
  await page.getByRole("searchbox", { name: "Search shows" }).fill("test");
  await expect(shows(page).getByRole("link")).toHaveCount(1);
  await expectNoSideways(page);
});

test("a show lists its seasons and episodes", async ({ page }) => {
  await openShow(page, "Test Show");
  await expect(page.getByRole("heading", { name: "Specials" })).toBeVisible();
  const season1 = page.getByRole("list", { name: "Season 1 episodes" });
  await expect(season1.getByRole("link")).toHaveCount(3);
  await expect(season1.getByRole("link").nth(2)).toContainText("Many Voices");
  await expect(
    page.getByRole("button", { name: /Change this season/ }),
  ).toHaveCount(3);
  await expectNoSideways(page);
});

test("an episode shows its tracks, copies and the Dolby Vision action", async ({
  page,
}) => {
  await openShow(page, "Another Show");
  await page.getByRole("link", { name: /S01E01/ }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Start" }),
  ).toBeVisible();
  await expect(page.getByText("Copy made by Tailarr")).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Make an HDR10 copy/ }),
  ).toBeVisible();
  await page.getByRole("combobox", { name: "File" }).selectOption({ index: 1 });
  await expect(page).toHaveURL(/file=/);
  await page.getByRole("link", { name: "Another Show" }).first().click();
  await expect(page).toHaveURL(/\/tv\/shows\/\d+$/);
});

test("a seeding episode is marked", async ({ page }) => {
  await openShow(page, "Another Show");
  await page.getByRole("link", { name: /S01E02/ }).click();
  await expect(page.getByText("Also in your downloads")).toBeVisible();
});

test("the batch summary lists every episode before anything starts", async ({
  page,
}) => {
  await openShow(page, "Another Show");
  await page.getByRole("button", { name: /Change this season/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Show what will happen" }).click();
  await expect(dialog.getByTestId("batch-counts")).toHaveText(
    "1 episode will get a copy, 2 skipped.",
  );
  await dialog.getByText("Skipped (2)").click();
  await expect(dialog.getByText(/profile 5/)).toBeVisible();
  await expect(dialog.getByText(/already exists/)).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Make 1 copy" }),
  ).toBeEnabled();
  if (isPhone(page)) {
    // A sheet from the bottom on phones.
    const box = await dialog.boundingBox();
    expect(box!.y + box!.height).toBeGreaterThan(
      page.viewportSize()!.height - 2,
    );
  }
  await dialog.getByRole("button", { name: "Back" }).click();
  await dialog.getByRole("radio", { name: /Choose the default audio/ }).click();
  await dialog
    .getByLabel("Default audio", { exact: true })
    .selectOption({ label: "French" });
  await dialog.getByRole("button", { name: "Show what will happen" }).click();
  await expect(
    dialog.getByText(/This changes the original files/),
  ).toBeVisible();
  await expect(
    dialog.getByRole("checkbox", { name: /change seeding episodes/ }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

for (const theme of ["dark", "light"] as const) {
  test(`TV screenshots in ${theme} theme`, async ({ page }, testInfo) => {
    await setTheme(page, theme);
    const name = `${testInfo.project.name}-${theme}`;
    await page.goto("/tv");
    await expect(shows(page).getByRole("link")).toHaveCount(2);
    for (const img of await shows(page).locator("img").all()) {
      await expect
        .poll(() => img.evaluate((i: HTMLImageElement) => i.complete))
        .toBe(true);
    }
    await expectNoSideways(page);
    await page.screenshot({ path: `screenshots/${name}-tv-shows.png` });

    await shows(page)
      .getByRole("link", { name: /Another Show/ })
      .click();
    await expect(page.getByRole("heading", { name: "Season 1" })).toBeVisible();
    await expectNoSideways(page);
    await page.screenshot({
      path: `screenshots/${name}-tv-show.png`,
      fullPage: true,
    });

    await page.getByRole("button", { name: /Change this season/ }).click();
    const dialog = page.getByRole("dialog");
    await dialog
      .getByRole("radio", { name: /Save copies without some/ })
      .click();
    await page.screenshot({ path: `screenshots/${name}-tv-batch-choose.png` });
    await dialog
      .getByRole("radio", { name: /Make copies without Dolby/ })
      .click();
    await dialog.getByRole("button", { name: "Show what will happen" }).click();
    await expect(dialog.getByTestId("batch-counts")).toBeVisible();
    await page.screenshot({ path: `screenshots/${name}-tv-batch-summary.png` });
    await page.keyboard.press("Escape");

    await page.getByRole("link", { name: /S01E02/ }).click();
    await expect(page.getByText("What's inside")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Make an HDR10 copy/ }),
    ).toBeVisible();
    await expectNoSideways(page);
    await page.screenshot({
      path: `screenshots/${name}-tv-episode.png`,
      fullPage: true,
    });
  });
}
