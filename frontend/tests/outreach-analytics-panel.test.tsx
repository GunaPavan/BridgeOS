import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";

import { OutreachAnalyticsPanel } from "@/components/ui/outreach-analytics-panel";

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const MOCK = {
  lookback_days: 30,
  waves: { total: 24, active: 4, accepted: 18, expired: 2, by_tier: { tier_1: 20, tier_2: 4 } },
  pings: {
    total: 56,
    accepted: 18,
    declined: 8,
    no_reply: 26,
    pending: 4,
    pings_per_acceptance: 3.11,
    avg_minutes_to_accept_by_urgency: { critical: 14.2, high: 122.0 },
  },
  donor_fatigue: { "0": 5800, "1": 600, "2": 200, "3-5": 80, "6+": 12 },
  emergency: {
    total: 2,
    active: 1,
    recent: [
      {
        id: "evt-1",
        patient_id: "p-1",
        triggered_at: "2026-06-05T18:00:00Z",
        triggered_by: "Aakash J",
        hospital_name: "Apollo",
        reach_window_min: 240,
        pool_size_at_trigger: 18,
        status: "active",
      },
    ],
  },
};

describe("OutreachAnalyticsPanel", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/outreach/analytics")) {
          return new Response(JSON.stringify(MOCK), {
            status: 200,
            headers: { "content-type": "application/json" },
          });
        }
        throw new Error(`Unmocked fetch: ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the 3 KPI tiles + wave-mix + fatigue + recent emergencies", async () => {
    renderWithClient(<OutreachAnalyticsPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("outreach-analytics-panel")).toBeInTheDocument();
    });

    const kpis = screen.getAllByTestId("outreach-kpi");
    // Acceptance rate, Pings/acceptance, Emergency events. Manual queue tile
    // was removed when the manual-call flow was deleted in favour of full
    // tier-escalation automation.
    expect(kpis).toHaveLength(3);

    expect(screen.getByTestId("wave-mix")).toBeInTheDocument();
    expect(screen.getByTestId("fatigue-distribution")).toBeInTheDocument();
    expect(screen.getByTestId("recent-emergencies")).toBeInTheDocument();
  });

  it("computes acceptance rate correctly from the totals", async () => {
    renderWithClient(<OutreachAnalyticsPanel />);
    await screen.findByTestId("outreach-analytics-panel");
    // 18 of 56 = 32%
    expect(screen.getByText("32%")).toBeInTheDocument();
  });

  it("populates each fatigue bucket", async () => {
    renderWithClient(<OutreachAnalyticsPanel />);
    await screen.findByTestId("outreach-analytics-panel");
    expect(screen.getByTestId("fatigue-bucket-0")).toHaveTextContent("5800");
    expect(screen.getByTestId("fatigue-bucket-1")).toHaveTextContent("600");
    expect(screen.getByTestId("fatigue-bucket-6+")).toHaveTextContent("12");
  });
});
