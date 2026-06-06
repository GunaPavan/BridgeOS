import { expect, test } from "@playwright/test";

/**
 * Live E2E for Phase 9 cohort simulator.
 * Requires backend at http://localhost:8000 with stability model trained
 * and a seeded DB containing Aarav.
 */

test.describe("Cohort simulator (Phase 9 live)", () => {
  test("page loads, picks Aarav by default, and shows cohort tiles", async ({ page }) => {
    await page.goto("/simulator");

    await expect(
      page.getByRole("heading", { name: /live cohort simulator/i }),
    ).toBeVisible();

    await expect(page.getByTestId("simulator-body")).toBeVisible({ timeout: 25_000 });

    // Bridge picker should have selected Aarav's bridge
    const picker = page.getByTestId("bridge-picker");
    const selected = await picker.evaluate(
      (el: HTMLSelectElement) => el.options[el.selectedIndex]?.text ?? "",
    );
    expect(selected).toMatch(/aarav reddy/i);

    // 8 donor tiles for Aarav's cohort
    const tiles = page.getByTestId("donor-tile");
    const count = await tiles.count();
    expect(count).toBeGreaterThanOrEqual(6);

    await page.screenshot({
      path: "playwright-report/simulator-baseline.png",
      fullPage: true,
    });
  });

  test("ejecting Priya improves avg churn and surfaces replacement candidates", async ({
    page,
  }) => {
    await page.goto("/simulator");
    await page.getByTestId("simulator-body").waitFor({ timeout: 25_000 });

    // Find Priya's tile by name and click to eject
    const priyaTile = page
      .getByTestId("donor-tile")
      .filter({ hasText: /priya sharma/i })
      .first();
    await expect(priyaTile).toBeVisible();
    await priyaTile.click();

    // After the scenario runs, the direction pill should say "Health improved"
    await expect(page.getByTestId("churn-direction")).toContainText(
      /improved/i,
      { timeout: 15_000 },
    );

    // Priya's tile should now show "Restore" instead of "Eject"
    const ejectedPriya = page
      .getByTestId("donor-tile")
      .filter({ hasText: /priya sharma/i })
      .first();
    await expect(ejectedPriya).toHaveAttribute("data-ejected", "true");

    // At least one replacement candidate should appear
    const candidates = page.getByTestId("candidate-tile");
    const cCount = await candidates.count();
    expect(cCount).toBeGreaterThanOrEqual(1);

    await page.screenshot({
      path: "playwright-report/simulator-after-eject.png",
      fullPage: true,
    });
  });

  test("Reset button restores baseline and clears ejections", async ({ page }) => {
    await page.goto("/simulator");
    await page.getByTestId("simulator-body").waitFor({ timeout: 25_000 });

    const priyaTile = page
      .getByTestId("donor-tile")
      .filter({ hasText: /priya sharma/i })
      .first();
    await priyaTile.click();

    const reset = page.getByTestId("reset-button");
    await expect(reset).toBeVisible({ timeout: 10_000 });
    await reset.click();

    // No more ejected tiles
    const ejectedTiles = page.locator('[data-testid="donor-tile"][data-ejected="true"]');
    await expect(ejectedTiles).toHaveCount(0, { timeout: 10_000 });
  });
});
