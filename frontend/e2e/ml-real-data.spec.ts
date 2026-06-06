import { expect, request, test } from "@playwright/test";

/**
 * Live E2E for the real-data ML surfaces (Module Integration).
 *
 * Verifies that:
 *   1. /donors/[id] shows ChurnPredictionCard + SurvivalCurve when the
 *      churn + survival model artifacts are present on the backend.
 *   2. /analytics shows the MLStackOverview + Bake-off tables for both
 *      churn and survival, with the winner row visible.
 *
 * Tests run serially. Each one short-circuits if the backend reports no
 * model artifact (returns 503), so they're safe to run before training.
 */

test.describe.configure({ mode: "serial" });

const API = "http://localhost:8000";

test.describe("Real-data ML surfaces (Module Integration live)", () => {
  test("Donor detail shows churn prediction card with class + recommendation", async ({
    page,
    request,
  }) => {
    const donors = await request
      .get(`${API}/donors?limit=10`)
      .then((r) => r.json());
    const donorId: string | undefined = donors?.items?.[0]?.id;
    test.skip(!donorId, "No donors seeded.");

    const churnResp = await request.get(`${API}/donors/${donorId}/churn-prediction`);
    test.skip(
      churnResp.status() === 503,
      "Churn model not loaded — run `python -m app.ml.churn.bakeoff`.",
    );

    await page.goto(`/donors/${donorId}`);
    const card = page.getByTestId("churn-prediction-card");
    await expect(card).toBeVisible({ timeout: 20_000 });
    // One of the three classes must be set on data-class
    const cls = await card.getAttribute("data-class");
    expect(
      ["active", "inactive_not_donated_1y", "inactive_limited_despite_calls"],
    ).toContain(cls);

    // Probability bars + recommendation copy + winner tag must all render
    await expect(page.getByTestId("churn-prob-bars")).toBeVisible();
    await expect(page.getByTestId("churn-recommendation")).toBeVisible();
    await expect(page.getByTestId("churn-model-tag")).toBeVisible();
  });

  test("Donor detail shows survival curve with 90/180/365 day points", async ({
    page,
    request,
  }) => {
    const donors = await request
      .get(`${API}/donors?limit=10`)
      .then((r) => r.json());
    const donorId: string | undefined = donors?.items?.[0]?.id;
    test.skip(!donorId, "No donors seeded.");

    const survResp = await request.get(`${API}/donors/${donorId}/survival`);
    test.skip(
      survResp.status() === 503,
      "Survival model not loaded — run `python -m app.ml.survival.bakeoff`.",
    );

    await page.goto(`/donors/${donorId}`);
    const curve = page.getByTestId("survival-curve");
    await expect(curve).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("survival-90d")).toBeVisible();
    await expect(page.getByTestId("survival-180d")).toBeVisible();
    await expect(page.getByTestId("survival-365d")).toBeVisible();
    await expect(page.getByTestId("survival-curve-svg")).toBeVisible();
  });

  test("Analytics page surfaces the production ML stack overview", async ({
    page,
  }) => {
    await page.goto("/analytics");
    const overview = page.getByTestId("ml-stack-overview");
    await expect(overview).toBeVisible({ timeout: 20_000 });
    // Both model cards must render with at least the title text
    await expect(page.getByTestId("ml-card-churn")).toBeVisible();
    await expect(page.getByTestId("ml-card-survival")).toBeVisible();
    await expect(overview).toContainText(/real blood warriors data/i);
  });

  test("Analytics page shows churn + survival bake-off tables with winner marked", async ({
    page,
    request,
  }) => {
    const churnResp = await request.get(`${API}/ml/bakeoff/churn`);
    test.skip(
      churnResp.status() !== 200,
      "Churn bake-off report not present — run bakeoff first.",
    );

    await page.goto("/analytics");
    const churnTable = page.getByTestId("bakeoff-table-churn");
    await expect(churnTable).toBeVisible({ timeout: 20_000 });
    // The winner row must carry data-winner="true"
    const winners = page.locator(
      "[data-testid^='bakeoff-row-'][data-winner='true']",
    );
    await expect(winners.first()).toBeVisible();

    // Survival table conditional on its report existing
    const survResp = await request.get(`${API}/ml/bakeoff/survival`);
    if (survResp.status() === 200) {
      await expect(page.getByTestId("bakeoff-table-survival")).toBeVisible();
    }
  });
});
