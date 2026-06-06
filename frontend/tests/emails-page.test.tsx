import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import EmailsPage from "@/app/(app)/emails/page";

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const MOCK_DIST = {
  window_days: 30,
  total: 2,
  sent: 1,
  failed: 0,
  mocked: 1,
  by_template: [
    { template_key: "caregiver_daily_digest", sent: 1, failed: 0, mocked: 1, skipped: 0 },
  ],
};

const MOCK_LIST = {
  items: [
    {
      id: "e-1",
      direction: "outbound",
      recipient_email: "anita@example.com",
      from_email: "ops@team019.example",
      subject: "Today's bridge update for Riya",
      body: "Hi Anita,\nAll is well.\n— Team",
      template_key: "caregiver_daily_digest",
      language: "en",
      ses_message_id: "real-id-1",
      status: "sent",
      is_mock: false,
      error_message: null,
      donor_id: null,
      caregiver_for_patient_id: "p-1",
      created_at: "2026-06-07T08:00:00Z",
      sent_at: "2026-06-07T08:00:00Z",
    },
    {
      id: "e-2",
      direction: "outbound",
      recipient_email: "raj@example.com",
      from_email: "ops@team019.example",
      subject: "Urgent",
      body: "Need a donor for Vikram tomorrow.",
      template_key: "caregiver_emergency_alert",
      language: "en",
      ses_message_id: null,
      status: "mocked",
      is_mock: true,
      error_message: null,
      donor_id: null,
      caregiver_for_patient_id: "p-2",
      created_at: "2026-06-07T09:00:00Z",
      sent_at: null,
    },
  ],
  total: 2,
  limit: 100,
  offset: 0,
};

describe("EmailsPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/emails/distribution")) {
          return new Response(JSON.stringify(MOCK_DIST), { status: 200 });
        }
        if (url.includes("/emails")) {
          return new Response(JSON.stringify(MOCK_LIST), { status: 200 });
        }
        throw new Error(`Unmocked: ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the page header, filter bar, and email list", async () => {
    renderWithClient(<EmailsPage />);
    expect(await screen.findByTestId("emails-page")).toBeInTheDocument();
    expect(screen.getByText(/Outbound emails/i)).toBeInTheDocument();
    expect(screen.getByTestId("emails-filters")).toBeInTheDocument();
    // List rows show recipients (scope to the main list, since the embedded
    // EmailChannelPanel also renders some recipients in its "recent" tile)
    const rows = await screen.findAllByTestId("email-row");
    expect(rows.length).toBe(2);
    const listTexts = rows.map((r) => r.textContent ?? "");
    expect(listTexts.some((t) => t.includes("anita@example.com"))).toBe(true);
    expect(listTexts.some((t) => t.includes("raj@example.com"))).toBe(true);
  });

  it("shows the body in the preview pane when a row is clicked", async () => {
    renderWithClient(<EmailsPage />);
    const rows = await screen.findAllByTestId("email-row");
    // First row hasn't been clicked yet — preview pane is empty
    expect(screen.getByText(/Select a message to preview/i)).toBeInTheDocument();

    fireEvent.click(rows[0]);
    expect(await screen.findByTestId("email-body")).toBeInTheDocument();
    expect(screen.getByText("Today's bridge update for Riya")).toBeInTheDocument();
    expect(screen.getByTestId("email-body").textContent).toContain("All is well");
  });
});
