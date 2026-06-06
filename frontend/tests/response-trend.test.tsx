import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ResponseTrend } from "@/components/ui/response-trend";
import type { ResponseHistory } from "@/lib/api";

// Use REAL time (Date.now()) so TanStack Query + React effects schedule
// correctly. We just place events relative to `now()` instead of a fixed date.
function makeHistory(overrides: Partial<ResponseHistory> = {}): ResponseHistory {
  const now = Date.now();
  return {
    donor_id: "d1",
    donor_name: "Priya Sharma",
    current_response_rate: 0.45,
    current_avg_response_hours: 24,
    events: [
      {
        kind: "reply",
        prior_response_rate: 0.32,
        new_response_rate: 0.39,
        prior_avg_hours: 48,
        new_avg_hours: 36,
        hours_to_response: 6,
        at: new Date(now - 14 * 86400_000).toISOString(),
      },
      // older than the 7-day baseline cutoff
      {
        kind: "reply",
        prior_response_rate: 0.39,
        new_response_rate: 0.40,
        prior_avg_hours: 36,
        new_avg_hours: 30,
        hours_to_response: 8,
        at: new Date(now - 8 * 86400_000).toISOString(),
      },
      {
        kind: "no_reply",
        prior_response_rate: 0.40,
        new_response_rate: 0.36,
        prior_avg_hours: 30,
        new_avg_hours: 30,
        hours_to_response: null,
        at: new Date(now - 3 * 86400_000).toISOString(),
      },
    ],
    days: 30,
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactNode, history: ResponseHistory) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => history,
      text: async () => JSON.stringify(history),
    })),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

describe("ResponseTrend", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders current response rate from the history endpoint", async () => {
    renderWithClient(<ResponseTrend donorId="d1" />, makeHistory());
    await waitFor(() =>
      expect(screen.getByTestId("response-trend")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("response-trend-current")).toHaveTextContent(
      "45%",
    );
    expect(screen.getByTestId("response-trend-sparkline")).toBeInTheDocument();
  });

  it("shows an UP badge when current > baseline (7d) by more than 5%", async () => {
    renderWithClient(
      <ResponseTrend donorId="d1" />,
      // baseline (older than 7d) = 0.40; current = 0.50 -> +10%
      makeHistory({ current_response_rate: 0.5 }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("response-trend-badge")).toBeInTheDocument(),
    );
    const badge = screen.getByTestId("response-trend-badge");
    expect(badge.dataset.direction).toBe("up");
    expect(badge).toHaveTextContent(/\+10%/);
  });

  it("shows a DOWN badge when current dropped >5% vs 7d baseline", async () => {
    renderWithClient(
      <ResponseTrend donorId="d1" />,
      makeHistory({ current_response_rate: 0.3 }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("response-trend-badge")).toBeInTheDocument(),
    );
    const badge = screen.getByTestId("response-trend-badge");
    expect(badge.dataset.direction).toBe("down");
    expect(badge).toHaveTextContent(/-10%/);
  });

  it("shows a flat badge when the change is within the noise floor", async () => {
    renderWithClient(
      <ResponseTrend donorId="d1" />,
      makeHistory({ current_response_rate: 0.42 }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("response-trend-badge")).toBeInTheDocument(),
    );
    const badge = screen.getByTestId("response-trend-badge");
    expect(badge.dataset.direction).toBe("flat");
    expect(badge).toHaveTextContent(/stable/i);
  });
});
