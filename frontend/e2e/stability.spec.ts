import { expect, test } from "@playwright/test";

/**
 * Live E2E for Phase 4 stability panel.
 * Requires backend at http://localhost:8000 with a trained stability model
 * and a seeded DB containing Aarav's bridge.
 */

test.describe("Cohort Stability (Phase 4 live)", () => {
  test("Aarav's bridge page shows the stability panel with Priya at top", async ({ page }) => {
    await page.goto("/bridges");

    await page.getByRole("heading", { name: /aarav reddy/i }).waitFor({ timeout: 15_000 });
    await page
      .getByRole("link")
      .filter({ has: page.getByRole("heading", { name: /aarav reddy/i }) })
      .first()
      .click();

    // Wait for the stability panel to load
    await expect(page.getByText(/cohort stability/i)).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByTestId("stability-panel"),
    ).toBeVisible({ timeout: 15_000 });

    // The first stability-donor card (highest churn) should be Priya
    const firstDonorCard = page.getByTestId("stability-donor").first();
    await expect(firstDonorCard).toContainText(/priya sharma/i);
    await expect(firstDonorCard).toContainText(/at risk/i);

    // Should expose the XGBoost provenance
    await expect(page.getByText(/predicted by xgboost/i)).toBeVisible();

    await page.screenshot({
      path: "playwright-report/aarav-stability.png",
      fullPage: true,
    });
  });

  test("each stability-donor card shows three churn horizons", async ({ page }) => {
    await page.goto("/bridges");
    await page.getByRole("heading", { name: /aarav reddy/i }).waitFor({ timeout: 15_000 });
    await page
      .getByRole("link")
      .filter({ has: page.getByRole("heading", { name: /aarav reddy/i }) })
      .first()
      .click();

    await page.getByTestId("stability-panel").waitFor({ timeout: 15_000 });

    const firstDonorCard = page.getByTestId("stability-donor").first();
    // 30d, 60d, 90d bars (testids on ChurnBar). Scope to the first donor card.
    const bars = firstDonorCard.locator('[data-testid="churn-bar"]');
    await expect(bars).toHaveCount(3);
  });

  test("at least one SHAP factor explanation is rendered", async ({ page }) => {
    await page.goto("/bridges");
    await page.getByRole("heading", { name: /aarav reddy/i }).waitFor({ timeout: 15_000 });
    await page
      .getByRole("link")
      .filter({ has: page.getByRole("heading", { name: /aarav reddy/i }) })
      .first()
      .click();

    await page.getByTestId("stability-panel").waitFor({ timeout: 15_000 });
    await expect(page.getByText(/why this score/i).first()).toBeVisible();
  });
});
