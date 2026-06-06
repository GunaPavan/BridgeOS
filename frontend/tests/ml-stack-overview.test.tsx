import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MLStackOverview } from "@/components/ui/ml-stack-overview";
import type { MlModelMetrics } from "@/lib/api";

function payload(overrides: Partial<MlModelMetrics> = {}): MlModelMetrics {
  return {
    churn: {
      loaded: true,
      winner: "XGBoost",
      metrics: {
        binary_auc: 0.979,
        macro_f1: 0.81,
        cv_macro_f1_mean: 0.804,
        cv_macro_f1_std: 0.022,
      },
      feature_names: [
        "donations_till_date",
        "avg_cycle_days",
        "days_since_last_contact",
      ],
    },
    survival: {
      loaded: true,
      winner: "GradientBoostingSurvival",
      metrics: {
        c_index: 0.751,
        n_events: 682,
        n_censored: 6267,
      },
      feature_names: ["donations_till_date", "avg_cycle_days"],
    },
    ...overrides,
  };
}

function renderWithClient(p: MlModelMetrics) {
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
    <QueryClientProvider client={client}>
      <MLStackOverview />
    </QueryClientProvider>,
  );
}

describe("MLStackOverview", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders both churn + survival cards", async () => {
    renderWithClient(payload());
    await waitFor(() =>
      expect(screen.getByTestId("ml-stack-overview")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("ml-card-churn")).toBeInTheDocument();
    expect(screen.getByTestId("ml-card-survival")).toBeInTheDocument();
  });

  it("shows the winner algorithm name for each model", async () => {
    renderWithClient(payload());
    await waitFor(() => screen.getByTestId("ml-card-churn"));
    expect(screen.getByTestId("ml-card-churn")).toHaveTextContent("XGBoost");
    expect(screen.getByTestId("ml-card-survival")).toHaveTextContent(
      "GradientBoostingSurvival",
    );
  });

  it("surfaces churn AUC + macro F1 metrics", async () => {
    renderWithClient(payload());
    await waitFor(() => screen.getByTestId("ml-card-churn"));
    const churn = screen.getByTestId("ml-card-churn");
    expect(churn).toHaveTextContent("0.979"); // AUC
    expect(churn).toHaveTextContent("0.810"); // Macro F1
  });

  it("surfaces survival C-index + event counts", async () => {
    renderWithClient(payload());
    await waitFor(() => screen.getByTestId("ml-card-survival"));
    const survival = screen.getByTestId("ml-card-survival");
    expect(survival).toHaveTextContent("0.751"); // C-index
    expect(survival).toHaveTextContent("682"); // events
    expect(survival).toHaveTextContent("6267"); // censored
  });

  it("flags an unloaded model in amber", async () => {
    renderWithClient(
      payload({
        survival: {
          loaded: false,
          winner: null,
          metrics: null,
          feature_names: null,
        },
      }),
    );
    await waitFor(() => screen.getByTestId("ml-card-survival"));
    const badge = screen.getByTestId("ml-card-survival-loaded-status");
    expect(badge).toHaveTextContent(/missing/i);
  });
});
