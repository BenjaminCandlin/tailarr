/**
 * Flows that really change sample files (the "Bright Lights" film), one after the other.
 * They run in their own project, after every other browser test has finished, so they
 * never change a file another test is looking at.
 */
import { expect, test, type Page } from "@playwright/test";

const isPhone = (page: Page) => (page.viewportSize()?.width ?? 0) < 768;

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
  await expect(
    page.getByRole("heading", { level: 1, name: new RegExp(title) }),
  ).toBeVisible();
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

test.describe.configure({ mode: "serial" });

test("change track settings, confirm, and watch the job finish", async ({
  page,
}) => {
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
  await expect(page.getByTestId("save-bar")).toContainText(
    "3 tracks changed, not saved yet",
  );

  await page.getByRole("button", { name: "Save track changes" }).click();
  const dialog = page.getByRole("dialog", {
    name: "Change the original file?",
  });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId("summary-file")).toHaveText(
    "Bright Lights (2019) Bluray-2160p.mkv",
  );
  await expect(dialog).toContainText("Audio 1: English");
  await expect(dialog).toContainText("Stop it being the default");
  await expect(dialog).toContainText(
    "Rename it from “Français 5.1” to “French 5.1”",
  );
  await expect(dialog).toContainText("Mark it as forced");
  await dialog
    .getByRole("button", { name: "Change the original file" })
    .click();

  await expect(page.getByText("Track changes saved")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText(/3 tracks changed\./)).toBeVisible();
  await expect(page.getByTestId("save-bar")).toHaveCount(0);
  // The page now shows the file as it really is.
  await expect(defaultSwitch(page, 2)).toBeChecked();
  await expect(defaultSwitch(page, 1)).not.toBeChecked();
  await expect(forcedSwitch(page, 3)).toBeChecked();
  await expect(trackRow(page, 2)).toContainText("French 5.1");

  // The finished job is in the queue.
  await page.getByRole("link", { name: "Queue" }).first().click();
  const job = page.getByRole("listitem", {
    name: "Change track settings: Bright Lights (2019)",
  });
  await expect(job.first()).toContainText("Done");
  await expect(job.first()).toContainText("3 tracks changed.");
});

test("remove a track into a copy, then replace the original with it", async ({
  page,
}) => {
  await openFilm(page, "Bright Lights");
  // After the test above: English isn't the default any more, French is.
  await trackRow(page, 1).getByRole("checkbox", { name: /^Keep/ }).click();
  await expect(page.getByTestId("save-bar")).toContainText("1 track left out");
  await page
    .getByRole("button", { name: "Save a copy without the unticked tracks" })
    .click();

  const dialog = page.getByRole("dialog", {
    name: "Make a copy without these tracks?",
  });
  await expect(dialog.getByTestId("summary-new-file")).toHaveText(
    "Bright Lights (2019) Bluray-2160p - Tailarr.mkv",
  );
  await expect(
    dialog.getByRole("list", { name: "Left out of the copy" }),
  ).toContainText("Audio 1: English");
  await expect(dialog).not.toContainText("None of the audio tracks left");
  await dialog.getByRole("button", { name: "Make the copy" }).click();
  await expect(page.getByText("Copy saved", { exact: true })).toBeVisible({
    timeout: 30_000,
  });

  // The copy has one audio track; the original still has two.
  await page.getByRole("button", { name: "Show the copy" }).click();
  await expect(page).toHaveURL(/file=/);
  await expect(page.getByRole("region", { name: /^Audio/ })).toContainText(
    "Audio (1)",
  );
  await expect(trackRow(page, 1)).toContainText("French");

  await page
    .getByRole("button", { name: "Replace the original with this copy…" })
    .click();
  const replace = page.getByRole("dialog", {
    name: "Replace the original with this copy?",
  });
  await expect(replace.getByTestId("replace-original")).toHaveText(
    "Bright Lights (2019) Bluray-2160p.mkv",
  );
  await expect(replace).toContainText("deleted after 30 days");
  const confirm = replace.getByRole("button", { name: "Replace the original" });
  await expect(confirm).toBeDisabled();
  await replace.getByRole("checkbox", { name: /I understand/ }).click();
  await confirm.click();
  await expect(
    page.getByText("Original replaced", { exact: true }),
  ).toBeVisible({
    timeout: 30_000,
  });
  await page.getByText("Close", { exact: true }).click();

  // One file again, with the copy's tracks under the original's name.
  await expect(page.getByRole("combobox", { name: "File" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: /^Audio/ })).toContainText(
    "Audio (1)",
  );
  const recycle = await (
    await page.request.get("/api/settings/recycle")
  ).json();
  expect(recycle.file_count).toBe(1);
});

