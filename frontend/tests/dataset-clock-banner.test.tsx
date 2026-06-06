import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DatasetClockBanner } from "@/components/ui/dataset-clock-banner";
import type { SystemClock } from "@/lib/api";

function payload(overrides: Partial<SystemClock> = {}): SystemClock {
  return {
    today: "2026-02-27",
    wall_clock: "2026-06-06",
    is_anchored: true,
    days_anchored_back: 99,
    label:
      "System clock anchored to dataset reference 2026-02-27 (wall-clock is 99 days ahead)",
    ...overrides,
  };
}

function renderWithClient(p: SystemClock) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => p,
      text: async () => JSON.stringify(p),
    })),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DatasetClockBanner />
    </QueryClientProvider>,
  );
}

describe("DatasetClockBanner", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the anchored date when the dataset is stale", async () => {
    renderWithClient(payload());
    await waitFor(() =>
      expect(screen.getByTestId("dataset-clock-banner")).toBeInTheDocument(),
    );
    const banner = screen.getByTestId("dataset-clock-banner");
    expect(banner.dataset.anchored).toBe("true");
    expect(banner).toHaveTextContent("2026-02-27");
    expect(banner).toHaveTextContent(/99d behind real time/);
  });

  it("shows 'Live' when the system clock is real-time (not anchored)", async () => {
    renderWithClient(
      payload({
        today: "2026-06-06",
        wall_clock: "2026-06-06",
        is_anchored: false,
        days_anchored_back: 0,
        label: "System clock: 2026-06-06 (live)",
      }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("dataset-clock-banner")).toBeInTheDocument(),
    );
    const banner = screen.getByTestId("dataset-clock-banner");
    expect(banner.dataset.anchored).toBe("false");
    expect(banner).toHaveTextContent("Live");
  });
});
