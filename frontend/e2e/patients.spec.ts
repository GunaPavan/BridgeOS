import { expect, test } from "@playwright/test";

/**
 * Live E2E for Phase 3 patients flow.
 * Requires backend at http://localhost:8000 with a seeded DB.
 */

test.describe("Patients browsing (Phase 3 live)", () => {
  test("lists patients and shows the filters bar", async ({ page }) => {
    await page.goto("/patients");

    await expect(
      page.getByRole("heading", { name: /all patients/i }),
    ).toBeVisible();
    await expect(page.getByPlaceholder(/search by name/i)).toBeVisible();

    await expect(
      page.locator('[data-testid="patient-card"]').first(),
    ).toBeVisible({ timeout: 15_000 });

    await page.screenshot({
      path: "playwright-report/patients-list.png",
      fullPage: true,
    });
  });

  test("search narrows results to Aarav Reddy", async ({ page }) => {
    await page.goto("/patients");

    await page.getByPlaceholder(/search by name/i).fill("Aarav");
    await expect(
      page.getByRole("heading", { name: /^aarav reddy$/i }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("clicking Aarav opens profile with bridge link and projections", async ({ page }) => {
    await page.goto("/patients");

    await page.getByPlaceholder(/search by name/i).fill("Aarav");
    await page.getByRole("heading", { name: /^aarav reddy$/i }).waitFor({ timeout: 15_000 });

    await page
      .getByRole("link")
      .filter({ has: page.getByRole("heading", { name: /^aarav reddy$/i }) })
      .first()
      .click();

    await expect(page).toHaveURL(/\/patients\/[0-9a-f-]+/);
    await expect(page.getByRole("heading", { name: /^aarav reddy$/i })).toBeVisible();
    await expect(page.getByText(/apollo hospitals/i).first()).toBeVisible();
    await expect(page.getByText(/projected next 6 transfusions/i)).toBeVisible();

    const bridgeLink = page.getByTestId("patient-bridge-link");
    await expect(bridgeLink).toBeVisible();

    await page.screenshot({
      path: "playwright-report/aarav-patient-profile.png",
      fullPage: true,
    });
  });

  test("bridge link from patient profile leads back to bridge detail", async ({ page }) => {
    await page.goto("/patients");
    await page.getByPlaceholder(/search by name/i).fill("Aarav");
    await page.getByRole("heading", { name: /^aarav reddy$/i }).waitFor({ timeout: 15_000 });
    await page
      .getByRole("link")
      .filter({ has: page.getByRole("heading", { name: /^aarav reddy$/i }) })
      .first()
      .click();

    await page.getByTestId("patient-bridge-link").click();

    await expect(page).toHaveURL(/\/bridges\/[0-9a-f-]+/);
    await expect(page.getByText(/bridge for aarav/i)).toBeVisible();
  });

  test("404 on unknown patient surfaces graceful error", async ({ page }) => {
    await page.goto("/patients/00000000-0000-0000-0000-000000000000");
    await expect(page.getByText(/could not load this patient/i)).toBeVisible({
      timeout: 15_000,
    });
  });
});
