import { expect, request, test } from "@playwright/test";

/**
 * G2 live E2E: donor reply on WhatsApp -> response_rate moves on /donors/[id].
 * Tests the closing of the "every response calibrates the next prediction" loop.
 *
 * Runs serially because it mutates persisted donor stats.
 */

test.describe.configure({ mode: "serial" });

const API = "http://localhost:8000";

test.describe("G2 response feedback loop (live)", () => {
  test("YES on webhook bumps Priya's response_rate, visible on donor page", async ({
    page,
  }) => {
    const apiCtx = await request.newContext();

    // 1. Find Priya Sharma directly via API
    const donorsResp = await apiCtx.get(
      `${API}/donors?search=Priya%20Sharma&limit=3`,
    );
    expect(donorsResp.ok()).toBe(true);
    const donors = (await donorsResp.json()).items as Array<{
      id: string;
      response_rate: number;
    }>;
    const priya = donors[0];
    expect(priya).toBeTruthy();

    // 2. Send an outbound slot_reminder so we have an outbound for the
    //    hours-to-response computation to anchor on. We pick the donor's
    //    bridge so the template can render with patient context.
    const pendingResp = await apiCtx.get(
      `${API}/donors/${priya.id}/pending-actions`,
    );
    // bridge_id can also be pulled via /donors/{id} detail
    const detailResp = await apiCtx.get(`${API}/donors/${priya.id}`);
    const memberships = (await detailResp.json()).memberships as Array<{
      bridge_id: string;
      status: string;
    }>;
    const bridgeId =
      memberships.find((m) => m.status === "active")?.bridge_id ??
      memberships[0]?.bridge_id;
    expect(bridgeId).toBeTruthy();

    await apiCtx.post(`${API}/whatsapp/send`, {
      data: {
        donor_id: priya.id,
        template_key: "slot_reminder",
        bridge_id: bridgeId,
      },
    });

    // 3. Phone for the webhook
    const phone = (await detailResp.json()).phone as string;

    const startRate = priya.response_rate;

    // 4. POST a YES on the webhook
    await apiCtx.post(`${API}/whatsapp/webhook`, {
      form: {
        From: `whatsapp:${phone}`,
        To: "whatsapp:+14155238886",
        Body: "YES",
        MessageSid: `SM_e2e_g2_yes_${Date.now()}`,
      },
    });

    // 5. Re-check via API
    const afterResp = await apiCtx.get(
      `${API}/donors/${priya.id}/response-history`,
    );
    const after = await afterResp.json();
    expect(after.current_response_rate).toBeGreaterThan(startRate);
    expect(after.events.length).toBeGreaterThanOrEqual(1);
    const lastEvent = after.events[after.events.length - 1];
    expect(lastEvent.kind).toBe("reply");
    expect(lastEvent.new_response_rate).toBeGreaterThan(
      lastEvent.prior_response_rate,
    );

    // 6. Visit the donor page and confirm the ResponseTrend widget renders
    //    with the new percentage.
    await page.goto(`/donors/${priya.id}`);
    const trend = page.getByTestId("response-trend");
    await expect(trend).toBeVisible({ timeout: 15_000 });
    const current = page.getByTestId("response-trend-current");
    await expect(current).toBeVisible();
    const currentText = (await current.textContent()) ?? "";
    expect(currentText).toMatch(/%/);

    await page.screenshot({
      path: "playwright-report/response-trend.png",
      fullPage: true,
    });
  });
});
