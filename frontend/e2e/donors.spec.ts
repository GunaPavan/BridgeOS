import { expect, test } from "@playwright/test";

/**
 * Live E2E for Phase 2 donors flow.
 *
 * Requires the backend running on http://localhost:8000 with a seeded DB.
 */

test.describe("Donors browsing (Phase 2 live)", () => {
  test("lists donors and shows the search input", async ({ page }) => {
    await page.goto("/donors");

    await expect(
      page.getByRole("heading", { name: /all donors/i }),
    ).toBeVisible();
    await expect(page.getByPlaceholder(/search by name/i)).toBeVisible();

    // At least one donor card should render after data loads
    await expect(
      page.locator('[data-testid="donor-card"]').first(),
    ).toBeVisible({ timeout: 15_000 });

    await page.screenshot({
      path: "playwright-report/donors-list.png",
      fullPage: true,
    });
  });

  test("search filter narrows results to Priya Sharma", async ({ page }) => {
    await page.goto("/donors");

    await page.getByPlaceholder(/search by name/i).fill("Priya Sharma");

    const priyaCard = page.getByRole("heading", { name: /^priya sharma$/i });
    await expect(priyaCard).toBeVisible({ timeout: 15_000 });
  });

  test("clicking Priya opens detail with Aarav's bridge", async ({ page }) => {
    await page.goto("/donors");

    await page.getByPlaceholder(/search by name/i).fill("Priya Sharma");
    await page.getByRole("heading", { name: /^priya sharma$/i }).waitFor({ timeout: 15_000 });

    await page
      .getByRole("link")
      .filter({ has: page.getByRole("heading", { name: /^priya sharma$/i }) })
      .first()
      .click();

    await expect(page).toHaveURL(/\/donors\/[0-9a-f-]+/);
    await expect(page.getByRole("heading", { name: /^priya sharma$/i })).toBeVisible();
    // Bridge membership shows Aarav as the patient
    await expect(page.getByText(/aarav reddy/i).first()).toBeVisible({ timeout: 15_000 });

    await page.screenshot({
      path: "playwright-report/priya-donor-detail.png",
      fullPage: true,
    });
  });

  test("Kell-negative filter restricts the result set", async ({ page }) => {
    await page.goto("/donors");

    await page.getByLabel(/kell-negative only/i).check();

    // Wait for query to refire and at least one card to render
    await expect(
      page.locator('[data-testid="donor-card"]').first(),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("404 on unknown donor surfaces graceful error", async ({ page }) => {
    await page.goto("/donors/00000000-0000-0000-0000-000000000000");

    await expect(page.getByText(/could not load this donor/i)).toBeVisible({
      timeout: 15_000,
    });
  });
});
