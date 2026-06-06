import { expect, test } from "@playwright/test";

/**
 * Live E2E for the Overview / Dashboard page.
 * Requires backend at http://localhost:8000 with the dataset ingested and
 * both ML models trained.
 */

test.describe("Overview / Dashboard page", () => {
  test("renders KPI row, needs-attention list, ML quick view, and quick actions", async ({
    page,
  }) => {
    await page.goto("/dashboard");

    // Page mounts
    await expect(page.getByTestId("overview-page")).toBeVisible({
      timeout: 20_000,
    });

    // Header copy
    await expect(
      page.getByRole("heading", { name: /today on bridge os/i }),
    ).toBeVisible();

    // KPI row: at least 6 stat tiles
    const tiles = page.getByTestId("stat-tile");
    await expect(tiles).toHaveCount(6, { timeout: 20_000 });

    // Needs-attention list renders at least one row when there are recommendations
    const attention = page.getByTestId("needs-attention-panel");
    await expect(attention).toBeVisible();

    // ML quick view + 4 quick-action cards
    await expect(page.getByTestId("ml-quick-view")).toBeVisible({
      timeout: 20_000,
    });
    const actions = page.getByTestId("quick-action");
    await expect(actions).toHaveCount(4);

    await page.screenshot({
      path: "playwright-report/dashboard.png",
      fullPage: true,
    });
  });

  test("sidebar Overview link no longer shows the 'soon' chip", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    const overviewLink = page
      .locator("nav[aria-label='Main'] a", { hasText: /^overview$/i })
      .first();
    await expect(overviewLink).toBeVisible({ timeout: 20_000 });
    // The 'soon' badge would be a descendant text — make sure it's gone.
    await expect(overviewLink.locator("text=soon")).toHaveCount(0);
  });
});
