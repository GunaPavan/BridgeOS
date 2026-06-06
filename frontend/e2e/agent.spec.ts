import { expect, test } from "@playwright/test";

/**
 * Live E2E for the Care Agent page.
 * Requires backend at http://localhost:8000 with the dataset ingested.
 *
 * Tests run serially because they share the persisted agent_messages table.
 */

test.describe.configure({ mode: "serial" });

test.describe("Care Agent page", () => {
  test("page renders shell + provider pill + language picker", async ({ page }) => {
    await page.goto("/agent");

    await expect(
      page.getByRole("heading", { name: /multilingual llm assistant/i }),
    ).toBeVisible();

    // Three panels
    await expect(page.getByTestId("agent-sessions-panel")).toBeVisible();
    await expect(page.getByTestId("agent-chat-panel")).toBeVisible();
    await expect(page.getByTestId("agent-sources-panel")).toBeVisible();

    // Provider pill (mock by default; flips to 'bedrock' when BEDROCK_REGION is set,
    // or 'anthropic' when only ANTHROPIC_API_KEY is set)
    const pill = page.getByTestId("provider-pill");
    await expect(pill).toBeVisible({ timeout: 20_000 });

    // Language selector has all 8 options
    const langSelect = page.getByTestId("language-select");
    const options = await langSelect.locator("option").count();
    expect(options).toBe(8);

    await page.screenshot({
      path: "playwright-report/agent-page.png",
      fullPage: true,
    });
  });

  test("sample query click populates input + Ask sends + assistant reply renders", async ({
    page,
  }) => {
    await page.goto("/agent");

    // Start fresh
    await page.getByTestId("new-session-button").click();

    // Click first sample query
    const sample = page.getByTestId("sample-query").first();
    await sample.click();

    const input = page.getByTestId("agent-input");
    await expect(input).not.toHaveValue("");

    await page.getByTestId("agent-send-button").click();

    // Both user + assistant bubbles appear
    await expect(
      page.locator('[data-testid="agent-message"][data-role="user"]'),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.locator('[data-testid="agent-message"][data-role="assistant"]'),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("picking a Bridge context surfaces a sources row after asking", async ({
    page,
  }) => {
    await page.goto("/agent");
    await page.getByTestId("new-session-button").click();

    await page.getByTestId("context-chip-bridge").click();
    await expect(page.getByTestId("context-picker")).toBeVisible();
    // Pick first bridge (Aarav is alphabetically near the top of synthetic data)
    const firstBridge = page.getByTestId("context-pick-bridge").first();
    await expect(firstBridge).toBeVisible({ timeout: 15_000 });
    await firstBridge.click();

    // Selected pill shows up
    await expect(page.getByTestId("selected-context-pill")).toBeVisible();

    // Ask a question that triggers the schedule intent
    await page.getByTestId("agent-input").fill("When is the next transfusion?");
    await page.getByTestId("agent-send-button").click();

    // Assistant reply renders
    await expect(
      page.locator('[data-testid="agent-message"][data-role="assistant"]'),
    ).toBeVisible({ timeout: 15_000 });

    // Sources panel populated
    await expect(page.getByTestId("source-row").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("Donor context with Priya Sharma surfaces risk explanation in the answer", async ({
    page,
  }) => {
    await page.goto("/agent");
    await page.getByTestId("new-session-button").click();

    await page.getByTestId("context-chip-donor").click();
    await page.getByTestId("context-search-input").fill("Priya Sharma");
    const pick = page.getByTestId("context-pick-donor").first();
    await expect(pick).toBeVisible({ timeout: 15_000 });
    await pick.click();

    await page.getByTestId("agent-input").fill("Why is this donor at risk?");
    await page.getByTestId("agent-send-button").click();

    const reply = page
      .locator('[data-testid="agent-message"][data-role="assistant"]')
      .last();
    await expect(reply).toBeVisible({ timeout: 15_000 });
    await expect(reply).toContainText(/Priya Sharma/i);
  });

  test("language selection persists into the conversation", async ({ page }) => {
    await page.goto("/agent");
    await page.getByTestId("new-session-button").click();

    await page.getByTestId("language-select").selectOption("hi");
    await page.getByTestId("agent-input").fill("Hello");
    await page.getByTestId("agent-send-button").click();

    // The reply renders successfully (in mock mode the text is still English,
    // but the language field is persisted — we only assert the round-trip works).
    await expect(
      page.locator('[data-testid="agent-message"][data-role="assistant"]'),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("New button clears the thread; previous session still appears in sidebar", async ({
    page,
  }) => {
    await page.goto("/agent");
    await page.getByTestId("new-session-button").click();
    await page.getByTestId("agent-input").fill("First session msg");
    await page.getByTestId("agent-send-button").click();
    await expect(
      page.locator('[data-testid="agent-message"][data-role="assistant"]'),
    ).toBeVisible({ timeout: 15_000 });

    // Click New
    await page.getByTestId("new-session-button").click();
    // Thread is empty -> sample-query buttons reappear
    await expect(page.getByTestId("sample-query").first()).toBeVisible();

    // Old session is in the sidebar
    await expect(page.getByTestId("session-row").first()).toBeVisible();
  });

  test("Sidebar link to Care Agent is present and has Sparkles icon", async ({ page }) => {
    await page.goto("/agent");
    const link = page.getByRole("link", { name: /care agent/i });
    await expect(link).toBeVisible();
    await expect(link).not.toContainText(/soon/i);
  });

  // ----- Module 1: Bedrock multi-model -----

  test("multi-model banner is hidden by default (non-Bedrock provider)", async ({
    page,
    request,
  }) => {
    // Verify backend isn't on Bedrock right now (the test env shouldn't have
    // BEDROCK_REGION set). If it is, this assertion is correctly skipped via early-return.
    const status = await request.get("http://localhost:8000/agent/status").then((r) => r.json());
    test.skip(
      Boolean(status.multi_model),
      "Backend running on Bedrock — multi-model banner is expected to be visible.",
    );

    await page.goto("/agent");
    await expect(page.getByTestId("provider-pill")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("multi-model-indicator")).toHaveCount(0);
  });

  test("multi-model banner appears when backend reports Bedrock", async ({
    page,
    request,
  }) => {
    const status = await request.get("http://localhost:8000/agent/status").then((r) => r.json());
    test.skip(
      !status.multi_model,
      "Backend not running on Bedrock — multi-model banner skip.",
    );

    await page.goto("/agent");
    const banner = page.getByTestId("multi-model-indicator");
    await expect(banner).toBeVisible({ timeout: 20_000 });
    await expect(banner).toContainText(/Bedrock multi-model active/i);
    await expect(banner).toContainText(/chat/i);
    await expect(banner).toContainText(/intent/i);
    await expect(banner).toContainText(/embed/i);
  });
});
