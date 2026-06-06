import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ScheduleTimeline } from "@/components/ui/schedule-timeline";
import type { BridgeSchedule } from "@/lib/api";

const sample: BridgeSchedule = {
  bridge_id: "bridge-aarav",
  bridge_name: "Bridge for Aarav",
  horizon_days: 365,
  transfusion_cadence_days: 18,
  solved_at: "2026-05-31T00:00:00Z",
  solve_time_ms: 42,
  solver_status: "OPTIMAL",
  objective_value: 12_345,
  message: "",
  slots: [
    { sequence: 1, transfusion_date: "2026-06-06", donor_id: "d1", donor_name: "Karan Trivedi", donor_blood_group: "O+" },
    { sequence: 2, transfusion_date: "2026-06-24", donor_id: "d2", donor_name: "Vikram Pandey", donor_blood_group: "B+" },
    { sequence: 3, transfusion_date: "2026-07-12", donor_id: "d3", donor_name: "Meera Desai", donor_blood_group: "B+" },
  ],
  donor_load: [
    { donor_id: "d1", donor_name: "Karan Trivedi", assignment_count: 1 },
    { donor_id: "d2", donor_name: "Vikram Pandey", assignment_count: 1 },
    { donor_id: "d3", donor_name: "Meera Desai", assignment_count: 1 },
  ],
};

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("ScheduleTimeline", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sample),
      text: () => Promise.resolve(""),
      statusText: "OK",
      status: 200,
    } as Response) as unknown as typeof fetch;
  });

  it("renders the section heading with provenance line", async () => {
    renderWithClient(<ScheduleTimeline bridgeId="bridge-aarav" />);
    // Wait for actual loaded content — heading is present in loading state too
    await waitFor(() =>
      expect(screen.getByText(/or-tools cp-sat/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/rotation schedule/i)).toBeInTheDocument();
  });

  it("shows solver status and solve time", async () => {
    renderWithClient(<ScheduleTimeline bridgeId="bridge-aarav" />);
    await waitFor(() => expect(screen.getByText("OPTIMAL")).toBeInTheDocument());
    expect(screen.getByText("42 ms")).toBeInTheDocument();
  });

  it("renders one card per slot with the assigned donor name", async () => {
    renderWithClient(<ScheduleTimeline bridgeId="bridge-aarav" />);
    await waitFor(() =>
      expect(screen.getAllByTestId("schedule-slot")).toHaveLength(3),
    );
    const slotsContainer = screen.getByTestId("schedule-slots");
    expect(within(slotsContainer).getByText("Karan Trivedi")).toBeInTheDocument();
    expect(within(slotsContainer).getByText("Vikram Pandey")).toBeInTheDocument();
    expect(within(slotsContainer).getByText("Meera Desai")).toBeInTheDocument();
  });

  it("renders the donor load chart with one row per donor", async () => {
    renderWithClient(<ScheduleTimeline bridgeId="bridge-aarav" />);
    await waitFor(() => screen.getByTestId("donor-load-chart"));
    const chart = screen.getByTestId("donor-load-chart");
    // 3 donors, 3 rows
    expect(chart.children.length).toBe(3);
  });

  it("shows a 'View recruitment recommendations' CTA when the schedule is infeasible", async () => {
    // 422 INFEASIBLE response — must surface an actionable CTA, not just an error
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      statusText: "Unprocessable Entity",
      json: () => Promise.resolve({ detail: "No feasible rotation found." }),
      text: () => Promise.resolve("422: No feasible rotation found."),
    } as Response) as unknown as typeof fetch;

    renderWithClient(<ScheduleTimeline bridgeId="bridge-aarav" />);
    await waitFor(() =>
      expect(screen.getByTestId("schedule-timeline-error")).toBeInTheDocument(),
    );
    expect(screen.getByText(/rotation is infeasible/i)).toBeInTheDocument();
    const cta = screen.getByTestId("schedule-infeasible-cta");
    expect(cta).toBeInTheDocument();
    expect(cta.getAttribute("href")).toBe("/recommendations");
  });
});
