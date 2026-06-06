import { expect, test } from "@playwright/test";

/**
 * Live E2E — Alert Allocator analytics panel renders on /analytics.
 * Requires backend at http://localhost:8000.
 */

test.describe("Outreach analytics panel", () => {
  test("renders inside /analytics with 4 KPIs and fatigue distribution", async ({
    page,
  }) => {
    await page.goto("/analytics");

    const panel = page.getByTestId("outreach-analytics-panel");
    await expect(panel).toBeVisible({ timeout: 20_000 });

    // 4 KPI tiles (acceptance rate, pings/acceptance, manual queue, emergencies)
    const kpis = page.getByTestId("outreach-kpi");
    await expect(kpis).toHaveCount(4);

    // Fatigue distribution has 5 buckets (0, 1, 2, 3-5, 6+)
    await expect(page.getByTestId("fatigue-distribution")).toBeVisible();
    await expect(page.getByTestId("fatigue-bucket-0")).toBeVisible();
    await expect(page.getByTestId("fatigue-bucket-6+")).toBeVisible();
  });
});
