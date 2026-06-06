import { expect, test } from "@playwright/test";

/**
 * Live E2E for Phase 10 WhatsApp page.
 * Requires backend at http://localhost:8000 with synthetic data seeded.
 *
 * Tests run serially because they mutate the shared backend conversation log.
 */

test.describe.configure({ mode: "serial" });

test.describe("WhatsApp page (Phase 10 live)", () => {
  test("page renders header, columns, and Twilio status", async ({ page }) => {
    await page.goto("/whatsapp");

    await expect(
      page.getByRole("heading", { name: /donor messaging/i }),
    ).toBeVisible();

    // 3-column shell
    await expect(page.getByTestId("conversation-list")).toBeVisible();
    await expect(page.getByTestId("thread-panel")).toBeVisible();
    await expect(page.getByTestId("compose-panel")).toBeVisible();

    // Twilio status pill defaults to mock mode unless env vars are set
    const pill = page.getByTestId("twilio-status-pill");
    await expect(pill).toBeVisible({ timeout: 20_000 });
    const pillText = (await pill.textContent()) ?? "";
    expect(/twilio live|mock mode/i.test(pillText)).toBe(true);

    await page.screenshot({
      path: "playwright-report/whatsapp-page.png",
      fullPage: true,
    });
  });

  test("opening 'New' reveals donor search; picking one focuses compose", async ({
    page,
  }) => {
    await page.goto("/whatsapp");

    await page.getByTestId("new-conversation-button").click();
    await expect(page.getByTestId("new-conversation-panel")).toBeVisible();

    const search = page.getByTestId("new-conversation-search");
    await search.fill("Priya Sharma");

    // Priya Sharma is the locked demo destabilizer in synthetic data
    const firstMatch = page.getByTestId("new-conversation-donor").first();
    await expect(firstMatch).toBeVisible({ timeout: 10_000 });
    await firstMatch.click();

    // Compose panel now shows the template selector + send button
    await expect(page.getByTestId("template-select")).toBeVisible();
    await expect(page.getByTestId("send-button")).toBeVisible();
  });

  test("sending a template message creates an outbound bubble and a conversation row", async ({
    page,
  }) => {
    await page.goto("/whatsapp");

    // Open Priya in compose
    await page.getByTestId("new-conversation-button").click();
    await page.getByTestId("new-conversation-search").fill("Priya Sharma");
    await page.getByTestId("new-conversation-donor").first().click();

    // Use template mode (default) — slot_reminder requires a bridge_id which
    // the page auto-fills from Priya's active bridge membership.
    await page.getByTestId("template-select").selectOption("slot_reminder");

    // Wait for the bridge select to render — it appears once the donor's
    // bridge memberships have loaded, signalling the auto-fill is ready.
    const bridgeSelect = page.getByTestId("bridge-select");
    await expect(bridgeSelect).toBeVisible({ timeout: 10_000 });

    // After G1 (recruit) Priya may end up on multiple bridges across E2E runs
    // (persistent DB). Find the option labelled with "Aarav" and pick it
    // explicitly so the template renders Aarav's name.
    const aaravOption = bridgeSelect.locator("option", { hasText: /aarav/i }).first();
    const aaravValue = await aaravOption.getAttribute("value");
    if (aaravValue) {
      await bridgeSelect.selectOption(aaravValue);
    }

    await page.getByTestId("send-button").click();

    // Outbound bubble appears in the thread. Messages are rendered oldest →
    // newest so the just-sent one is at the bottom: use .last().
    const bubbles = page.locator('[data-testid="message-bubble"]');
    await expect(bubbles.first()).toBeVisible({ timeout: 15_000 });
    const outbound = page.locator('[data-direction="outbound"]').last();
    await expect(outbound).toBeVisible();
    await expect(outbound).toContainText(/aarav/i); // template fills patient name

    // Conversation row appears in the left rail with Priya
    await expect(
      page.getByTestId("conversation-row").first(),
    ).toContainText(/priya/i, { timeout: 10_000 });
  });

  test("free-text mode sends a custom message", async ({ page }) => {
    await page.goto("/whatsapp");

    // Click into the existing Priya conversation if present, otherwise open new
    const existing = page.getByTestId("conversation-row").first();
    if (await existing.isVisible().catch(() => false)) {
      await existing.click();
    } else {
      await page.getByTestId("new-conversation-button").click();
      await page.getByTestId("new-conversation-search").fill("Priya Sharma");
      await page.getByTestId("new-conversation-donor").first().click();
    }

    await page.getByTestId("mode-free").click();
    const textarea = page.getByTestId("free-textarea");
    await expect(textarea).toBeVisible();
    const customBody = `Hi Priya, just checking in — Bridge OS E2E ${Date.now()}`;
    await textarea.fill(customBody);
    await page.getByTestId("send-button").click();

    // Bubble with our exact text shows up
    await expect(
      page.getByTestId("thread-messages").getByText(customBody, { exact: false }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("free-text send with empty body shows inline error and does not send", async ({
    page,
  }) => {
    await page.goto("/whatsapp");
    await page.getByTestId("new-conversation-button").click();
    await page.getByTestId("new-conversation-search").fill("Priya Sharma");
    await page.getByTestId("new-conversation-donor").first().click();

    await page.getByTestId("mode-free").click();
    await page.getByTestId("send-button").click();

    await expect(page.getByText(/message body is required/i)).toBeVisible();
  });

  test("WhatsApp link in sidebar no longer shows 'soon' tag", async ({ page }) => {
    await page.goto("/whatsapp");
    const sidebarLink = page.getByRole("link", { name: /^WhatsApp/i });
    await expect(sidebarLink).toBeVisible();
    await expect(sidebarLink).not.toContainText(/soon/i);
  });
});
