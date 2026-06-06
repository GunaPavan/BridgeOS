import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import OutreachPage from "@/app/(app)/outreach/page";

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const MOCK_LIST = {
  total: 2,
  items: [
    {
      id: "wave-1",
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
    },
    {
      id: "wave-2",
      patient_id: "p-2",
      bridge_id: "b-2",
      slot_date: "2026-06-10",
      tier: "tier_2",
      urgency: "high",
      status: "accepted",
      target_p_accept: 0.85,
      realised_p_accept: 0.88,
      gap_days_at_creation: 4,
      pool_size_at_creation: 90,
      triggered_by: "escalate_from_abc12345",
      created_at: "2026-06-06T10:00:00Z",
      expires_at: "2026-06-06T12:00:00Z",
      resolved_at: "2026-06-06T11:15:00Z",
      resolved_by_donor_id: "d-7",
    },
  ],
};

describe("OutreachPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/outreach/waves")) {
          return new Response(JSON.stringify(MOCK_LIST), {
            status: 200,
            headers: { "content-type": "application/json" },
          });
        }
        if (url.includes("/outreach/expire-and-sweep")) {
          return new Response(
            JSON.stringify({
              expired_count: 0,
              expired_waves: [],
              escalated_waves: [],
            }),
            { status: 200, headers: { "content-type": "application/json" } },
          );
        }
        if (url.includes("/outreach/run-cycle")) {
          return new Response(
            JSON.stringify({
              summary: {
                cycle_at: "2026-06-06T12:00:00Z",
                open_slots: 5,
                waves_created: 5,
                pings_planned: 18,
                critical_slots: 3,
                high_slots: 1,
                medium_slots: 1,
                fully_covered_slots: 5,
                shortfall_slots: 0,
                dry_run: true,
              },
              allocations: MOCK_LIST.items.map((w, i) => ({
                patient_id: w.patient_id,
                patient_name: `Patient ${w.patient_id.slice(0, 4)}`,
                slot_date: w.slot_date,
                urgency: w.urgency,
                gap_days: w.gap_days_at_creation,
                target_p_accept: w.target_p_accept,
                realised_p_accept: w.realised_p_accept,
                fully_covered: true,
                pool_size: w.pool_size_at_creation,
                batch_size: 2,
                batch: [
                  {
                    donor_id: `donor-${i}-a`,
                    donor_name: `Donor ${i}A`,
                    blood_group: "O+",
                    city: "Hyderabad",
                    preferred_language: "en",
                  },
                  {
                    donor_id: `donor-${i}-b`,
                    donor_name: `Donor ${i}B`,
                    blood_group: "O+",
                    city: "Hyderabad",
                    preferred_language: "te",
                  },
                ],
              })),
            }),
            { status: 200, headers: { "content-type": "application/json" } },
          );
        }
        throw new Error(`Unmocked fetch: ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the waves list with header + actions + status filter chips", async () => {
    renderWithClient(<OutreachPage />);

    await waitFor(() => {
      expect(screen.getByTestId("outreach-page")).toBeInTheDocument();
    });

    expect(screen.getByTestId("run-cycle-button")).toBeInTheDocument();
    expect(screen.getByTestId("expire-sweep-button")).toBeInTheDocument();
    expect(screen.getByTestId("status-filter")).toBeInTheDocument();

    const rows = await screen.findAllByTestId("wave-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("data-status", "active");
    expect(rows[1]).toHaveAttribute("data-status", "accepted");
  });

  it("opens the run-cycle modal and previews allocations with selection rows", async () => {
    renderWithClient(<OutreachPage />);
    await screen.findAllByTestId("wave-row");

    fireEvent.click(screen.getByTestId("run-cycle-button"));
    expect(screen.getByTestId("run-cycle-modal")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("dry-run-button"));

    await waitFor(() => {
      expect(screen.getByTestId("cycle-preview")).toBeInTheDocument();
    });

    // Selectable allocation rows
    const rows = screen.getAllByTestId("allocation-row");
    expect(rows.length).toBe(2);
    // Each carries a checkbox (default checked)
    const checkboxes = screen.getAllByTestId(
      "allocation-checkbox",
    ) as HTMLInputElement[];
    expect(checkboxes).toHaveLength(2);
    expect(checkboxes[0].checked).toBe(true);

    // Commit button enabled (we have selections)
    expect(screen.getByTestId("commit-cycle")).not.toBeDisabled();
  });

  it("Select none / Select all toggle every row's checkbox", async () => {
    renderWithClient(<OutreachPage />);
    await screen.findAllByTestId("wave-row");

    fireEvent.click(screen.getByTestId("run-cycle-button"));
    fireEvent.click(screen.getByTestId("dry-run-button"));
    await screen.findByTestId("cycle-preview");

    // Default: all 2 checked
    const initiallyChecked = (
      screen.getAllByTestId("allocation-checkbox") as HTMLInputElement[]
    ).filter((c) => c.checked).length;
    expect(initiallyChecked).toBe(2);

    // Select none
    fireEvent.click(screen.getByTestId("select-none-button"));
    const afterNone = (
      screen.getAllByTestId("allocation-checkbox") as HTMLInputElement[]
    ).filter((c) => c.checked).length;
    expect(afterNone).toBe(0);
    expect(screen.getByTestId("commitable-count")).toHaveTextContent("0");
    expect(screen.getByTestId("commit-cycle")).toBeDisabled();

    // Select all
    fireEvent.click(screen.getByTestId("select-all-button"));
    const afterAll = (
      screen.getAllByTestId("allocation-checkbox") as HTMLInputElement[]
    ).filter((c) => c.checked).length;
    expect(afterAll).toBe(2);
    expect(screen.getByTestId("commitable-count")).toHaveTextContent("2");
    expect(screen.getByTestId("commit-cycle")).not.toBeDisabled();
  });

  it("Expire+escalate button shows a feedback banner explaining what happened", async () => {
    renderWithClient(<OutreachPage />);
    await screen.findAllByTestId("wave-row");

    fireEvent.click(screen.getByTestId("expire-sweep-button"));

    await waitFor(() => {
      expect(screen.getByTestId("sweep-result-banner")).toBeInTheDocument();
    });
    // When zero waves expired, banner explains why nothing changed
    expect(screen.getByTestId("sweep-result-banner")).toHaveTextContent(
      /Nothing to expire/i,
    );
  });

  it("Clicking an individual checkbox updates the visible count live", async () => {
    renderWithClient(<OutreachPage />);
    await screen.findAllByTestId("wave-row");

    fireEvent.click(screen.getByTestId("run-cycle-button"));
    fireEvent.click(screen.getByTestId("dry-run-button"));
    await screen.findByTestId("cycle-preview");

    // Both rows seeded as checked + 2 donors each → commitable = 2
    expect(screen.getByTestId("commitable-count")).toHaveTextContent("2");
    // Button label reflects the SELECTED count (matches checkboxes)
    expect(screen.getByTestId("commit-cycle")).toHaveTextContent(
      /Commit selected \(2\)/,
    );

    // Uncheck the first row
    const checkboxes = screen.getAllByTestId(
      "allocation-checkbox",
    ) as HTMLInputElement[];
    fireEvent.click(checkboxes[0]);
    expect(checkboxes[0].checked).toBe(false);

    // Both the footer counter AND the button label drop to 1
    expect(screen.getByTestId("commitable-count")).toHaveTextContent("1");
    expect(screen.getByTestId("commit-cycle")).toHaveTextContent(
      /Commit selected \(1\)/,
    );
    expect(screen.getByTestId("commit-cycle")).not.toBeDisabled();

    // Uncheck the second row → button shows (0) and is disabled
    fireEvent.click(checkboxes[1]);
    expect(screen.getByTestId("commit-cycle")).toHaveTextContent(
      /Commit selected \(0\)/,
    );
    expect(screen.getByTestId("commit-cycle")).toBeDisabled();
  });

  it("Per-row expand reveals donor pills + Add-donor search field", async () => {
    renderWithClient(<OutreachPage />);
    await screen.findAllByTestId("wave-row");

    fireEvent.click(screen.getByTestId("run-cycle-button"));
    fireEvent.click(screen.getByTestId("dry-run-button"));
    await screen.findByTestId("cycle-preview");

    const expandButtons = screen.getAllByTestId("allocation-expand");
    fireEvent.click(expandButtons[0]);

    // Editor surface shows up (mock allocation has empty batch; check the input)
    expect(await screen.findByTestId("allocation-editor")).toBeInTheDocument();
    expect(screen.getByTestId("add-donor-search")).toBeInTheDocument();
  });
});
