import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { EmergencyButton } from "@/components/ui/emergency-button";

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("EmergencyButton", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/outreach/emergency") && init?.method === "POST") {
          return new Response(
            JSON.stringify({
              event_id: "evt-uuid-12345678",
              wave_id: "wave-uuid-12345678",
              reachable_count: 23,
              pool_size_before_filter: 6949,
              deadline_at: "2026-06-06T16:00:00Z",
              reach_window_min: 240,
              status: "active",
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

  it("renders the red button and reveals the dialog when clicked", async () => {
    renderWithClient(
      <EmergencyButton patientId="pat-1" patientName="Patient 9872DA" />,
    );

    const btn = screen.getByTestId("emergency-button");
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);

    expect(screen.getByTestId("emergency-dialog")).toBeInTheDocument();
    expect(screen.getByTestId("emergency-coordinator")).toBeInTheDocument();
    expect(screen.getByTestId("emergency-justification")).toBeInTheDocument();
  });

  it("trigger button stays disabled until coord + justification are present", () => {
    renderWithClient(
      <EmergencyButton patientId="pat-1" patientName="P" />,
    );
    fireEvent.click(screen.getByTestId("emergency-button"));
    const confirm = screen.getByTestId("emergency-confirm");
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByTestId("emergency-coordinator"), {
      target: { value: "Aakash" },
    });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByTestId("emergency-justification"), {
      target: { value: "Severe Hb drop — needs immediate transfusion" },
    });
    expect(confirm).not.toBeDisabled();
  });

  it("submits the trigger and shows the result panel with reachable count", async () => {
    renderWithClient(
      <EmergencyButton patientId="pat-1" patientName="P" />,
    );
    fireEvent.click(screen.getByTestId("emergency-button"));
    fireEvent.change(screen.getByTestId("emergency-coordinator"), {
      target: { value: "Aakash" },
    });
    fireEvent.change(screen.getByTestId("emergency-justification"), {
      target: { value: "Critical" },
    });
    fireEvent.click(screen.getByTestId("emergency-confirm"));

    await waitFor(() => {
      expect(screen.getByTestId("emergency-success")).toBeInTheDocument();
    });
    expect(screen.getByTestId("reachable-count")).toHaveTextContent("23");
  });
});
