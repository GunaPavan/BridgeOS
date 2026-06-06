import { expect, request, test } from "@playwright/test";

/**
 * G1 live E2E: invite-with-consent loop.
 * Recruits a candidate -> sees PENDING -> POSTs YES via webhook -> sees ACTIVE.
 *
 * Tests run serially because they mutate persisted bridge membership state.
 */

test.describe.configure({ mode: "serial" });

const API = "http://localhost:8000";

test.describe("G1 recruit consent loop (live)", () => {
  test("Recruit modal -> Send invite -> Pending strip -> YES on webhook -> badge clears", async ({
    page,
  }) => {
    // 1. Find a non-Aarav recommendation card with a compatible candidate
    //    (we don't want to disrupt the Aarav demo narrative).
    await page.goto("/recommendations");
    await page.getByTestId("recommendation-card").first().waitFor({ timeout: 25_000 });

    const card = page
      .getByTestId("recommendation-card")
      .filter({ hasNotText: /aarav reddy/i })
      .first();
    await card.scrollIntoViewIfNeeded();

    // 2. Click Recruit on the top candidate -> modal opens
    const recruitBtn = card.getByTestId("recruit-button").first();
    await expect(recruitBtn).toBeVisible();
    await recruitBtn.click();

    await expect(page.getByTestId("recruit-confirm-modal")).toBeVisible({ timeout: 5_000 });

    // 3. Confirm with default language -> POST fires, modal closes, pending pill appears
    await page.getByTestId("recruit-modal-confirm").click();
    await expect(page.getByTestId("recruit-confirm-modal")).not.toBeVisible({
      timeout: 10_000,
    });

    // Toast renders
    await expect(page.getByTestId("toast").first()).toContainText(/invite sent/i, {
      timeout: 10_000,
    });

    // Button now says "Waiting on reply"
    const pendingBtn = card.getByTestId("recruit-button").first();
    await expect(pendingBtn).toContainText(/waiting on reply/i, { timeout: 10_000 });
    await expect(pendingBtn).toHaveAttribute("data-pending", "true");

    // 4. Read back what's pending so we can simulate the donor's YES via the
    //    webhook. We need the candidate's phone number — pull from the API.
    const bridgeId = await card.getAttribute("data-bridge-id");
    expect(bridgeId).toBeTruthy();

    const apiCtx = await request.newContext();
    const pendingResp = await apiCtx.get(
      `${API}/bridges/${bridgeId}/pending-recruits`,
    );
    expect(pendingResp.ok()).toBe(true);
    const pendings = await pendingResp.json();
    expect(pendings.length).toBeGreaterThan(0);
    const pending = pendings[0];

    // 5. POST a YES reply through the webhook
    const yes = await apiCtx.post(`${API}/whatsapp/webhook`, {
      form: {
        From: `whatsapp:${pending.candidate_donor_phone}`,
        To: "whatsapp:+14155238886",
        Body: "YES",
        MessageSid: `SM_e2e_yes_${Date.now()}`,
      },
    });
    expect(yes.ok()).toBe(true);

    // 6. Pending pill clears (the auto-refetch picks up the cleared state)
    await expect(pendingBtn).not.toContainText(/waiting on reply/i, { timeout: 15_000 });

    await page.screenshot({
      path: "playwright-report/recruit-consent-flow.png",
      fullPage: true,
    });
  });

  test("Pending recruits strip appears on bridge detail and clears on YES", async ({
    page,
  }) => {
    // We hit /bridges, pick the first non-Aarav bridge, recruit a compatible donor
    // through the API directly, then check that the strip surfaces on the detail page.
    const apiCtx = await request.newContext();
    const bridgesResp = await apiCtx.get(`${API}/bridges?limit=50`);
    const bridges = (await bridgesResp.json()).items as Array<{
      id: string;
      patient_name: string;
      blood_group: string;
    }>;
    const target = bridges.find((b) => !b.patient_name.includes("Aarav"));
    expect(target).toBeTruthy();
    if (!target) return;

    // Find a compatible donor not already on this bridge
    const donorsResp = await apiCtx.get(
      `${API}/donors?blood_group=${encodeURIComponent(target.blood_group)}&limit=200`,
    );
    const donors = (await donorsResp.json()).items as Array<{
      id: string;
      bridge_count: number;
      is_eligible_to_donate: boolean;
    }>;
    const candidate = donors.find((d) => d.bridge_count === 0);
    expect(candidate).toBeTruthy();
    if (!candidate) return;

    const recruitResp = await apiCtx.post(`${API}/bridges/${target.id}/recruit`, {
      data: { candidate_donor_id: candidate.id },
    });
    expect(recruitResp.ok()).toBe(true);

    // Visit the bridge detail page
    await page.goto(`/bridges/${target.id}`);
    const strip = page.getByTestId("pending-recruits-strip");
    await expect(strip).toBeVisible({ timeout: 15_000 });
    const rows = page.getByTestId("pending-recruit-row");
    await expect(rows.first()).toBeVisible();

    // Pull the candidate's phone (we already know the id but need the phone)
    const detailResp = await apiCtx.get(`${API}/donors/${candidate.id}`);
    const phone = (await detailResp.json()).phone as string;

    // YES via webhook -> strip clears
    await apiCtx.post(`${API}/whatsapp/webhook`, {
      form: {
        From: `whatsapp:${phone}`,
        To: "whatsapp:+14155238886",
        Body: "YES",
        MessageSid: `SM_e2e_strip_yes_${Date.now()}`,
      },
    });

    // Strip disappears (no PENDING rows left for this bridge)
    await expect(strip).not.toBeVisible({ timeout: 15_000 });
  });
});
