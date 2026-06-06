import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import SchedulerPage from "@/app/(app)/system/scheduler/page";

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const MOCK_STATUS = {
  running: true,
  demo_mode: false,
  job_count: 5,
  enabled_count: 5,
  last_tick_at: "2026-06-07T10:00:00Z",
  failures_24h: 0,
  jobs: [
    {
      name: "auto_run_cycle",
      description: "Allocator cycle.",
      enabled: true,
      cron_default: "*/5 * * * *",
      cron_demo: "*/30 * * * * *",
      cron_override: null,
      effective_cron: "*/5 * * * *",
      last_run_at: "2026-06-07T10:00:00Z",
      next_run_at: "2026-06-07T10:05:00Z",
    },
    {
      name: "auto_expire_and_escalate",
      description: "Expire + escalate.",
      enabled: false,
      cron_default: "* * * * *",
      cron_demo: "*/15 * * * * *",
      cron_override: null,
      effective_cron: "* * * * *",
      last_run_at: null,
      next_run_at: null,
    },
  ],
};

const MOCK_HEALTH = {
  healthy: true,
  issues: [],
  last_tick_at: "2026-06-07T10:00:00Z",
  failure_streaks: {},
};

describe("SchedulerPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        const method = init?.method ?? "GET";
        if (url.includes("/scheduler/status")) {
          return new Response(JSON.stringify(MOCK_STATUS), { status: 200 });
        }
        if (url.includes("/scheduler/health")) {
          return new Response(JSON.stringify(MOCK_HEALTH), { status: 200 });
        }
        if (url.includes("/scheduler/runs")) {
          return new Response(
            JSON.stringify({ items: [], total: 0, limit: 50, offset: 0 }),
            { status: 200 },
          );
        }
        if (url.includes("/scheduler/jobs/") && url.endsWith("/pause") && method === "POST") {
          return new Response(JSON.stringify(MOCK_STATUS.jobs[0]), { status: 200 });
        }
        if (url.includes("/scheduler/jobs/") && url.endsWith("/resume") && method === "POST") {
          return new Response(JSON.stringify(MOCK_STATUS.jobs[1]), { status: 200 });
        }
        if (url.includes("/scheduler/jobs/") && url.endsWith("/trigger") && method === "POST") {
          return new Response(
            JSON.stringify({ job_name: "auto_run_cycle", triggered: true, detail: null }),
            { status: 200 },
          );
        }
        if (url.includes("/scheduler/demo-mode") && method === "POST") {
          return new Response(
            JSON.stringify({ ...MOCK_STATUS, demo_mode: true }),
            { status: 200 },
          );
        }
        throw new Error(`Unmocked: ${method} ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the page with summary tiles and job grid", async () => {
    renderWithClient(<SchedulerPage />);
    expect(await screen.findByTestId("scheduler-page")).toBeInTheDocument();
    expect(await screen.findByTestId("scheduler-summary")).toBeInTheDocument();
    expect(await screen.findByTestId("job-grid")).toBeInTheDocument();
    const cards = await screen.findAllByTestId("job-status-card");
    expect(cards).toHaveLength(2);
  });

  it("marks paused jobs with the warning state", async () => {
    renderWithClient(<SchedulerPage />);
    const cards = await screen.findAllByTestId("job-status-card");
    const paused = cards.find((c) => c.getAttribute("data-job-name") === "auto_expire_and_escalate");
    expect(paused).not.toBeNull();
    expect(paused).toHaveAttribute("data-enabled", "false");
  });

  it("clicking Trigger now calls the API", async () => {
    renderWithClient(<SchedulerPage />);
    await screen.findAllByTestId("job-status-card");
    const triggers = screen.getAllByTestId("trigger-now");
    fireEvent.click(triggers[0]);
    await waitFor(() => {
      const calls = (global.fetch as any).mock.calls.filter((c: any[]) =>
        String(c[0]).endsWith("/trigger"),
      );
      expect(calls.length).toBeGreaterThan(0);
    });
  });

  it("toggling demo mode posts the new state", async () => {
    renderWithClient(<SchedulerPage />);
    await screen.findAllByTestId("job-status-card");
    const btn = screen.getByTestId("demo-mode-toggle");
    fireEvent.click(btn);
    await waitFor(() => {
      const calls = (global.fetch as any).mock.calls.filter((c: any[]) =>
        String(c[0]).endsWith("/scheduler/demo-mode"),
      );
      expect(calls.length).toBeGreaterThan(0);
    });
  });
});
