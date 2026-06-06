import { expect, test } from "@playwright/test";

/**
 * Live E2E — Allocator cycle runs against the real backend.
 * Requires backend at http://localhost:8000 with both ML models loaded.
 */

test.describe("Allocator cycle endpoint", () => {
  test("dry-run returns a summary + allocations list", async ({ request }) => {
    const resp = await request.post(
      "http://localhost:8000/outreach/run-cycle?dry_run=true&horizon_days=14",
      { timeout: 60_000 },
    );
    expect(resp.status()).toBe(200);
    const body = await resp.json();

    // Schema sanity — every key we document must be present
    expect(body).toHaveProperty("summary");
    expect(body).toHaveProperty("allocations");
    expect(body.summary).toHaveProperty("open_slots");
    expect(body.summary).toHaveProperty("waves_created");
    expect(body.summary).toHaveProperty("pings_planned");
    expect(body.summary).toHaveProperty("critical_slots");

    // Allocations is an array sized to open_slots
    expect(Array.isArray(body.allocations)).toBe(true);
    expect(body.allocations.length).toBe(body.summary.open_slots);

    // dry_run = true → must NOT create live waves
    expect(body.summary.dry_run).toBe(true);
  });

  test("analytics endpoint returns the documented shape", async ({ request }) => {
    const resp = await request.get(
      "http://localhost:8000/outreach/analytics?lookback_days=30",
    );
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty("waves");
    expect(body).toHaveProperty("pings");
    expect(body).toHaveProperty("donor_fatigue");
    expect(body).toHaveProperty("emergency");
    // Donor fatigue has 5 buckets
    for (const bucket of ["0", "1", "2", "3-5", "6+"]) {
      expect(body.donor_fatigue).toHaveProperty(bucket);
    }
  });
});
