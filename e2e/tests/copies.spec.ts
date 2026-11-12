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

type FilmSummary = { id: number; title: string; media: { read: boolean } };

async function filmId(page: Page, title: string): Promise<number> {
  let id = 0;
  await expect
    .poll(
      async () => {
        const films: FilmSummary[] = (
          await (await page.request.get("/api/films")).json()
        ).films;
        id = films.find((f) => f.title === title)?.id ?? 0;
        return films.every((f) => f.media.read);
      },
      { timeout: 60_000 },
    )
    .toBe(true);
  return id;
}

function trackRow(page: Page, id: number) {
  return page.getByTestId(isPhone(page) ? `track-card-${id}` : `track-${id}`);
}

const MULTI = "Sample Multi-Language Film";
const MULTI_FILE = "Sample Multi-Language Film (2021).mkv";

/** A copy of the multi-language film without its Japanese audio (the original isn't changed). */
async function makeCopy(page: Page, id: number) {
  const media = await (
    await page.request.get(
      `/api/films/${id}/media?file=${encodeURIComponent(MULTI_FILE)}`,
    )
  ).json();
  const japanese = media.tracks.find(
    (t: { language: string }) => t.language === "jpn",
  );
  const response = await page.request.post(`/api/films/${id}/remove-tracks`, {
    headers: { "X-Requested-With": "tailarr" }, // as Tailarr's own page sends it
    data: {
      file: MULTI_FILE,
      remove: [japanese.uid],
      confirmed: true,
      overwrite: true,
    },
  });
  expect(response.status()).toBe(202);
  const job = await response.json();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/jobs/${job.id}`)).json()).status,
      {
        timeout: 30_000,
      },
    )
    .toBe("done");
}

test("unticked tracks are crossed out and the copy summary explains everything", async ({
  page,
}) => {
  const id = await filmId(page, "Colour Test");
  await page.goto(`/films/${id}`);
  await trackRow(page, 2).getByRole("checkbox", { name: /^Keep/ }).click();
  await expect(
    trackRow(page, 2).getByRole("checkbox", { name: /^Keep/ }),
  ).not.toBeChecked();
  await expect(page.getByTestId("save-bar")).toContainText("1 track left out");
  await expectNoSideways(page);
  await page
    .getByRole("button", { name: "Save a copy without the unticked tracks" })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Make a copy without these tracks?",
  });
  await expect(dialog).toContainText("Audio 2: French");
  await expect(dialog).toContainText("Your original isn't changed.");
  await expect(
    dialog.getByRole("button", { name: "Make the copy" }),
  ).toBeEnabled();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
});

test("Dolby Vision: an HDR10 copy is offered, and explained when it isn't possible", async ({
  page,
}) => {
  const colour = await filmId(page, "Colour Test");
  await page.goto(`/films/${colour}`);
  const action = page.getByTestId("dv-action");
  await expect(action).toContainText(
    "show Dolby Vision with the wrong colours",
  );
  await action.getByRole("button", { name: "Make an HDR10 copy…" }).click();
  const dialog = page.getByRole("dialog", {
    name: "Make a copy without Dolby Vision?",
  });
  await expect(dialog.getByTestId("hdr10-new-file")).toHaveText(
    "Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10.mkv",
  );
  // The sample library already has an HDR10 copy: replacing it must be ticked first.
  await expect(dialog).toContainText("An HDR10 copy is already there.");
  await expect(
    dialog.getByRole("button", { name: "Make the HDR10 copy" }),
  ).toBeDisabled();
  await expectNoSideways(page);
  await dialog.getByRole("button", { name: "Cancel" }).click();

  const streaming = await filmId(page, "Streaming Only");
  await page.goto(`/films/${streaming}`);
  await expect(page.getByTestId("dv-not-possible")).toContainText("profile 5");
  await expect(
    page.getByRole("button", { name: "Make an HDR10 copy…" }),
  ).toHaveCount(0);

  const weekend = await filmId(page, "The Long Weekend");
  await page.goto(`/films/${weekend}`);
  await expect(page.getByTestId("hdr-note")).toBeVisible();
  await expect(page.getByTestId("dv-action")).toHaveCount(0);
});

for (const theme of ["dark", "light"] as const) {
  test(`copy screenshots in ${theme} theme`, async ({ page }, testInfo) => {
    await setTheme(page, theme);
    const name = `${testInfo.project.name}-${theme}`;

    // Removing tracks: a summary, nothing changed.
    const colour = await filmId(page, "Colour Test");
    await page.goto(`/films/${colour}`);
    await trackRow(page, 2).getByRole("checkbox", { name: /^Keep/ }).click();
    await expect(page.getByTestId("save-bar")).toBeVisible();
    await page.screenshot({
      path: `screenshots/${name}-remove-tracks.png`,
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Save a copy without the unticked tracks" })
      .click();
    await expect(page.getByRole("dialog")).toContainText(
      "Left out of the copy",
    );
    await page.waitForTimeout(300); // let the sheet finish sliding in
    await expectNoSideways(page);
    await page.screenshot({ path: `screenshots/${name}-copy-summary.png` });
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Cancel" })
      .click();

    // Making a copy without Dolby Vision: the summary only.
    await page.goto(`/films/${colour}`);
    await page.getByRole("button", { name: "Make an HDR10 copy…" }).click();
    await expect(page.getByRole("dialog")).toContainText("What happens");
    await page.waitForTimeout(300);
    await expectNoSideways(page);
    await page.screenshot({ path: `screenshots/${name}-hdr10-summary.png` });
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Cancel" })
      .click();
    await page.screenshot({
      path: `screenshots/${name}-hdr10-action.png`,
      fullPage: true,
    });

    // Replacing the original: only the summary (cancelled), so the original stays.
    const multi = await filmId(page, MULTI);
    await makeCopy(page, multi);
    await page.goto(`/films/${multi}`);
    const replaceButton = page.getByRole("button", {
      name: "Replace the original with this copy…",
    });
    await expect(replaceButton).toBeVisible();
    await replaceButton.click();
    const dialog = page.getByRole("dialog", {
      name: "Replace the original with this copy?",
    });
    await expect(dialog.getByTestId("replace-original")).toHaveText(MULTI_FILE);
    await page.waitForTimeout(300);
    await expectNoSideways(page);
    await page.screenshot({ path: `screenshots/${name}-replace-original.png` });
    for (const button of await dialog.getByRole("button").all()) {
      if (isPhone(page))
        expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    await dialog.getByRole("button", { name: "Cancel" }).click();

    await page.goto("/settings");
    await expect(
      page.getByRole("spinbutton", { name: /Keep replaced originals/ }),
    ).toBeVisible();
    await expectNoSideways(page);
    await page.screenshot({
      path: `screenshots/${name}-settings-recycle.png`,
      fullPage: true,
    });
  });
}
