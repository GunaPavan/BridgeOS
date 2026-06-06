import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ScheduleHistoryPanel } from "@/components/ui/schedule-history-panel";
import type { ScheduleHistory } from "@/lib/api";

function makeHistory(overrides: Partial<ScheduleHistory> = {}): ScheduleHistory {
  return {
    bridge_id: "b1",
    events: [
      {
        id: "e1",
        before_status: "INFEASIBLE",
        after_status: "OPTIMAL",
        before_objective: 0,
        after_objective: 12345,
        before_slot_count: 0,
        after_slot_count: 20,
        triggered_by: "webhook_yes",
        solve_time_ms: 45,
        notes: "Donor Aishwarya Murthy accepted invite",
        at: new Date().toISOString(),
      },
    ],
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactNode, payload: ScheduleHistory) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    })),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

describe("ScheduleHistoryPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the panel with one row for each event", async () => {
    renderWithClient(<ScheduleHistoryPanel bridgeId="b1" />, makeHistory());
    await waitFor(() =>
      expect(screen.getByTestId("schedule-history-panel")).toBeInTheDocument(),
    );
    const rows = screen.getAllByTestId("schedule-history-row");
    expect(rows).toHaveLength(1);
  });

  it("renders nothing when the events list is empty", async () => {
    renderWithClient(
      <ScheduleHistoryPanel bridgeId="b1" />,
      makeHistory({ events: [] }),
    );
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId("schedule-history-panel")).not.toBeInTheDocument();
  });

  it("shows a GOOD-tone row for INFEASIBLE → OPTIMAL", async () => {
    renderWithClient(<ScheduleHistoryPanel bridgeId="b1" />, makeHistory());
    await waitFor(() =>
      expect(screen.getByTestId("schedule-history-row")).toBeInTheDocument(),
    );
    const row = screen.getByTestId("schedule-history-row");
    expect(row.dataset.tone).toBe("good");
    expect(row).toHaveTextContent(/INFEASIBLE → OPTIMAL/);
    expect(row).toHaveTextContent(/webhook_yes/);
    expect(row).toHaveTextContent(/45ms/);
  });

  it("shows a BAD-tone row for OPTIMAL → INFEASIBLE", async () => {
    const payload = makeHistory({
      events: [
        {
          id: "e2",
          before_status: "OPTIMAL",
          after_status: "INFEASIBLE",
          before_objective: 12345,
          after_objective: 0,
          before_slot_count: 20,
          after_slot_count: 0,
          triggered_by: "webhook_yes",
          solve_time_ms: 50,
          notes: null,
          at: new Date().toISOString(),
        },
      ],
    });
    renderWithClient(<ScheduleHistoryPanel bridgeId="b1" />, payload);
    await waitFor(() =>
      expect(screen.getByTestId("schedule-history-row")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("schedule-history-row").dataset.tone).toBe("bad");
  });

  it("shows slot count delta when both sides are present", async () => {
    renderWithClient(<ScheduleHistoryPanel bridgeId="b1" />, makeHistory());
    await waitFor(() =>
      expect(screen.getByTestId("schedule-history-row")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Slots 0 → 20/i)).toBeInTheDocument();
  });
});
