import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { PingFollowupTimeline } from "@/components/ui/ping-followup-timeline";

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const FRESH_PING = {
  ping_id: "p-1",
  wave_id: "w-1",
  donor_id: "d-1",
  response: "pending",
  sent_at: "2026-06-07T08:00:00Z",
  response_at: null,
  nudge: { count: 0, last_sent_at: null },
  reminder: { sent_at: null },
  thank_you: { sent_at: null },
};

const FULL_TIMELINE_PING = {
  ping_id: "p-2",
  wave_id: "w-2",
  donor_id: "d-2",
  response: "accepted",
  sent_at: "2026-06-05T08:00:00Z",
  response_at: "2026-06-05T08:30:00Z",
  nudge: { count: 1, last_sent_at: "2026-06-05T13:00:00Z" },
  reminder: { sent_at: "2026-06-06T09:00:00Z" },
  thank_you: { sent_at: "2026-06-07T09:00:00Z" },
};

describe("PingFollowupTimeline", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        const method = init?.method ?? "GET";
        if (url.includes("/follow-ups/nudge") && method === "POST") {
          return new Response(
            JSON.stringify({
              ping_id: "p-1",
              sent: true,
              nudge_count: 1,
              last_nudge_at: "2026-06-07T10:00:00Z",
            }),
            { status: 200 },
          );
        }
        if (url.includes("/p-1/follow-ups")) {
          return new Response(JSON.stringify(FRESH_PING), { status: 200 });
        }
        if (url.includes("/p-2/follow-ups")) {
          return new Response(JSON.stringify(FULL_TIMELINE_PING), { status: 200 });
        }
        throw new Error(`Unmocked: ${method} ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the four-stage timeline with only Sent done on a fresh ping", async () => {
    renderWithClient(<PingFollowupTimeline pingId="p-1" />);
    expect(await screen.findByTestId("ping-followup-timeline")).toBeInTheDocument();
    expect(screen.getByTestId("stage-sent")).toHaveAttribute("data-done", "true");
    expect(screen.getByTestId("stage-nudged")).toHaveAttribute("data-done", "false");
    expect(screen.getByTestId("stage-reminded")).toHaveAttribute("data-done", "false");
    expect(screen.getByTestId("stage-thanked")).toHaveAttribute("data-done", "false");
  });

  it("renders all four stages as done when fully followed up", async () => {
    renderWithClient(<PingFollowupTimeline pingId="p-2" />);
    await screen.findByTestId("ping-followup-timeline");
    expect(screen.getByTestId("stage-sent")).toHaveAttribute("data-done", "true");
    expect(screen.getByTestId("stage-nudged")).toHaveAttribute("data-done", "true");
    expect(screen.getByTestId("stage-reminded")).toHaveAttribute("data-done", "true");
    expect(screen.getByTestId("stage-thanked")).toHaveAttribute("data-done", "true");
    // Manual nudge button only shows while response=pending; this ping is accepted
    expect(screen.queryByTestId("manual-nudge-button")).toBeNull();
  });

  it("manual Nudge now button triggers the API for pending pings", async () => {
    renderWithClient(<PingFollowupTimeline pingId="p-1" />);
    await screen.findByTestId("ping-followup-timeline");
    const btn = screen.getByTestId("manual-nudge-button");
    fireEvent.click(btn);
    await waitFor(() => {
      const calls = (global.fetch as any).mock.calls.filter((c: any[]) =>
        String(c[0]).endsWith("/follow-ups/nudge"),
      );
      expect(calls.length).toBeGreaterThan(0);
    });
  });
});
