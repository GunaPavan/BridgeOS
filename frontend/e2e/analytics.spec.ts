import { expect, test } from "@playwright/test";

/**
 * Live E2E for the analytics dashboard.
 * Requires backend at http://localhost:8000 with both ML models trained
 * (churn + survival) and a seeded DB.
 */

test.describe("Analytics dashboard", () => {
  test("page renders all top-level sections", async ({ page }) => {
    await page.goto("/analytics");

    await expect(
      page.getByRole("heading", { name: /network overview/i }),
    ).toBeVisible();
    await expect(page.getByTestId("analytics-content")).toBeVisible({
      timeout: 20_000,
    });

    // 4 top stat tiles (patients, donors, bridges, memberships)
    // + 4 model AUC + inference + 4 donor pool tiles
    const tiles = page.getByTestId("stat-tile");
    const count = await tiles.count();
    expect(count).toBeGreaterThanOrEqual(8);

    await page.screenshot({
      path: "playwright-report/analytics-dashboard.png",
      fullPage: true,
    });
  });

  test("shows a single ML-scored cohort-health distribution", async ({ page }) => {
    await page.goto("/analytics");
    await page.getByTestId("analytics-content").waitFor({ timeout: 20_000 });

    const dists = page.getByTestId("health-distribution");
    await expect(dists).toHaveCount(1);
    await expect(page.getByText(/^Cohort health$/i)).toBeVisible();
  });

  test("renders the ML-driven network insights panel", async ({ page }) => {
    await page.goto("/analytics");
    await page.getByTestId("analytics-content").waitFor({ timeout: 20_000 });

    const insights = page.getByTestId("ml-insights-panel");
    await expect(insights).toBeVisible({ timeout: 20_000 });
    // 4 intervention tiles + survival quartile block
    await expect(page.getByTestId("insight-needs-reminder")).toBeVisible();
    await expect(page.getByTestId("insight-stop-calling")).toBeVisible();
    await expect(page.getByTestId("insight-high-risk")).toBeVisible();
    await expect(page.getByTestId("insight-low-risk")).toBeVisible();
    await expect(page.getByTestId("survival-quartiles")).toBeVisible();
  });

  test("renders donor blood-group + city bar charts", async ({ page }) => {
    await page.goto("/analytics");
    await page.getByTestId("analytics-content").waitFor({ timeout: 20_000 });

    await expect(page.getByTestId("bg-chart")).toBeVisible();
    await expect(page.getByTestId("city-chart")).toBeVisible();
  });
});
