import { expect, test } from "@playwright/test";

/**
 * Live E2E for the integrations page.
 * Requires backend at http://localhost:8000.
 */

test.describe("Integrations page", () => {
  test("page renders status cards for all four integrations", async ({ page }) => {
    await page.goto("/integrations");

    await expect(
      page.getByRole("heading", { name: /external systems/i }),
    ).toBeVisible();

    const cards = page.getByTestId("integration-card");
    await expect(cards).toHaveCount(4, { timeout: 20_000 });

    // Status pills cover all four
    const pills = page.getByTestId("status-pill");
    await expect(pills).toHaveCount(4);

    await page.screenshot({
      path: "playwright-report/integrations-page.png",
      fullPage: true,
    });
  });

  test("eRaktKosh + ICMR RDRI MOCKED; WhatsApp + AWS Bedrock status reflects env", async ({
    page,
    request,
  }) => {
    await page.goto("/integrations");
    await page.getByTestId("integration-card").first().waitFor({ timeout: 20_000 });

    // "eRaktKosh" and "ICMR" also appear in the sample-data section titles —
    // use .first() to match either occurrence.
    await expect(page.getByText(/eRaktKosh/i).first()).toBeVisible();
    await expect(page.getByText(/ICMR Rare Donor Registry/i).first()).toBeVisible();
    await expect(page.getByText(/WhatsApp Business API/i).first()).toBeVisible();
    await expect(page.getByText(/AWS Bedrock/i).first()).toBeVisible();

    // eRaktKosh + ICMR are always mocked.
    const mockedPills = page.getByText(/^MOCKED$/);
    await expect(mockedPills).toHaveCount(2);

    // Bedrock card flips to LIVE when BEDROCK_REGION is set on the backend.
    const intsBody = await request
      .get("http://localhost:8000/integrations")
      .then((r) => r.json());
    const bedrock = intsBody.items.find(
      (i: { key: string }) => i.key === "aws_bedrock",
    );
    const notConfigCount = bedrock?.status === "connected" ? 1 : 2;
    const notConfigPills = page.getByText(/^NOT CONFIGURED$/);
    await expect(notConfigPills).toHaveCount(notConfigCount);
  });

  test("eRaktKosh sample inventory table renders for Hyderabad", async ({ page }) => {
    await page.goto("/integrations");
    const table = page.getByTestId("inventory-table");
    await expect(table).toBeVisible({ timeout: 20_000 });

    // Hyderabad mock has Apollo + CARE + Yashoda
    await expect(table).toContainText(/Apollo Blood Bank/i);
    await expect(table).toContainText(/CARE Hospital Blood Centre/i);

    // Header row has all 8 ABO+Rh groups
    for (const bg of ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]) {
      await expect(table.getByText(bg, { exact: true }).first()).toBeVisible();
    }
  });

  test("ICMR RDRI returns at least one B+ Kell-negative donor", async ({ page }) => {
    await page.goto("/integrations");
    const list = page.getByTestId("icmr-donors-list");
    await expect(list).toBeVisible({ timeout: 20_000 });

    const items = list.locator("li");
    const count = await items.count();
    expect(count).toBeGreaterThanOrEqual(1);

    // Registry IDs follow the RDRI-YYYY-CITY-NNN pattern
    await expect(list).toContainText(/RDRI-\d{4}-[A-Z]{3}-\d{3}/);
  });
});
