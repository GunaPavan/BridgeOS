import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { EventsFeedPanel } from "@/components/ui/events-feed-panel";

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const MOCK_STATUS = {
  running: true,
  delivered: 5,
  failed: 0,
  last_tick_at: "2026-06-07T10:00:00Z",
  topics: [
    { topic: "donor-reply-accept", subscribers: ["ema_feedback_audit", "caregiver_notify"] },
    { topic: "donor-reply-decline", subscribers: ["ema_feedback_audit"] },
    { topic: "donor-reply-opt-out", subscribers: ["cooldown_opt_out_audit"] },
    { topic: "donor-reply-out-of-town", subscribers: ["cooldown_out_of_town_audit"] },
    { topic: "donor-reply-medical-defer", subscribers: ["cooldown_medical_audit"] },
    { topic: "wave-expired", subscribers: ["allocator_refire_audit"] },
    { topic: "wave-accepted", subscribers: ["sibling_cancel_audit"] },
  ],
};

const MOCK_EVENTS = [
  {
    message_id: "m-1",
    topic_name: "team019-bridge-os-donor-reply-accept",
    body: { donor_id: "d-1" },
    published_at: "2026-06-07T10:00:00Z",
    is_mock: false,
  },
];

describe("EventsFeedPanel", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/events/status")) {
          return new Response(JSON.stringify(MOCK_STATUS), { status: 200 });
        }
        if (url.includes("/events/recent")) {
          return new Response(JSON.stringify(MOCK_EVENTS), { status: 200 });
        }
        throw new Error(`Unmocked: ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders dispatcher status + topic list + recent events", async () => {
    renderWithClient(<EventsFeedPanel />);
    expect(await screen.findByTestId("events-feed-panel")).toBeInTheDocument();
    expect(await screen.findByTestId("events-topics")).toBeInTheDocument();
    expect(screen.getByTestId("topic-donor-reply-accept")).toBeInTheDocument();
    expect(screen.getByText(/dispatcher running/)).toBeInTheDocument();
    const row = await screen.findByTestId("event-row");
    expect(row).toBeInTheDocument();
    // The non-mock event renders a "live" badge — scope the match to the row
    // so it doesn't collide with the "delivered" word in the dispatcher status.
    expect(row.textContent?.toLowerCase()).toContain("live");
  });

  it("shows empty state when no events have been published yet", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/events/status")) {
          return new Response(JSON.stringify(MOCK_STATUS), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }),
    );
    renderWithClient(<EventsFeedPanel />);
    expect(await screen.findByText(/No events published yet/i)).toBeInTheDocument();
  });
});
