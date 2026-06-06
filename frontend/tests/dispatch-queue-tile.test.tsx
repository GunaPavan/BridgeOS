import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { DispatchQueueTile } from "@/components/ui/dispatch-queue-tile";

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function stubStatus(overrides: Partial<any> = {}) {
  const status = {
    primary_depth: 3,
    in_flight: 1,
    dlq_depth: 0,
    mode: "mock",
    error: null,
    worker_running: true,
    worker_received: 10,
    worker_sent: 7,
    worker_duplicates_skipped: 1,
    worker_failed: 1,
    worker_last_drained_at: "2026-06-07T10:00:00Z",
    worker_started_at: "2026-06-07T09:00:00Z",
    ...overrides,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";
      if (url.includes("/dispatch-queue/status")) {
        return new Response(JSON.stringify(status), { status: 200 });
      }
      if (url.includes("/dispatch-queue/replay-dlq") && method === "POST") {
        return new Response(JSON.stringify({ replayed: 2, failed: 0 }), { status: 200 });
      }
      throw new Error(`Unmocked: ${method} ${url}`);
    }),
  );
}

describe("DispatchQueueTile", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders depth + worker stats", async () => {
    stubStatus();
    renderWithClient(<DispatchQueueTile />);
    expect(await screen.findByTestId("dispatch-queue-tile")).toBeInTheDocument();
    expect(screen.getByTestId("dq-cell-primary-depth")).toHaveTextContent("3");
    expect(screen.getByTestId("dq-cell-in-flight")).toHaveTextContent("1");
    expect(screen.getByTestId("dq-cell-dlq-depth")).toHaveTextContent("0");
    expect(screen.getByText("mock")).toBeInTheDocument();
    expect(screen.getByText(/running/i)).toBeInTheDocument();
  });

  it("disables replay button when DLQ is empty", async () => {
    stubStatus({ dlq_depth: 0 });
    renderWithClient(<DispatchQueueTile />);
    const btn = await screen.findByTestId("replay-dlq-button");
    expect(btn).toBeDisabled();
  });

  it("enables replay button when DLQ has messages and POSTs on click", async () => {
    stubStatus({ dlq_depth: 2 });
    renderWithClient(<DispatchQueueTile />);
    const btn = await screen.findByTestId("replay-dlq-button");
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    await waitFor(() => {
      const calls = (global.fetch as any).mock.calls.filter((c: any[]) =>
        String(c[0]).endsWith("/replay-dlq"),
      );
      expect(calls.length).toBeGreaterThan(0);
    });
  });
});
