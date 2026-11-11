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

type FilmSummary = { id: number; title: string; media: { read: boolean } };

/** The film's page, once Tailarr has read every sample file's details. */
async function openFilm(page: Page, title: string) {
  let id = 0;
  await expect
    .poll(
      async () => {
        const body = await (await page.request.get("/api/films")).json();
        const films: FilmSummary[] = body.films;
        id = films.find((f) => f.title === title)?.id ?? 0;
        return films.every((f) => f.media.read);
      },
      { timeout: 60_000 },
    )
    .toBe(true);
  await page.goto(`/films/${id}`);
  await expect(page.getByRole("heading", { level: 1, name: new RegExp(title) })).toBeVisible();
  return id;
}

/** A track as shown: a table row on PCs, a card on phones. */
function trackRow(page: Page, id: number) {
  return page.getByTestId(isPhone(page) ? `track-card-${id}` : `track-${id}`);
}

const defaultSwitch = (page: Page, id: number) =>
  trackRow(page, id).getByRole("switch", { name: /^Default/ });
const forcedSwitch = (page: Page, id: number) =>
  trackRow(page, id).getByRole("switch", { name: /^Forced/ });

test("change track settings, confirm, and watch the job finish", async ({ page }) => {
  // Changes a real file: run it once (on the computer-sized screen), not in parallel twice.
  test.skip(isPhone(page), "the phone layout of this flow is checked without saving");
  await openFilm(page, "Bright Lights");
  await expect(defaultSwitch(page, 1)).toBeChecked();

  // French audio becomes the default: English is switched off automatically.
  await defaultSwitch(page, 2).click();
  await expect(defaultSwitch(page, 2)).toBeChecked();
  await expect(defaultSwitch(page, 1)).not.toBeChecked();
  await forcedSwitch(page, 3).click();
  await trackRow(page, 2)
    .getByRole("button", { name: /^Rename/ })
    .click();
  const name = page.getByRole("textbox", { name: /^Name of Audio 2/ });
  await name.fill("French 5.1");
  await name.press("Enter");
  await expect(page.getByTestId("save-bar")).toContainText("3 tracks changed, not saved yet");

  await page.getByRole("button", { name: "Save track changes" }).click();
  const dialog = page.getByRole("dialog", { name: "Change the original file?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId("summary-file")).toHaveText(
    "Bright Lights (2019) Bluray-2160p.mkv",
  );
  await expect(dialog).toContainText("Audio 1: English");
  await expect(dialog).toContainText("Stop it being the default");
  await expect(dialog).toContainText("Rename it from “Français 5.1” to “French 5.1”");
  await expect(dialog).toContainText("Mark it as forced");
  await dialog.getByRole("button", { name: "Change the original file" }).click();

  await expect(page.getByText("Track changes saved")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/3 tracks changed\./)).toBeVisible();
  await expect(page.getByTestId("save-bar")).toHaveCount(0);
  // The page now shows the file as it really is.
  await expect(defaultSwitch(page, 2)).toBeChecked();
  await expect(defaultSwitch(page, 1)).not.toBeChecked();
  await expect(forcedSwitch(page, 3)).toBeChecked();
  await expect(trackRow(page, 2)).toContainText("French 5.1");

  // The finished job is in the queue.
  await page.getByRole("link", { name: "Queue" }).first().click();
  const job = page.getByRole("listitem", { name: "Change track settings: Bright Lights (2019)" });
  await expect(job.first()).toContainText("Done");
  await expect(job.first()).toContainText("3 tracks changed.");
});

test("a hardlinked (seeding) file needs 'I understand'", async ({ page }) => {
  await openFilm(page, "Colour Test");
  await forcedSwitch(page, 3).click();
  await page.getByRole("button", { name: "Save track changes" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("This file is also in your downloads");
  const confirm = dialog.getByRole("button", { name: "Change the original file" });
  await expect(confirm).toBeDisabled();
  await dialog.getByRole("checkbox", { name: /I understand/ }).click();
  await expect(confirm).toBeEnabled();
  // Cancel: nothing is changed and the choice stays on the page.
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId("save-bar")).toBeVisible();
  await expect((await page.request.get("/api/jobs")).json()).resolves.toMatchObject({
    counts: { running: 0 },
  });
});

test("the summary is a sheet from the bottom on phones", async ({ page }) => {
  test.skip(!isPhone(page), "phones only");
  await openFilm(page, "Colour Test");
  await defaultSwitch(page, 2).click();
  await expect(page.getByTestId("save-bar")).toBeVisible();
  await expectNoSideways(page);
  await page.getByRole("button", { name: "Save track changes" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // Once it has slid in, it sits at the bottom, full width.
  const viewport = page.viewportSize()!;
  await expect
    .poll(async () => {
      const box = (await dialog.boundingBox())!;
      return [box.x, Math.round(box.y + box.height)];
    })
    .toEqual([0, viewport.height]);
  for (const button of await dialog.getByRole("button").all()) {
    const size = await button.boundingBox();
    expect(size!.height, "buttons are easy to tap").toBeGreaterThanOrEqual(44);
  }
  await expectNoSideways(page);
});

/** Starts a harmless real job (renames an audio track on a film no other test checks). */
async function finishedJob(page: Page, label: string) {
  const films: FilmSummary[] = (await (await page.request.get("/api/films")).json()).films;
  const film = films.find((f) => f.title === "Blu-ray Night")!;
  const detail = await (await page.request.get(`/api/films/${film.id}`)).json();
  const file = detail.main_file;
  const media = await (
    await page.request.get(`/api/films/${film.id}/media?file=${encodeURIComponent(file)}`)
  ).json();
  const audio = media.tracks.find((t: { type: string }) => t.type === "audio");
  const response = await page.request.post(`/api/films/${film.id}/track-settings`, {
    data: { file, confirmed: true, changes: [{ uid: audio.uid, name: `English (${label})` }] },
  });
  expect(response.status()).toBe(202);
  const job = await response.json();
  await expect
    .poll(async () => (await (await page.request.get(`/api/jobs/${job.id}`)).json()).status, {
      timeout: 30_000,
    })
    .toBe("done");
}

for (const theme of ["dark", "light"] as const) {
  test(`job screenshots in ${theme} theme`, async ({ page }, testInfo) => {
    await setTheme(page, theme);
    const name = `${testInfo.project.name}-${theme}`;

    await openFilm(page, "Colour Test");
    await defaultSwitch(page, 2).click();
    await forcedSwitch(page, 3).click();
    await expect(page.getByTestId("save-bar")).toBeVisible();
    await expectNoSideways(page);
    await page.screenshot({ path: `screenshots/${name}-track-settings.png`, fullPage: true });

    await page.getByRole("button", { name: "Save track changes" }).click();
    await expect(page.getByRole("dialog")).toContainText("This file is also in your downloads");
    await page.waitForTimeout(300); // let the sheet finish sliding in
    await page.screenshot({ path: `screenshots/${name}-confirm-summary.png` });
    await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();

    await finishedJob(page, name);
    await page.goto("/queue");
    await expect(page.getByRole("region", { name: /Finished/ })).toBeVisible();
    await expectNoSideways(page);
    await page.screenshot({ path: `screenshots/${name}-queue.png`, fullPage: true });
  });
}
