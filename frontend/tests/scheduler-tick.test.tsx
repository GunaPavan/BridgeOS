import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { SchedulerTick } from "@/components/ui/scheduler-tick";
import { DemoModeBanner } from "@/components/ui/demo-mode-banner";

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function stubStatus(overrides: Partial<any> = {}) {
  const now = Date.now();
  const next = new Date(now + 2 * 60 * 1000 + 14 * 1000).toISOString(); // ~2m 14s
  const status = {
    running: true,
    demo_mode: false,
    job_count: 1,
    enabled_count: 1,
    last_tick_at: null,
    failures_24h: 0,
    jobs: [
      {
        name: "auto_run_cycle",
        description: "Allocator.",
        enabled: true,
        cron_default: "*/5 * * * *",
        cron_demo: "*/30 * * * * *",
        cron_override: null,
        effective_cron: "*/5 * * * *",
        last_run_at: null,
        next_run_at: next,
      },
    ],
    ...overrides,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/scheduler/status")) {
        return new Response(JSON.stringify(status), { status: 200 });
      }
      throw new Error(`Unmocked: ${url}`);
    }),
  );
}

describe("SchedulerTick", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the live tick with a countdown when scheduler is running", async () => {
    stubStatus();
    renderWithClient(<SchedulerTick />);
    expect(await screen.findByTestId("scheduler-tick")).toBeInTheDocument();
    // "ticks in 2m 14s" — match either 2m 13s or 2m 14s (clock drift)
    expect(screen.getByTestId("scheduler-tick").textContent).toMatch(/Allocator ticks in/);
  });

  it("returns null when scheduler is not running", async () => {
    stubStatus({ running: false });
    const { container } = renderWithClient(<SchedulerTick />);
    // Wait a tick for the query to resolve
    await new Promise((r) => setTimeout(r, 50));
    expect(container.querySelector('[data-testid="scheduler-tick"]')).toBeNull();
  });

  it("indicates paused when job is disabled", async () => {
    stubStatus({
      jobs: [
        {
          name: "auto_run_cycle",
          description: "Allocator.",
          enabled: false,
          cron_default: "*/5 * * * *",
          cron_demo: "*/30 * * * * *",
          cron_override: null,
          effective_cron: "*/5 * * * *",
          last_run_at: null,
          next_run_at: null,
        },
      ],
    });
    renderWithClient(<SchedulerTick />);
    const tick = await screen.findByTestId("scheduler-tick");
    expect(tick.textContent).toMatch(/paused/);
  });
});

describe("DemoModeBanner", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the sticky banner when demo mode is on", async () => {
    stubStatus({ demo_mode: true });
    renderWithClient(<DemoModeBanner />);
    expect(await screen.findByTestId("demo-mode-banner")).toBeInTheDocument();
    expect(screen.getByText(/cadences compressed/i)).toBeInTheDocument();
  });

  it("renders nothing when demo mode is off", async () => {
    stubStatus({ demo_mode: false });
    const { container } = renderWithClient(<DemoModeBanner />);
    await new Promise((r) => setTimeout(r, 50));
    expect(container.querySelector('[data-testid="demo-mode-banner"]')).toBeNull();
  });
});
