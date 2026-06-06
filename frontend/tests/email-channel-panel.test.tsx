import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { EmailChannelPanel } from "@/components/ui/email-channel-panel";

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const MOCK_DIST = {
  window_days: 30,
  total: 7,
  sent: 3,
  failed: 1,
  mocked: 3,
  by_template: [
    { template_key: "caregiver_daily_digest", sent: 3, failed: 0, mocked: 2, skipped: 0 },
    { template_key: "caregiver_emergency_alert", sent: 0, failed: 1, mocked: 1, skipped: 0 },
  ],
};

const MOCK_RECENT = {
  items: [
    {
      id: "e-1",
      direction: "outbound",
      recipient_email: "caregiver1@example.com",
      from_email: "ops@team019.example",
      subject: "Digest",
      body: "...",
      template_key: "caregiver_daily_digest",
      language: "en",
      ses_message_id: "real-id-1",
      status: "sent",
      is_mock: false,
      error_message: null,
      donor_id: null,
      caregiver_for_patient_id: null,
      created_at: "2026-06-07T08:00:00Z",
      sent_at: "2026-06-07T08:00:00Z",
    },
  ],
  total: 1,
  limit: 5,
  offset: 0,
};

describe("EmailChannelPanel", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/emails/distribution")) {
          return new Response(JSON.stringify(MOCK_DIST), { status: 200 });
        }
        if (url.includes("/emails?") || url.endsWith("/emails")) {
          return new Response(JSON.stringify(MOCK_RECENT), { status: 200 });
        }
        throw new Error(`Unmocked: ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders KPIs, per-template table and recent recipients", async () => {
    renderWithClient(<EmailChannelPanel />);
    expect(await screen.findByTestId("email-channel-panel")).toBeInTheDocument();
    const kpis = screen.getAllByTestId("email-kpi");
    expect(kpis).toHaveLength(4); // total, sent, mocked, failed
    expect(screen.getByTestId("email-by-template")).toBeInTheDocument();
    expect(screen.getByText(/Daily digest/i)).toBeInTheDocument();
    expect(await screen.findByText("caregiver1@example.com")).toBeInTheDocument();
  });

  it("shows empty state when no emails sent", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/distribution")) {
          return new Response(
            JSON.stringify({ ...MOCK_DIST, total: 0, sent: 0, failed: 0, mocked: 0, by_template: [] }),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify({ items: [], total: 0, limit: 5, offset: 0 }), { status: 200 });
      }),
    );
    renderWithClient(<EmailChannelPanel />);
    expect(await screen.findByText(/No emails sent/i)).toBeInTheDocument();
  });
});
