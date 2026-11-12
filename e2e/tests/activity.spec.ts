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

test("the activity log opens from the Rules page and filters", async ({
  page,
}) => {
  await page.goto("/rules");
  await page.getByRole("link", { name: "Activity log" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Activity log" }),
  ).toBeVisible();
  await page.getByLabel("Show").selectOption({ label: "Problems only" });
  await expect(page).toHaveURL(/show=problems/);
  await expectNoSideways(page);
});

test("automatic rules settings", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByLabel(/stopped changing for/)).toHaveValue("60");
  await expect(
    page.getByRole("switch", { name: /watch the Films and TV folders/ }),
  ).not.toBeChecked();
  await expectNoSideways(page);
});

for (const theme of ["dark", "light"] as const) {
  test(`activity screenshots in ${theme} theme`, async ({ page }, testInfo) => {
    await setTheme(page, theme);
    const name = `${testInfo.project.name}-${theme}`;
    await page.goto("/activity");
    await expect(
      page.getByRole("heading", { level: 1, name: "Activity log" }),
    ).toBeVisible();
    await expectNoSideways(page);
    await page.screenshot({
      path: `screenshots/${name}-activity.png`,
      fullPage: true,
    });
  });
}
