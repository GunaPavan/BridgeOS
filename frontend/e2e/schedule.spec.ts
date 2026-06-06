import { expect, test } from "@playwright/test";

/**
 * Live E2E for Phase 5 rotation scheduler.
 * Requires backend at http://localhost:8000 with a seeded DB containing Aarav.
 */

test.describe("Rotation Schedule (Phase 5 live)", () => {
  test("Aarav's bridge shows the rotation timeline with OR-Tools provenance", async ({ page }) => {
    await page.goto("/bridges");
    await page.getByRole("heading", { name: /aarav reddy/i }).waitFor({ timeout: 15_000 });
    await page
      .getByRole("link")
      .filter({ has: page.getByRole("heading", { name: /aarav reddy/i }) })
      .first()
      .click();

    await expect(page.getByTestId("schedule-timeline")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/rotation schedule/i)).toBeVisible();
    await expect(page.getByText(/or-tools cp-sat/i)).toBeVisible();

    // Solver should reach OPTIMAL or FEASIBLE
    await expect(
      page.getByText(/^(OPTIMAL|FEASIBLE)$/),
    ).toBeVisible();

    await page.screenshot({
      path: "playwright-report/aarav-schedule.png",
      fullPage: true,
    });
  });

  test("at least 15 transfusion slots appear in the 12-month horizon", async ({ page }) => {
    await page.goto("/bridges");
    await page.getByRole("heading", { name: /aarav reddy/i }).waitFor({ timeout: 15_000 });
    await page
      .getByRole("link")
      .filter({ has: page.getByRole("heading", { name: /aarav reddy/i }) })
      .first()
      .click();

    await page.getByTestId("schedule-timeline").waitFor({ timeout: 20_000 });
    const slots = page.getByTestId("schedule-slot");
    const count = await slots.count();
    expect(count).toBeGreaterThanOrEqual(15);
  });

  test("Re-solve button refetches the schedule", async ({ page }) => {
    await page.goto("/bridges");
    await page.getByRole("heading", { name: /aarav reddy/i }).waitFor({ timeout: 15_000 });
    await page
      .getByRole("link")
      .filter({ has: page.getByRole("heading", { name: /aarav reddy/i }) })
      .first()
      .click();

    await page.getByTestId("schedule-timeline").waitFor({ timeout: 20_000 });
    const button = page.getByRole("button", { name: /re-solve/i });
    await expect(button).toBeVisible();
    await button.click();
    // After re-solve, the timeline must still render an OPTIMAL/FEASIBLE status
    await expect(
      page.getByText(/^(OPTIMAL|FEASIBLE)$/),
    ).toBeVisible({ timeout: 15_000 });
  });
});
