import { expect, test } from "@playwright/test";

/**
 * Live E2E for the new operator control surface:
 *   /outreach          — waves list with run-cycle + expire-sweep buttons
 *   /outreach/[id]     — wave detail with dispatch / promote / drop actions
 */

test.describe("Outreach operator surface", () => {
  test("waves page renders with Run-cycle + Expire buttons + status filter", async ({
    page,
  }) => {
    await page.goto("/outreach");
    await expect(page.getByTestId("outreach-page")).toBeVisible({ timeout: 20_000 });

    // Action buttons
    await expect(page.getByTestId("run-cycle-button")).toBeVisible();
    await expect(page.getByTestId("expire-sweep-button")).toBeVisible();

    // Status filter chips (all + 4 statuses)
    await expect(page.getByTestId("status-filter")).toBeVisible();
    await expect(page.getByTestId("status-chip-all")).toBeVisible();
    await expect(page.getByTestId("status-chip-active")).toBeVisible();
    await expect(page.getByTestId("status-chip-accepted")).toBeVisible();
    await expect(page.getByTestId("status-chip-expired")).toBeVisible();

    // Empty-state shown OR waves list (we don't care which, just that the page rendered cleanly)
    const empty = page.getByTestId("waves-empty");
    const list = page.getByTestId("waves-list");
    await expect(empty.or(list)).toBeVisible();
  });

  test("Run-cycle button opens the preview modal with horizon input", async ({
    page,
  }) => {
    await page.goto("/outreach");
    await page.getByTestId("outreach-page").waitFor({ timeout: 20_000 });

    await page.getByTestId("run-cycle-button").click();
    await expect(page.getByTestId("run-cycle-modal")).toBeVisible();
    await expect(page.getByTestId("horizon-input")).toBeVisible();
    await expect(page.getByTestId("dry-run-button")).toBeVisible();
  });

  test("Sidebar Outreach link is visible (no soon badge)", async ({ page }) => {
    await page.goto("/outreach");
    const link = page
      .locator("nav[aria-label='Main'] a", { hasText: /^outreach$/i })
      .first();
    await expect(link).toBeVisible({ timeout: 20_000 });
    await expect(link.locator("text=soon")).toHaveCount(0);
  });
});
