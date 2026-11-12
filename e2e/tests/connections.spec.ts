import { expect, test, type Page } from "@playwright/test";

const FAKE = "http://127.0.0.1:8496";

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

test("connection tests explain what's wrong, without saving anything", async ({
  page,
}) => {
  await page.goto("/settings");
  const radarr = page.getByTestId("connection-radarr");
  await expect(radarr).toContainText("Not connected (optional)");
  await radarr.getByLabel("Address").fill(`${FAKE}/radarr`);
  await radarr.getByLabel("API key").fill("wrong");
  await radarr.getByRole("button", { name: "Test Radarr" }).click();
  await expect(radarr.getByRole("alert")).toContainText(
    "Radarr refused the API key",
  );
  await radarr.getByLabel("API key").fill("radarr-key");
  await radarr.getByRole("button", { name: "Test Radarr" }).click();
  await expect(radarr.getByRole("status")).toHaveText(
    "Connected to Radarr 5.9.1. It has 3 films.",
  );
  await radarr.getByLabel("Address").fill("http://no-such-container:7878");
  await radarr.getByRole("button", { name: "Test Radarr" }).click();
  await expect(radarr.getByRole("alert")).toContainText(
    "same custom Docker network",
  );
  await expectNoSideways(page);
  // Nothing was saved.
  const saved = await (
    await page.request.get("/api/settings/connections")
  ).json();
  expect(saved.radarr.url).toBe("");
});

test("webhook addresses can be copied", async ({ page }) => {
  await page.goto("/settings");
  const field = page.getByLabel("Radarr webhook address", { exact: true });
  await expect(field).toHaveValue(
    /^http:\/\/tailarr:8484\/api\/webhooks\/radarr\?secret=.+/,
  );
  await expect(
    page.getByRole("button", { name: "Copy the Sonarr webhook address" }),
  ).toBeVisible();
});

for (const theme of ["dark", "light"] as const) {
  test(`connections screenshots in ${theme} theme`, async ({
    page,
  }, testInfo) => {
    await setTheme(page, theme);
    await page.goto("/settings");
    const card = page.getByTestId("connection-radarr");
    await card.getByLabel("Address").fill(`${FAKE}/radarr`);
    await card.getByLabel("API key").fill("radarr-key");
    await card.getByRole("button", { name: "Test Radarr" }).click();
    await expect(card.getByRole("status")).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    await expectNoSideways(page);
    const name = `${testInfo.project.name}-${theme}`;
    await page.screenshot({
      path: `screenshots/${name}-settings-connections.png`,
      fullPage: true,
    });
  });
}
