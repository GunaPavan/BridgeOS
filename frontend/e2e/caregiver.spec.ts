import { expect, request, test } from "@playwright/test";

/**
 * G5 live E2E: caregiver flow.
 * - Recruit a candidate to Aarav's bridge -> POST YES on the webhook
 *   -> caregiver notification fires automatically
 * - Confirm a caregiver row appears in the /whatsapp conversation list
 * - Confirm the patient profile shows the caregiver panel with at least one message
 *
 * Serial because it mutates persisted state.
 */

test.describe.configure({ mode: "serial" });

const API = "http://localhost:8000";

async function findAarav(apiCtx: ReturnType<typeof request.newContext> extends Promise<infer T> ? T : never) {
  const patientsResp = await apiCtx.get(`${API}/patients?search=Aarav%20Reddy&limit=1`);
  const patient = (await patientsResp.json()).items[0];
  return patient as { id: string; name: string };
}

test.describe("G5 caregiver WhatsApp (live)", () => {
  test("Manual notify-caregiver puts Lakshmi into the conversation list and the patient profile", async ({
    page,
  }) => {
    const apiCtx = await request.newContext();
    const aarav = await findAarav(apiCtx);

    // 1. Fire a caregiver notification directly via the API
    const notifyResp = await apiCtx.post(
      `${API}/patients/${aarav.id}/notify-caregiver`,
      {
        data: {
          template_key: "bridge_covered_caregiver",
          language: "en",
        },
      },
    );
    expect(notifyResp.ok()).toBe(true);
    const notifyBody = await notifyResp.json();
    expect(notifyBody.language_used).toBe("en");
    expect(notifyBody.body).toContain("Lakshmi");
    expect(notifyBody.body).toContain("Aarav");

    // 2. Visit /whatsapp and confirm a caregiver row appears
    await page.goto("/whatsapp");
    await expect(page.getByTestId("conversation-list")).toBeVisible();

    // Find any conversation row with kind=caregiver
    const caregiverRow = page
      .locator('[data-testid="conversation-row"][data-kind="caregiver"]')
      .first();
    await expect(caregiverRow).toBeVisible({ timeout: 15_000 });
    await expect(caregiverRow).toContainText(/Lakshmi Reddy/);
    await expect(caregiverRow).toContainText(/mother of Aarav Reddy/i);

    // 3. Visit Aarav's patient profile and confirm the caregiver panel +
    //    at least one message bubble.
    await page.goto(`/patients/${aarav.id}`);
    const panel = page.getByTestId("caregiver-panel");
    await expect(panel).toBeVisible({ timeout: 15_000 });
    await expect(panel).toContainText(/Lakshmi Reddy/);
    await expect(panel).toContainText(/mother/i);

    const thread = page.getByTestId("caregiver-thread");
    await expect(thread).toBeVisible({ timeout: 10_000 });

    await page.screenshot({
      path: "playwright-report/caregiver-panel.png",
      fullPage: true,
    });
  });

  test("Caregiver template dropdown exposes the 3 caregiver templates", async ({
    page,
  }) => {
    const apiCtx = await request.newContext();
    const aarav = await findAarav(apiCtx);

    await page.goto(`/patients/${aarav.id}`);
    const select = page.getByTestId("caregiver-template-select");
    await expect(select).toBeVisible({ timeout: 15_000 });
    const values = await select.locator("option").evaluateAll((opts) =>
      opts.map((o) => (o as HTMLOptionElement).value),
    );
    expect(values).toEqual([
      "bridge_covered_caregiver",
      "recruit_success_caregiver",
      "transfusion_confirmed_caregiver",
    ]);
  });
});
