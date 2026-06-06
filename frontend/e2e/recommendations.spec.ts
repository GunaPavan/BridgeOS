import { expect, test } from "@playwright/test";

/**
 * Live E2E for Phase 6 recruitment inbox.
 * Requires backend at http://localhost:8000 with the stability model trained
 * and a seeded DB containing Aarav + Priya.
 */

test.describe("Recommendations inbox (Phase 6 live)", () => {
  test("inbox shows Aarav's bridge with Priya flagged as weak", async ({ page }) => {
    await page.goto("/recommendations");

    await expect(
      page.getByRole("heading", { name: /recruitment inbox/i }),
    ).toBeVisible();

    // At least one card visible
    await expect(
      page.getByTestId("recommendation-card").first(),
    ).toBeVisible({ timeout: 20_000 });

    // Find Aarav's card anywhere in the inbox (Priya is 0.78, but other random
    // bridges with multiple high-churn donors will outrank him). The page can
    // render 40+ cards on first load, so wait for Aarav's specifically before
    // scrolling (scrollIntoViewIfNeeded on an empty locator hangs).
    const aaravCard = page
      .getByTestId("recommendation-card")
      .filter({ hasText: /aarav reddy/i })
      .first();
    await expect(aaravCard).toBeAttached({ timeout: 30_000 });
    await aaravCard.scrollIntoViewIfNeeded();
    await expect(aaravCard).toBeVisible();
    await expect(aaravCard).toContainText(/priya sharma/i);

    await page.screenshot({
      path: "playwright-report/recommendations-inbox.png",
      fullPage: true,
    });
  });

  test("each card surfaces an urgency pill", async ({ page }) => {
    await page.goto("/recommendations");
    await page.getByTestId("recommendation-card").first().waitFor({ timeout: 20_000 });

    const pills = page.getByTestId("urgency-pill");
    const count = await pills.count();
    expect(count).toBeGreaterThanOrEqual(1);
    const firstText = (await pills.first().textContent())?.toLowerCase() ?? "";
    expect(/critical|high|medium/.test(firstText)).toBe(true);
  });

  test("candidate cards have a Recruit button + rationale", async ({ page }) => {
    await page.goto("/recommendations");
    await page.getByTestId("recommendation-card").first().waitFor({ timeout: 20_000 });

    const candidate = page.getByTestId("candidate-row").first();
    await expect(candidate).toBeVisible();
    await expect(candidate.getByTestId("recruit-button")).toBeVisible();
    // Rationale lines start with "·"
    await expect(candidate).toContainText(/·/);
  });

  test("clicking Recruit opens the consent modal (G1)", async ({ page }) => {
    // Pick any non-Aarav card to avoid mutating state Phase 4/5 tests rely on.
    await page.goto("/recommendations");
    await page.getByTestId("recommendation-card").first().waitFor({ timeout: 20_000 });

    const nonAaravCard = page
      .getByTestId("recommendation-card")
      .filter({ hasNotText: /aarav reddy/i })
      .first();
    await nonAaravCard.scrollIntoViewIfNeeded();

    const recruitBtn = nonAaravCard.getByTestId("recruit-button").first();
    await expect(recruitBtn).toBeVisible();
    await recruitBtn.click();

    // The G1 confirmation modal appears with a language selector + Send button
    const modal = page.getByTestId("recruit-confirm-modal");
    await expect(modal).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId("recruit-modal-language")).toBeVisible();
    await expect(page.getByTestId("recruit-modal-confirm")).toBeVisible();

    // Cancel the modal so we don't actually fire a recruit (avoids polluting
    // the persistent DB across E2E runs).
    await page.getByTestId("recruit-modal-cancel").click();
    await expect(modal).not.toBeVisible();
  });
});
