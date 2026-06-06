import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";

import OverviewPage from "@/app/(app)/dashboard/page";

// next/link renders a plain <a> in jsdom; nothing to mock.

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const ANALYTICS = {
  generated_at: "2026-06-06T12:00:00Z",
  total_patients: 84,
  total_donors: 6949,
  donor_pool: {
    total: 6949,
    active: 4220,
    eligible_now: 2100,
    kell_negative: 312,
    by_blood_group: [],
  },
  cohort_stats: {
    total_bridges: 79,
    avg_active_donors: 7.4,
    avg_cohort_size: 9.1,
    total_active_memberships: 587,
    stub_health: { stable: 16, at_risk: 41, critical: 22 },
    ml_health: { stable: 15, at_risk: 35, critical: 29 },
  },
  patients_by_city: [],
  stability_model: null,
  stability_compute_time_ms: 132,
};

const RECS = {
  total: 3,
  items: [
    {
      bridge_id: "b1",
      bridge_name: "Bridge for Patient 9872DA",
      patient_id: "p1",
      patient_name: "Patient 9872DA",
      patient_age: 9,
      patient_blood_group: "B+",
      patient_hospital: null,
      patient_city: "Hyderabad",
      bridge_health_stub: "critical",
      active_donor_count: 5,
      urgency: "critical",
      weak_donors: [
        {
          membership_id: "m1",
          donor_id: "d1",
          donor_name: "Donor 87E350",
          role: "primary",
          churn_90d: 0.98,
          top_factors: [],
        },
      ],
      candidates: [],
    },
    {
      bridge_id: "b2",
      bridge_name: "Bridge for Patient 01655E",
      patient_id: "p2",
      patient_name: "Patient 01655E",
      patient_age: 11,
      patient_blood_group: "O+",
      patient_hospital: null,
      patient_city: "Chennai",
      bridge_health_stub: "critical",
      active_donor_count: 4,
      urgency: "critical",
      weak_donors: [],
      candidates: [],
    },
    {
      bridge_id: "b3",
      bridge_name: "Bridge for Patient 837FC9",
      patient_id: "p3",
      patient_name: "Patient 837FC9",
      patient_age: 14,
      patient_blood_group: "A+",
      patient_hospital: null,
      patient_city: "Bengaluru",
      bridge_health_stub: "at_risk",
      active_donor_count: 6,
      urgency: "high",
      weak_donors: [],
      candidates: [],
    },
  ],
};

const INSIGHTS = {
  n_scored: 500,
  predicted_class_counts: {
    active: 306,
    inactive_not_donated_1y: 29,
    inactive_limited_despite_calls: 165,
  },
  p_active_mean: 0.6087,
  high_risk_count: 159,
  low_risk_count: 267,
  survival_365d_median: 0.989,
  survival_365d_p25: 0.984,
  survival_365d_p75: 0.992,
  needs_reminder_count: 29,
  stop_calling_count: 165,
  churn_winner: "XGBoost",
  survival_winner: "GradientBoostingSurvival",
};

const CLOCK = {
  today: "2026-02-27",
  wall_clock: "2026-06-06",
  is_anchored: true,
  days_anchored_back: 99,
  label: "Snapshot · 99d behind real time",
};

describe("OverviewPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.toString();
        const route = (path: string, body: unknown) =>
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { "content-type": "application/json" },
          });
        if (url.endsWith("/analytics")) return route("analytics", ANALYTICS);
        if (url.includes("/recommendations"))
          return route("recommendations", RECS);
        if (url.includes("/ml/donor-pool-insights"))
          return route("insights", INSIGHTS);
        if (url.includes("/system/clock")) return route("clock", CLOCK);
        throw new Error(`Unmocked fetch: ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the KPI row + needs-attention rows + ML quick view + quick actions", async () => {
    renderWithClient(<OverviewPage />);

    // Page mounts
    await waitFor(() => {
      expect(screen.getByTestId("overview-page")).toBeInTheDocument();
    });

    // KPI row mounts with 6 stat tiles
    await waitFor(() => {
      const tiles = screen.getAllByTestId("stat-tile");
      expect(tiles.length).toBeGreaterThanOrEqual(6);
    });

    // Needs-attention list renders one row per recommendation
    const rows = await screen.findAllByTestId("attention-row");
    expect(rows.length).toBe(3);

    // First (most-critical) row should carry data-urgency="critical"
    expect(rows[0]).toHaveAttribute("data-urgency", "critical");

    // ML quick view + survival mini render
    expect(screen.getByTestId("ml-quick-view")).toBeInTheDocument();
    expect(screen.getByTestId("survival-mini")).toBeInTheDocument();
    expect(screen.getByTestId("engagement-mix")).toBeInTheDocument();

    // Quick actions: 4 cards
    const actions = screen.getAllByTestId("quick-action");
    expect(actions.length).toBe(4);
  });

  it("shows the dataset anchor label when system clock is anchored", async () => {
    renderWithClient(<OverviewPage />);
    await waitFor(() => {
      expect(screen.getByText(/dataset snapshot/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/99d behind real time/i)).toBeInTheDocument();
  });
});