test("make a copy without Dolby Vision of a UHD Blu-ray style film", async ({
  page,
}) => {
  await openFilm(page, "Blu-ray Night");
  await expect(page.getByTestId("hdr-note")).toContainText(
    "Dolby Vision profile 7",
  );
  await page.getByRole("button", { name: "Make an HDR10 copy…" }).click();
  const dialog = page.getByRole("dialog", {
    name: "Make a copy without Dolby Vision?",
  });
  await expect(dialog).toContainText(
    "together with the extra Blu-ray picture layer",
  );
  await dialog.getByRole("button", { name: "Make the HDR10 copy" }).click();
  await expect(page.getByText("HDR10 copy saved", { exact: true })).toBeVisible(
    {
      timeout: 60_000,
    },
  );
  await page.screenshot({
    path: "screenshots/changes-hdr10-done.png",
    fullPage: true,
  });

  await page.getByRole("button", { name: "Show the copy" }).click();
  await expect(page).toHaveURL(/file=/);
  await expect(page.getByTestId("hdr-note")).toContainText("HDR10");
  await expect(page.getByTestId("hdr-note")).not.toContainText("Dolby Vision");
  await expect(page.getByTestId("dv-action")).toHaveCount(0);
  // The copy sits next to the original (a second version in Plex). Replacing the original
  // is possible, but only on request, with a plain warning that Dolby Vision would be gone.
  await expect(
    page.getByText("Made from Blu-ray Night (2018) Remux-2160p.mkv"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Replace the original with this copy…" })
    .click();
  const replace = page.getByRole("dialog", {
    name: "Replace the original with this copy?",
  });
  await expect(replace.getByTestId("loses-dolby-vision")).toContainText(
    "Dolby Vision will be gone from this film",
  );
  await page.waitForTimeout(300); // let the dialog finish appearing
  await page.screenshot({ path: "screenshots/changes-replace-with-hdr10.png" });
  await replace.getByRole("button", { name: "Cancel" }).click();
  await expect(replace).toHaveCount(0);
});

test("make HDR10 copies for a whole season, followed as a group in the queue", async ({
  page,
}) => {
  await page.goto("/tv");
  await page
    .getByRole("list", { name: "Shows" })
    .getByRole("link", { name: /Another Show/ })
    .click();
  await page.getByRole("button", { name: /Change this season/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("checkbox", { name: /Replace HDR10 copies/ }).click();
  await dialog.getByRole("button", { name: "Show what will happen" }).click();
  await expect(dialog.getByTestId("batch-counts")).toHaveText(
    "2 episodes will get a copy, 1 skipped.",
  );
  await dialog.getByRole("button", { name: "Make 2 copies" }).click();
  await expect(dialog.getByText("2 jobs added to the queue")).toBeVisible();
  await dialog.getByRole("link", { name: /Open the Queue/ }).click();
  const group = page.getByRole("listitem", {
    name: /Group: Make a copy without Dolby Vision/,
  });
  await expect(group.getByTestId("group-counts")).toHaveText("2 of 2 done", {
    timeout: 60_000,
  });
  await page.screenshot({
    path: "screenshots/changes-tv-batch-done.png",
    fullPage: true,
  });
  await group.getByText("Show the 2 jobs").click();
  await group.getByRole("link", { name: /S01E02/ }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Middle" }),
  ).toBeVisible();
  await expect(page.getByText("Copy made by Tailarr")).toBeVisible();
});

test("connect Radarr and Plex: titles and posters appear, webhooks are heard", async ({
  page,
}) => {
  await page.goto("/settings");
  const radarr = page.getByTestId("connection-radarr");
  await radarr.getByLabel("Address").fill("http://127.0.0.1:8496/radarr");
  await radarr.getByLabel("API key").fill("radarr-key");
  const plex = page.getByTestId("connection-plex");
  await plex.getByLabel("Address").fill("http://127.0.0.1:8496/plex");
  await plex.getByLabel("Plex token").fill("plex-token");
  await page.getByRole("button", { name: "Save connections" }).click();
  await expect(page.getByTestId("connection-radarr")).toContainText(
    "Connected",
  );
  await expect(page.getByTestId("sync-status")).toContainText("3 films", {
    timeout: 30_000,
  });

  // A Radarr test message, as Radarr sends when the webhook is saved.
  const path = (
    await (await page.request.get("/api/settings/connections")).json()
  ).webhook_paths.radarr;
  const reply = await page.request.post(path, { data: { eventType: "Test" } });
  expect((await reply.json()).message).toContain("The connection works");
  await page.reload();
  await expect(
    page.getByText("Radarr sent a test message. The connection works."),
  ).toBeVisible();
  await page.screenshot({
    path: "screenshots/changes-connections-saved.png",
    fullPage: true,
  });

  await page.goto("/films");
  const card = page.getByRole("list", { name: "Films" }).getByRole("link", {
    name: /Streaming Only: The Film/,
  });
  await expect(card).toBeVisible();
  await expect(card.locator("img")).toBeVisible();
  await page.screenshot({ path: "screenshots/changes-radarr-posters.png" });
});
