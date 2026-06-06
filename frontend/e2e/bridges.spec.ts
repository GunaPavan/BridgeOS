import { expect, test } from "@playwright/test";

/**
 * Live E2E for Phase 1 bridges flow.
 *
 * Requires the backend running on http://localhost:8000 with a seeded DB.
 * Run setup:
 *   cd backend && python -m scripts.seed
 *   uvicorn app.main:app --port 8000
 */

test.describe("Bridges browsing (Phase 1 live)", () => {
  test("lists bridges and shows Aarav's card", async ({ page }) => {
    await page.goto("/bridges");

    await expect(
      page.getByRole("heading", { name: /all blood bridges/i }),
    ).toBeVisible();

    // Aarav must be visible somewhere in the grid
    const aaravCard = page.getByRole("heading", { name: /aarav reddy/i });
    await expect(aaravCard).toBeVisible({ timeout: 15_000 });

    await page.screenshot({ path: "playwright-report/bridges-list.png", fullPage: true });
  });

  test("clicking Aarav opens detail with Priya in the cohort", async ({ page }) => {
    await page.goto("/bridges");

    await page.getByRole("heading", { name: /aarav reddy/i }).waitFor({ timeout: 15_000 });
    await page
      .getByRole("link")
      .filter({ has: page.getByRole("heading", { name: /aarav reddy/i }) })
      .first()
      .click();

    await expect(page).toHaveURL(/\/bridges\/[0-9a-f-]+/);

    // Patient header
    await expect(
      page.getByRole("heading", { name: /aarav reddy/i }),
    ).toBeVisible();
    await expect(page.getByText(/apollo hospitals/i).first()).toBeVisible();

    // Priya appears in the cohort
    await expect(page.getByText(/priya sharma/i).first()).toBeVisible();

    await page.screenshot({ path: "playwright-report/aarav-bridge-detail.png", fullPage: true });
  });

  test("backend 404 surfaces as a graceful error on detail page", async ({ page }) => {
    await page.goto("/bridges/00000000-0000-0000-0000-000000000000");

    await expect(page.getByText(/could not load this bridge/i)).toBeVisible({ timeout: 15_000 });
  });
});
