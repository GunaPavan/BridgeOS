import { expect, request, test } from "@playwright/test";

/**
 * G4 live E2E: send a slot_reminder in Hindi → bubble shows Devanagari +
 * language chip 'hi'. Composer language picker swaps the preview body.
 *
 * Serial because it writes to the persisted DB.
 */

test.describe.configure({ mode: "serial" });

const API = "http://localhost:8000";

test.describe("G4 multilingual templates (live)", () => {
  test("Slot reminder in Hindi shows Devanagari body + 'hi' chip on bubble", async ({
    page,
  }) => {
    const apiCtx = await request.newContext();

    const donorsResp = await apiCtx.get(`${API}/donors?search=Priya%20Sharma&limit=1`);
    const priya = (await donorsResp.json()).items[0];
    expect(priya).toBeTruthy();

    // Find a B+ bridge to use as patient context
    const bridgesResp = await apiCtx.get(`${API}/bridges?limit=200`);
    const bridges = (await bridgesResp.json()).items as Array<{
      id: string;
      blood_group: string;
      patient_name: string;
    }>;
    const bpBridge = bridges.find(
      (b) => b.blood_group === "B+" && b.patient_name !== "Aarav Reddy",
    );
    expect(bpBridge).toBeTruthy();
    if (!bpBridge) return;

    const sendResp = await apiCtx.post(`${API}/whatsapp/send`, {
      data: {
        donor_id: priya.id,
        template_key: "slot_reminder",
        bridge_id: bpBridge.id,
        language: "hi",
      },
    });
    expect(sendResp.ok()).toBe(true);
    const sendBody = await sendResp.json();
    expect(sendBody.language_used).toBe("hi");
    expect(sendBody.message.language).toBe("hi");
    expect(sendBody.message.body).toMatch(/[ऀ-ॿ]/);

    await page.goto("/whatsapp");
    await page.getByTestId("new-conversation-button").click();
    await page.getByTestId("new-conversation-search").fill("Priya Sharma");
    await page.getByTestId("new-conversation-donor").first().click();

    await expect(page.getByTestId("thread-messages")).toBeVisible({ timeout: 15_000 });
    const chips = page.getByTestId("message-language-chip");
    await expect(chips.first()).toBeVisible({ timeout: 10_000 });
    const texts = await chips.allTextContents();
    expect(texts.some((t) => /\bhi\b/.test(t))).toBe(true);

    await page.screenshot({
      path: "playwright-report/multilingual-templates.png",
      fullPage: true,
    });
  });

  test("Composer language picker switches the preview body", async ({ page }) => {
    await page.goto("/whatsapp");
    await page.getByTestId("new-conversation-button").click();
    await page.getByTestId("new-conversation-search").fill("Priya Sharma");
    await page.getByTestId("new-conversation-donor").first().click();

    const preview = page.getByTestId("template-preview");
    await expect(preview).toBeVisible({ timeout: 15_000 });
    const enBody =
      (await page.getByTestId("template-preview-body").textContent()) ?? "";

    await page.getByTestId("template-language-select").selectOption("te");
    await expect(preview).toHaveAttribute("data-language", "te", { timeout: 5000 });
    const teBody =
      (await page.getByTestId("template-preview-body").textContent()) ?? "";
    expect(teBody).not.toBe(enBody);
    expect(teBody).toMatch(/[ఀ-౿]/);
  });
});
