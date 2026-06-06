import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { ReplyIntelligencePanel } from "@/components/ui/reply-intelligence-panel";

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const MOCK_DIST = {
  window_days: 30,
  total: 12,
  counts: [
    { intent: "accept", count: 6 },
    { intent: "decline", count: 2 },
    { intent: "reschedule_request", count: 2 },
    { intent: "out_of_town", count: 1 },
    { intent: "medical_defer", count: 1 },
    { intent: "unrelated_question", count: 0 },
    { intent: "stop", count: 0 },
    { intent: "unknown", count: 0 },
  ],
  avg_confidence: 0.83,
  fallback_rate: 0.17,
  top_reschedule_reasons: ["school exam", "out of town for wedding"],
};

const MOCK_HIST = Array.from({ length: 10 }, (_, i) => ({
  low: i / 10,
  high: (i + 1) / 10,
  count: i === 8 ? 6 : i === 1 ? 2 : 0,
}));

describe("ReplyIntelligencePanel", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/reply-classifications/distribution")) {
          return new Response(JSON.stringify(MOCK_DIST), { status: 200 });
        }
        if (url.includes("/reply-classifications/confidence-histogram")) {
          return new Response(JSON.stringify(MOCK_HIST), { status: 200 });
        }
        throw new Error(`Unmocked: ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the distribution bar and legend", async () => {
    renderWithClient(<ReplyIntelligencePanel />);
    expect(await screen.findByTestId("reply-intelligence-panel")).toBeInTheDocument();
    expect(screen.getByTestId("intent-distribution")).toBeInTheDocument();
    expect(screen.getByTestId("intent-legend")).toBeInTheDocument();
    // The two non-zero intents render segments
    expect(screen.getByTestId("intent-segment-accept")).toBeInTheDocument();
    expect(screen.getByTestId("intent-segment-decline")).toBeInTheDocument();
  });

  it("renders the confidence histogram", async () => {
    renderWithClient(<ReplyIntelligencePanel />);
    expect(await screen.findByTestId("confidence-histogram")).toBeInTheDocument();
    // Bucket 8 (0.8-0.9) has count 6 — bar is non-empty
    expect(screen.getByTestId("hist-bucket-8")).toBeInTheDocument();
  });

  it("renders the top reschedule reasons", async () => {
    renderWithClient(<ReplyIntelligencePanel />);
    expect(await screen.findByTestId("top-reschedule-reasons")).toBeInTheDocument();
    expect(screen.getByText("school exam")).toBeInTheDocument();
  });

  it("shows empty state when there are no classifications", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/distribution")) {
          return new Response(
            JSON.stringify({ ...MOCK_DIST, total: 0, counts: MOCK_DIST.counts.map((c) => ({ ...c, count: 0 })) }),
            { status: 200 },
          );
        }
        if (url.includes("/confidence-histogram")) {
          return new Response(JSON.stringify(MOCK_HIST.map((b) => ({ ...b, count: 0 }))), { status: 200 });
        }
        throw new Error(`Unmocked: ${url}`);
      }),
    );
    renderWithClient(<ReplyIntelligencePanel />);
    expect(await screen.findByText(/No replies classified/i)).toBeInTheDocument();
  });
});
