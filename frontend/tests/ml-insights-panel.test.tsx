import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";

import { MLInsightsPanel } from "@/components/ui/ml-insights-panel";

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
    },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const MOCK = {
  n_scored: 500,
  predicted_class_counts: {
    active: 306,
    inactive_not_donated_1y: 29,
    inactive_limited_despite_calls: 165,
  },
  p_active_mean: 0.6087,
  high_risk_count: 142,
  low_risk_count: 280,
  survival_365d_median: 0.74,
  survival_365d_p25: 0.41,
  survival_365d_p75: 0.99,
  needs_reminder_count: 29,
  stop_calling_count: 165,
  churn_winner: "xgboost_multiclass",
  survival_winner: "gradient_boosting_survival",
};

describe("MLInsightsPanel", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/ml/donor-pool-insights")) {
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

  it("renders both model winners + intervention counts after data loads", async () => {
    renderWithClient(<MLInsightsPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("ml-insights-panel")).toBeInTheDocument();
    });
    // Winners shown
    expect(screen.getByText(/xgboost_multiclass/i)).toBeInTheDocument();
    expect(screen.getByText(/gradient_boosting_survival/i)).toBeInTheDocument();
    // Intervention tiles populated
    expect(screen.getByTestId("insight-needs-reminder")).toHaveTextContent("29");
    expect(screen.getByTestId("insight-stop-calling")).toHaveTextContent("165");
    expect(screen.getByTestId("insight-high-risk")).toHaveTextContent("142");
    expect(screen.getByTestId("insight-low-risk")).toHaveTextContent("280");
    // Survival quartiles
    expect(screen.getByTestId("survival-quartiles")).toBeInTheDocument();
  });

  it("renders nothing when n_scored is 0 (cold ML stack)", async () => {
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        return new Response(
          JSON.stringify({ ...MOCK, n_scored: 0, predicted_class_counts: {} }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }),
    );

    const { container } = renderWithClient(<MLInsightsPanel />);
    await waitFor(() => {
      // After load + null return, the panel should not be in the document.
      expect(container.querySelector("[data-testid='ml-insights-panel']")).toBeNull();
    });
  });
});
