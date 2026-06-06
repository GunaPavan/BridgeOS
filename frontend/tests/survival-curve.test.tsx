import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SurvivalCurve } from "@/components/ui/survival-curve";
import type { SurvivalPrediction } from "@/lib/api";

function payload(overrides: Partial<SurvivalPrediction> = {}): SurvivalPrediction {
  return {
    donor_id: "d1",
    donor_name: "Donor 042",
    model_winner: "GradientBoostingSurvival",
    model_metrics: {
      c_index: 0.751,
      n_events: 682,
    },
    risk_score: 0.42,
    median_survival_days: 730,
    p_survive_90d: 0.95,
    p_survive_180d: 0.88,
    p_survive_365d: 0.74,
    top_factors: [
      { feature: "days_since_last_contact", global_importance: 0.37, value: 41 },
      { feature: "avg_cycle_days", global_importance: 0.15, value: 90 },
    ],
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactNode, p: SurvivalPrediction) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => p,
      text: async () => JSON.stringify(p),
    })),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

describe("SurvivalCurve", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders curve with 90/180/365 day probabilities", async () => {
    renderWithClient(<SurvivalCurve donorId="d1" />, payload());
    await waitFor(() => screen.getByTestId("survival-curve"));
    expect(screen.getByTestId("survival-90d")).toHaveTextContent("95%");
    expect(screen.getByTestId("survival-180d")).toHaveTextContent("88%");
    expect(screen.getByTestId("survival-365d")).toHaveTextContent("74%");
  });

  it("colors emerald when lowest probability is high (>=0.85)", async () => {
    renderWithClient(
      <SurvivalCurve donorId="d1" />,
      payload({
        p_survive_90d: 0.96,
        p_survive_180d: 0.92,
        p_survive_365d: 0.88,
      }),
    );
    await waitFor(() => screen.getByTestId("survival-curve"));
    expect(screen.getByTestId("survival-curve").dataset.tone).toBe("emerald");
  });

  it("colors red when lowest probability drops below 0.65", async () => {
    renderWithClient(
      <SurvivalCurve donorId="d2" />,
      payload({
        p_survive_90d: 0.7,
        p_survive_180d: 0.5,
        p_survive_365d: 0.3,
      }),
    );
    await waitFor(() => screen.getByTestId("survival-curve"));
    expect(screen.getByTestId("survival-curve").dataset.tone).toBe("red");
  });

  it("draws an SVG polyline with 4 datapoints (t=0,90,180,365)", async () => {
    renderWithClient(<SurvivalCurve donorId="d1" />, payload());
    await waitFor(() => screen.getByTestId("survival-curve-svg"));
    const svg = screen.getByTestId("survival-curve-svg");
    const circles = svg.querySelectorAll("circle");
    expect(circles.length).toBe(4);
  });

  it("shows median survival days when available", async () => {
    renderWithClient(<SurvivalCurve donorId="d1" />, payload({ median_survival_days: 542 }));
    await waitFor(() => screen.getByTestId("survival-curve"));
    expect(screen.getByText(/542 days/)).toBeInTheDocument();
  });
});
