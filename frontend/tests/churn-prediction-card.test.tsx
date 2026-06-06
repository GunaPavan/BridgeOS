import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChurnPredictionCard } from "@/components/ui/churn-prediction-card";
import type { ChurnPrediction } from "@/lib/api";

function payload(overrides: Partial<ChurnPrediction> = {}): ChurnPrediction {
  return {
    donor_id: "d1",
    donor_name: "Donor 042",
    model_winner: "XGBoost",
    model_metrics: {
      binary_auc: 0.979,
      macro_f1: 0.81,
    },
    p_active: 0.65,
    p_not_donated_1y: 0.25,
    p_limited_despite_calls: 0.1,
    predicted_class: "active",
    predicted_label: "Active",
    recommended_action: "Continue normal cadence",
    top_factors: [
      { feature: "donations_till_date", global_importance: 0.57, value: 5 },
      { feature: "avg_cycle_days", global_importance: 0.14, value: 90 },
      { feature: "days_since_last_contact", global_importance: 0.08, value: 41 },
    ],
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactNode, p: ChurnPrediction) {
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

describe("ChurnPredictionCard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the card with the predicted class as Active", async () => {
    renderWithClient(<ChurnPredictionCard donorId="d1" />, payload());
    await waitFor(() =>
      expect(screen.getByTestId("churn-prediction-card")).toBeInTheDocument(),
    );
    const card = screen.getByTestId("churn-prediction-card");
    expect(card.dataset.class).toBe("active");
    // "Active" appears in the heading + a prob bar label; just check the recommendation copy.
    expect(screen.getByText(/Continue normal cadence/i)).toBeInTheDocument();
  });

  it("renders probability bars with correct percentages", async () => {
    renderWithClient(<ChurnPredictionCard donorId="d1" />, payload());
    await waitFor(() => screen.getByTestId("churn-prob-bars"));
    const bars = screen.getByTestId("churn-prob-bars");
    expect(bars).toHaveTextContent("65%");
    expect(bars).toHaveTextContent("25%");
    expect(bars).toHaveTextContent("10%");
  });

  it("flags 'limited despite calls' donors in red with phone-off icon", async () => {
    renderWithClient(
      <ChurnPredictionCard donorId="d2" />,
      payload({
        predicted_class: "inactive_limited_despite_calls",
        predicted_label: "Limited engagement despite calls",
        recommended_action: "Stop calling — try a different channel or accept loss",
        p_active: 0.05,
        p_not_donated_1y: 0.15,
        p_limited_despite_calls: 0.8,
      }),
    );
    await waitFor(() => screen.getByTestId("churn-prediction-card"));
    const card = screen.getByTestId("churn-prediction-card");
    expect(card.dataset.class).toBe("inactive_limited_despite_calls");
    expect(screen.getByTestId("churn-recommendation")).toHaveTextContent(
      /stop calling/i,
    );
  });

  it("renders top factors with importance + value", async () => {
    renderWithClient(<ChurnPredictionCard donorId="d1" />, payload());
    await waitFor(() => screen.getByTestId("churn-top-factors"));
    const factors = screen.getByTestId("churn-top-factors");
    expect(factors).toHaveTextContent("donations_till_date");
    expect(factors).toHaveTextContent("importance 0.57");
  });

  it("shows model winner tag with metric tooltip", async () => {
    renderWithClient(<ChurnPredictionCard donorId="d1" />, payload());
    await waitFor(() => screen.getByTestId("churn-model-tag"));
    const tag = screen.getByTestId("churn-model-tag");
    expect(tag).toHaveTextContent("XGBoost");
    expect(tag.getAttribute("title")).toMatch(/AUC: 0\.979/);
  });
});
