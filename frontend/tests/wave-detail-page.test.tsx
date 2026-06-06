import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";

import WaveDetailPage from "@/app/(app)/outreach/[id]/page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "wave-uuid-12345678" }),
}));

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const MOCK_WAVE = {
  id: "wave-uuid-12345678",
  patient_id: "p-1",
  bridge_id: "b-1",
  slot_date: "2026-06-08",
  tier: "tier_1",
  urgency: "critical",
  status: "active",
  target_p_accept: 0.95,
  realised_p_accept: 0.94,
  gap_days_at_creation: 2,
  pool_size_at_creation: 120,
  triggered_by: "auto_cycle",
  created_at: "2026-06-06T12:00:00Z",
  expires_at: "2026-06-06T12:30:00Z",
  resolved_at: null,
  resolved_by_donor_id: null,
  pings: [
    {
      id: "p-1",
      donor_id: "donor-id-aaaaaa",
      channel: "whatsapp",
      response: "pending",
      sent_at: "2026-06-06T12:00:00Z",
      expires_at: "2026-06-06T12:30:00Z",
      response_at: null,
      composite_score: 0.78,
      adjusted_response_rate: 0.42,
      language: "en",
    },
    {
      id: "p-2",
      donor_id: "donor-id-bbbbbb",
      channel: "whatsapp",
      response: "accepted",
      sent_at: "2026-06-06T12:00:00Z",
      expires_at: "2026-06-06T12:30:00Z",
      response_at: "2026-06-06T12:14:00Z",
      composite_score: 0.85,
      adjusted_response_rate: 0.50,
      language: "te",
    },
  ],
};

describe("WaveDetailPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/outreach/waves/")) {
          return new Response(JSON.stringify(MOCK_WAVE), {
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

  it("renders wave header + action row + ping mix + pings table", async () => {
    renderWithClient(<WaveDetailPage />);
    await waitFor(() => {
      expect(screen.getByTestId("wave-detail-page")).toBeInTheDocument();
    });
    expect(screen.getByTestId("wave-status-pill")).toHaveTextContent(/active/i);
    expect(screen.getByTestId("wave-actions")).toBeInTheDocument();
    expect(screen.getByTestId("dispatch-button")).toBeInTheDocument();
    expect(screen.getByTestId("dispatch-emergency-button")).toBeInTheDocument();
    expect(screen.getByTestId("promote-manual-button")).toBeInTheDocument();
    expect(screen.getByTestId("ping-count-pending")).toHaveTextContent("1");
    expect(screen.getByTestId("ping-count-accepted")).toHaveTextContent("1");

    const rows = screen.getAllByTestId("ping-row");
    expect(rows).toHaveLength(2);
  });

  it("shows the Drop button only on PENDING pings of ACTIVE waves", async () => {
    renderWithClient(<WaveDetailPage />);
    await screen.findAllByTestId("ping-row");
    // Two pings: one pending → drop visible; one accepted → drop hidden
    const dropButtons = screen.getAllByTestId("force-exclude-button");
    expect(dropButtons).toHaveLength(1);
  });
});
