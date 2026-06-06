import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SwapPanel } from "@/components/ui/swap-panel";
import type { SwapRequest, SwapRequestsList } from "@/lib/api";

function makeSwap(overrides: Partial<SwapRequest> = {}): SwapRequest {
  return {
    id: "sw1",
    from_donor_id: "d-a",
    from_donor_name: "Aishwarya Murthy",
    to_donor_id: "d-b",
    to_donor_name: "Rohan Iyer",
    from_slot_date: "2026-06-10",
    to_slot_date: "2026-06-17",
    status: "proposed",
    expires_at: "2026-06-12T00:00:00Z",
    created_at: "2026-06-03T10:00:00Z",
    accepted_at: null,
    rejected_at: null,
    ...overrides,
  };
}

function makeList(swaps: SwapRequest[]): SwapRequestsList {
  return { bridge_id: "b1", swaps };
}

function renderWithClient(
  ui: React.ReactNode,
  payload: SwapRequestsList,
) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    })),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

describe("SwapPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders one row per swap request when there are any", async () => {
    renderWithClient(
      <SwapPanel bridgeId="b1" />,
      makeList([
        makeSwap(),
        makeSwap({ id: "sw2", status: "accepted" }),
        makeSwap({ id: "sw3", status: "rejected" }),
      ]),
    );
    await waitFor(() =>
      expect(screen.getByTestId("swap-panel")).toBeInTheDocument(),
    );
    expect(screen.getAllByTestId("swap-row")).toHaveLength(3);
    expect(screen.getAllByText("Aishwarya Murthy")).toHaveLength(3);
    expect(screen.getAllByText("Rohan Iyer")).toHaveLength(3);
  });

  it("renders nothing when the swaps list is empty", async () => {
    renderWithClient(<SwapPanel bridgeId="b1" />, makeList([]));
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId("swap-panel")).not.toBeInTheDocument();
  });

  it("status pills carry the correct data-status attribute per row", async () => {
    renderWithClient(
      <SwapPanel bridgeId="b1" />,
      makeList([
        makeSwap({ id: "sw1", status: "proposed" }),
        makeSwap({ id: "sw2", status: "accepted" }),
        makeSwap({ id: "sw3", status: "rejected" }),
        makeSwap({ id: "sw4", status: "expired" }),
      ]),
    );
    await waitFor(() =>
      expect(screen.getByTestId("swap-panel")).toBeInTheDocument(),
    );
    const rows = screen.getAllByTestId("swap-row");
    const statuses = rows.map((r) => r.dataset.status).sort();
    expect(statuses).toEqual(["accepted", "expired", "proposed", "rejected"]);
    // Awaiting YES label appears only on the proposed row
    expect(screen.getByText(/Awaiting YES/i)).toBeInTheDocument();
    expect(screen.getByText(/Accepted/i)).toBeInTheDocument();
    expect(screen.getByText(/Declined/i)).toBeInTheDocument();
    expect(screen.getByText(/Expired/i)).toBeInTheDocument();
  });
});
