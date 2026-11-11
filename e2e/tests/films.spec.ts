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

async function openFilms(page: Page, path = "/films") {
  await page.goto(path);
  await expect(films(page).getByRole("link").first()).toBeVisible();
}

test("the sample films are listed, with posters", async ({ page }) => {
  await openFilms(page);
  const cards = films(page).getByRole("link");
  await expect(cards).toHaveCount(9);
  await expect(page.getByText(/^9 films · /)).toBeVisible();
  // Empty folders, temporary files and the downloads folder never show up.
  await expect(page.getByText("Not Downloaded Yet")).toHaveCount(0);

  const colour = cards.filter({ hasText: "Colour Test" });
  const poster = colour.locator("img");
  await expect(poster).toBeVisible();
  // The small poster copy (480 pixels wide) is loaded, not the full-size picture.
  await expect.poll(() => poster.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(480);

  const noPoster = cards.filter({ hasText: "Streaming Only" });
  await expect(noPoster.getByTestId("poster-placeholder")).toBeVisible();
  await expect(cards.filter({ hasText: "Old Home Video" }).getByText("Not MKV")).toBeVisible();

  // Long names wrap inside their card instead of spilling out.
  for (const card of await cards.all()) {
    const spill = await card.evaluate((el) =>
      Array.from(el.querySelectorAll("p, span:not(.sr-only)")).some(
        (t) => t.scrollWidth > t.clientWidth + 1,
      ),
    );
    expect(spill, "card text should fit its card").toBe(false);
  }
  await expect(cards.filter({ hasText: "The Quiet Hours" })).toContainText("2017");

  // Two columns of posters on a phone, many more on a big screen.
  const boxes = await Promise.all([0, 1, 2].map((i) => cards.nth(i).boundingBox()));
  const firstRow = boxes.filter((b) => Math.abs(b!.y - boxes[0]!.y) < 2).length;
  expect(firstRow).toBe(isPhone(page) ? 2 : 3);
});

test("search finds a title, ignoring accents", async ({ page }) => {
  await openFilms(page);
  await page.getByRole("searchbox", { name: "Search films" }).fill("arger");
  await expect(films(page).getByRole("link")).toHaveCount(1);
  await expect(films(page).getByRole("link")).toContainText("Ärger im Paradies");
  await expect(page).toHaveURL(/q=arger/);

  await page.getByRole("searchbox", { name: "Search films" }).fill("nothing like this");
  await expect(page.getByText("No films match “nothing like this”")).toBeVisible();
  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(films(page).getByRole("link")).toHaveCount(9);
});

test("sorting and the list view", async ({ page }) => {
  await openFilms(page);
  await page.getByRole("combobox", { name: "Sort films" }).selectOption({ label: "Title (A–Z)" });
  await expect(films(page).getByRole("link").first()).toContainText("Ärger im Paradies");

  await page.getByRole("button", { name: "List" }).click();
  await expect(films(page)).toHaveClass(/divide-y/);
  await page.reload();
  await expect(page.getByRole("button", { name: "List" })).toHaveAttribute("aria-pressed", "true");
  await expectNoSideways(page);
});

test("check for new films", async ({ page }) => {
  await openFilms(page);
  await page.getByRole("button", { name: /Check for new films/ }).click();
  await expect(page.getByText(/Last checked/)).toBeVisible();
  await expect(films(page).getByRole("link")).toHaveCount(9);
});

test("opening a film shows its files", async ({ page }) => {
  await openFilms(page);
  await films(page)
    .getByRole("link", { name: /Colour Test/ })
    .click();
  await expect(page.getByRole("heading", { level: 1, name: /Colour Test/ })).toBeVisible();
  await expect(page.getByText("Main file", { exact: true })).toBeVisible();
  await expect(page.getByText("Copy made by Tailarr")).toBeVisible();
  // The sample film is hardlinked to a "seeding" copy in the downloads folder.
  await expect(page.getByText("Also in your downloads")).toBeVisible();
  await page.getByRole("link", { name: "Films" }).first().click();
  await expect(page).toHaveURL(/\/films$/);
});

for (const theme of ["dark", "light"] as const) {
  test(`films screenshots in ${theme} theme`, async ({ page }, testInfo) => {
    await setTheme(page, theme);
    await openFilms(page);
    for (const img of await films(page).locator("img").all()) {
      await expect.poll(() => img.evaluate((i: HTMLImageElement) => i.complete)).toBe(true);
    }
    await expectNoSideways(page);
    const name = `${testInfo.project.name}-${theme}`;
    await page.screenshot({ path: `screenshots/${name}-films-grid.png` });

    await page.getByRole("button", { name: "List" }).click();
    await expectNoSideways(page);
    await page.screenshot({ path: `screenshots/${name}-films-list.png` });

    await films(page)
      .getByRole("link", { name: /Colour Test/ })
      .click();
    await expect(page.getByText("Main file", { exact: true })).toBeVisible();
    await expectNoSideways(page);
    await page.screenshot({
      path: `screenshots/${name}-film-detail.png`,
      fullPage: true,
    });
  });
}
