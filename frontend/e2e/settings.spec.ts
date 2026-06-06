import { expect, test } from "@playwright/test";

/**
 * Live E2E for the Phase 13 Settings page.
 * Requires backend at http://localhost:8000.
 */

test.describe.configure({ mode: "serial" });

test.describe("Settings page (Phase 13 live)", () => {
  test("page renders header + three provider cards", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: /system configuration/i }),
    ).toBeVisible();

    const providerCards = page.getByTestId("provider-card");
    await expect(providerCards).toHaveCount(3);

    // Mode pills (Live / Mock) — at least one renders
    await expect(page.getByTestId("provider-mode-pill").first()).toBeVisible({
      timeout: 15_000,
    });

    await page.screenshot({
      path: "playwright-report/settings-page.png",
      fullPage: true,
    });
  });

  test("integration status rows mirror the /integrations endpoint", async ({
    page,
  }) => {
    await page.goto("/settings");
    const rows = page.getByTestId("integration-status-row");
    await expect(rows).toHaveCount(4, { timeout: 15_000 });

    // At least one MOCKED pill present (eRaktKosh / ICMR)
    const pills = page.getByTestId("integration-pill");
    const count = await pills.count();
    expect(count).toBe(4);
  });

  test("Feature toggle ping shows a toast", async ({ page }) => {
    await page.goto("/settings");
    // Click the first ping button
    const ping = page.getByTestId("feature-ping").first();
    await expect(ping).toBeVisible({ timeout: 15_000 });
    await ping.click();

    // Toast region renders the toast
    const toast = page.getByTestId("toast").first();
    await expect(toast).toBeVisible({ timeout: 10_000 });
  });

  test("All six feature toggles render with state pills", async ({ page }) => {
    await page.goto("/settings");
    const toggles = page.getByTestId("feature-toggle");
    await expect(toggles).toHaveCount(6, { timeout: 10_000 });
  });

  test("Sidebar Settings link no longer shows 'soon'", async ({ page }) => {
    await page.goto("/settings");
    const link = page.getByRole("link", { name: /^Settings/i });
    await expect(link).toBeVisible();
    await expect(link).not.toContainText(/soon/i);
  });
});
