import { expect, test } from "@playwright/test";

/**
 * Live E2E for the public marketing pages: /, /how-it-works, /about.
 * No backend required — these pages are entirely static / client-side links.
 */

test.describe("Marketing pages (Phase 12 live)", () => {
  test("landing page renders hero, differentiators, and CTAs", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(page.getByTestId("marketing-nav")).toBeVisible();
    await expect(page.getByTestId("marketing-footer")).toBeVisible();

    // Wordmark heading
    await expect(
      page.getByRole("heading", { name: /^bridge os$/i }).first(),
    ).toBeVisible();

    // 4 differentiator cards
    const cards = page.getByTestId("differentiator-card");
    await expect(cards).toHaveCount(4);

    // Both hero CTAs
    await expect(page.getByTestId("hero-cta-primary")).toBeVisible();
    await expect(page.getByTestId("hero-cta-secondary")).toBeVisible();

    await page.screenshot({
      path: "playwright-report/landing-page.png",
      fullPage: true,
    });
  });

  test("primary CTA navigates to /bridges", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("hero-cta-primary").click();
    await page.waitForURL("**/bridges", { timeout: 15_000 });
    expect(page.url()).toContain("/bridges");
  });

  test("nav links open /how-it-works and /about", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("link", { name: /how it works/i }).first().click();
    await page.waitForURL("**/how-it-works", { timeout: 10_000 });
    await expect(
      page.getByRole("heading", { name: /one product/i }),
    ).toBeVisible();

    await page.getByRole("link", { name: /^about$/i }).first().click();
    await page.waitForURL("**/about", { timeout: 10_000 });
    await expect(page.getByRole("heading", { name: /algowarriors/i })).toBeVisible();
  });

  test("how-it-works renders architecture diagram and four deep-dives", async ({
    page,
  }) => {
    await page.goto("/how-it-works");

    const diagram = page.getByTestId("architecture-diagram");
    await expect(diagram).toBeVisible();
    await expect(diagram).toContainText(/FRONTEND/);
    await expect(diagram).toContainText(/BACKEND/);
    await expect(diagram).toContainText(/DATA/);

    const deepdives = page.getByTestId("differentiator-deepdive");
    await expect(deepdives).toHaveCount(4);

    await page.screenshot({
      path: "playwright-report/how-it-works.png",
      fullPage: true,
    });
  });

  test("about page lists both team members and Blood Warriors link", async ({
    page,
  }) => {
    await page.goto("/about");

    const teamCards = page.getByTestId("team-card");
    await expect(teamCards).toHaveCount(2);

    await expect(
      page.getByText(/Gunaputra Nagendra Pavan Yedida/).first(),
    ).toBeVisible();
    await expect(page.getByText(/Aakash Jangeeti/).first()).toBeVisible();

    const bwLink = page.getByTestId("blood-warriors-link");
    await expect(bwLink).toBeVisible();
    await expect(bwLink).toHaveAttribute("href", "https://bloodwarriors.in");

    await page.screenshot({
      path: "playwright-report/about-page.png",
      fullPage: true,
    });
  });

  test("footer links navigate to dashboard sections", async ({ page }) => {
    await page.goto("/");

    // Footer "Simulator" link routes to /simulator
    const footer = page.getByTestId("marketing-footer");
    await footer.getByRole("link", { name: /^simulator$/i }).click();
    await page.waitForURL("**/simulator", { timeout: 10_000 });
    expect(page.url()).toContain("/simulator");
  });

  test("dashboard nav CTA routes to /bridges", async ({ page }) => {
    await page.goto("/about");
    await page.getByTestId("nav-dashboard-cta").click();
    await page.waitForURL("**/bridges", { timeout: 10_000 });
    expect(page.url()).toContain("/bridges");
  });
});
