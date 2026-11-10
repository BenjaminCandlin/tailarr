import { expect, test, type Page } from "@playwright/test";

const isPhone = (page: Page) => (page.viewportSize()?.width ?? 0) < 768;

async function setTheme(page: Page, theme: "dark" | "light") {
  await page.addInitScript((t) => localStorage.setItem("tailarr-theme", t), theme);
}

async function expectNoSideways(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "page should not scroll sideways").toBeLessThanOrEqual(0);
}

const films = (page: Page) => page.getByRole("list", { name: "Films" });

/** Open the Films page once Tailarr has read every sample file's details. */
async function openFilmsWithDetails(page: Page, path = "/films") {
  await expect
    .poll(
      async () => {
        const body = await (await page.request.get("/api/films")).json();
        return body.films.every((f: { media: { read: boolean } }) => f.media.read);
      },
      { timeout: 60_000 },
    )
    .toBe(true);
  await page.goto(path);
  await expect(films(page).getByRole("link").first()).toBeVisible();
}

async function openFilm(page: Page, title: string) {
  await openFilmsWithDetails(page);
  await films(page)
    .getByRole("link", { name: new RegExp(title) })
    .click();
  await expect(page.getByRole("heading", { level: 1, name: new RegExp(title) })).toBeVisible();
}

/** A track as shown: a table row on PCs, a card on phones. */
function trackRow(page: Page, id: number) {
  return page.getByTestId(isPhone(page) ? `track-card-${id}` : `track-${id}`);
}

test("HDR badges on posters and the Dolby Vision filter", async ({ page }) => {
  await openFilmsWithDetails(page);
  const cards = films(page).getByRole("link");
  const colour = cards.filter({ hasText: "Colour Test" });
  await expect(colour.getByText("DV", { exact: true })).toBeVisible();
  await expect(colour.getByText("Dolby Vision profile 8.1")).toBeAttached();
  await expect(
    cards.filter({ hasText: "Ärger im Paradies" }).getByText("HDR10+", { exact: true }),
  ).toBeVisible();
  await expect(
    cards.filter({ hasText: "Bright Lights" }).getByText("HDR10", { exact: true }),
  ).toBeVisible();

  await page.getByRole("combobox", { name: "Show" }).selectOption({ label: "Has Dolby Vision" });
  await expect(page).toHaveURL(/show=dv/);
  await expect(cards).toHaveCount(3);
  for (const title of ["Blu-ray Night", "Colour Test", "Streaming Only"]) {
    await expect(cards.filter({ hasText: title })).toHaveCount(1);
  }
  await page.getByRole("combobox", { name: "Show" }).selectOption({ label: "No HDR" });
  await expect(cards.filter({ hasText: "The Long Weekend" })).toHaveCount(1);
  await expect(cards.filter({ hasText: "Colour Test" })).toHaveCount(0);
  await expectNoSideways(page);
});

test("a film's tracks, with friendly names", async ({ page }) => {
  await openFilm(page, "Sample Multi-Language Film");
  await expect(page.getByText("3 seconds")).toBeVisible();
  await expect(page.getByTestId("hdr-note")).toContainText("Normal picture (SDR)");

  await expect(trackRow(page, 0)).toContainText("H.264 (AVC)");
  await expect(trackRow(page, 0)).toContainText("320 × 180 · 23.976 fps");
  await expect(trackRow(page, 1)).toContainText("English");
  await expect(trackRow(page, 2)).toContainText("French");
  await expect(trackRow(page, 2)).toContainText("Dolby Digital · 5.1");
  await expect(trackRow(page, 2)).toContainText("Français 5.1");
  await expect(trackRow(page, 3)).toContainText("Japanese");
  await expect(trackRow(page, 5)).toContainText("English (Forced)");
  if (isPhone(page)) {
    await expect(trackRow(page, 5).getByText("Forced", { exact: true })).toBeVisible();
    await expect(trackRow(page, 4).getByText("Default", { exact: true })).toBeVisible();
  } else {
    await expect(trackRow(page, 5).getByText("Forced: yes")).toBeAttached();
    await expect(trackRow(page, 4).getByText("Default: yes")).toBeAttached();
  }
  await expect(trackRow(page, 7)).toContainText("Spanish");
  await expectNoSideways(page);
});

test("Dolby Vision profile 5 is explained", async ({ page }) => {
  await openFilm(page, "Streaming Only");
  const note = page.getByTestId("hdr-note");
  await expect(note).toContainText("Dolby Vision profile 5");
  await expect(note).toContainText("wrong colours");
});

test("switching to the copy made by Tailarr", async ({ page }) => {
  await openFilm(page, "Colour Test");
  await expect(page.getByTestId("hdr-note")).toContainText("Dolby Vision profile 8.1 with HDR10");
  await page
    .getByRole("combobox", { name: "File" })
    .selectOption({ label: "Copy: Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10.mkv" });
  await expect(page).toHaveURL(/file=/);
  await expect(page.getByTestId("hdr-note")).toContainText("HDR10");
  await expect(page.getByTestId("hdr-note")).not.toContainText("Dolby Vision");
  await expectNoSideways(page);
});

for (const theme of ["dark", "light"] as const) {
  test(`track screenshots in ${theme} theme`, async ({ page }, testInfo) => {
    await setTheme(page, theme);
    const name = `${testInfo.project.name}-${theme}`;
    await openFilmsWithDetails(page);
    for (const img of await films(page).locator("img").all()) {
      await expect.poll(() => img.evaluate((i: HTMLImageElement) => i.complete)).toBe(true);
    }
    await page.screenshot({ path: `screenshots/${name}-films-badges.png` });

    await films(page)
      .getByRole("link", { name: /Sample Multi-Language Film/ })
      .click();
    await expect(trackRow(page, 7)).toBeVisible();
    await expectNoSideways(page);
    await page.screenshot({ path: `screenshots/${name}-film-tracks.png`, fullPage: true });

    await page.goBack();
    await films(page)
      .getByRole("link", { name: /Streaming Only/ })
      .click();
    await expect(page.getByTestId("hdr-note")).toContainText("profile 5");
    await page.screenshot({ path: `screenshots/${name}-film-dv-profile-5.png`, fullPage: true });
  });
}
