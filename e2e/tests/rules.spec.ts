import { expect, test, type Page } from "@playwright/test";

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

/** Wait until Tailarr has read every sample file (previews only use what's been read). */
async function everythingRead(page: Page) {
  await expect
    .poll(
      async () => {
        const films = (await (await page.request.get("/api/films")).json())
          .films;
        return films.every((f: { media: { read: boolean } }) => f.media.read);
      },
      { timeout: 60_000 },
    )
    .toBe(true);
}

test("preview the Dolby Vision example rule without saving it", async ({
  page,
}) => {
  await everythingRead(page);
  await page.goto("/rules/new?example=0");
  await expect(page.getByLabel("Rule name")).toHaveValue(
    "HDR10 copies of Dolby Vision films",
  );
  await page.getByRole("button", { name: "Preview this rule" }).click();
  const counts = page.getByTestId("rule-preview-counts");
  await expect(counts).toContainText("would get a copy");
  await expect(
    page.getByRole("link", { name: "Blu-ray Night (2018)" }),
  ).toBeVisible();
  await page.getByText(/Matched but skipped/).click();
  await expect(page.getByRole("list", { name: "Skipped files" })).toContainText(
    "profile 5",
  );
  await expectNoSideways(page);
});

test("a rule that changes originals needs the switch", async ({ page }) => {
  await page.goto("/rules/new");
  await page.getByLabel("Rule name").fill("Default French audio");
  await page.getByRole("radio", { name: /Choose the default audio/ }).click();
  await page
    .getByLabel("Default audio", { exact: true })
    .selectOption({ label: "French" });
  await expect(
    page.getByRole("button", { name: "Save the rule" }),
  ).toBeDisabled();
  await page
    .getByRole("switch", { name: "Allowed to change original files" })
    .click();
  await expect(
    page.getByRole("button", { name: "Save the rule" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("switch", { name: /still seeding/ }),
  ).not.toBeChecked();
});

for (const theme of ["dark", "light"] as const) {
  test(`rules screenshots in ${theme} theme`, async ({ page }, testInfo) => {
    await setTheme(page, theme);
    await everythingRead(page);
    const name = `${testInfo.project.name}-${theme}`;
    await page.goto("/rules/new?example=1");
    await expect(page.getByLabel("Rule name")).toHaveValue(
      "Only English subtitles",
    );
    await expectNoSideways(page);
    await page.screenshot({
      path: `screenshots/${name}-rule-editor.png`,
      fullPage: true,
    });
    await page.getByRole("button", { name: "Preview this rule" }).click();
    await expect(page.getByTestId("rule-preview-counts")).toBeVisible();
    await page.getByTestId("rule-preview").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `screenshots/${name}-rule-preview.png` });
  });
}
