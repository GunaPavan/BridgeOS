import { expect, test } from "@playwright/test";

/**
 * Live E2E for the EMERGENCY OUTREACH button on the patient detail page.
 * Requires backend at http://localhost:8000.
 */

test.describe("EMERGENCY OUTREACH button", () => {
  test("button is visible on a patient page and opens the confirm dialog", async ({
    page,
    request,
  }) => {
    // Pick the first patient from the API so the test isn't tied to a specific UUID
    const listResp = await request.get("http://localhost:8000/patients?limit=1");
    expect(listResp.ok()).toBe(true);
    const list = await listResp.json();
    const patientId = list.items[0]?.id;
    expect(patientId).toBeTruthy();

    await page.goto(`/patients/${patientId}`);

    const button = page.getByTestId("emergency-button");
    await expect(button).toBeVisible({ timeout: 20_000 });
    await button.click();

    const dialog = page.getByTestId("emergency-dialog");
    await expect(dialog).toBeVisible();
    await expect(page.getByTestId("emergency-coordinator")).toBeVisible();
    await expect(page.getByTestId("emergency-justification")).toBeVisible();
    await expect(page.getByTestId("emergency-confirm")).toBeDisabled();
  });
});
