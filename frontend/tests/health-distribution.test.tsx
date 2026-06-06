import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HealthDistribution } from "@/components/ui/health-distribution";

describe("HealthDistribution", () => {
  it("renders the title and total bridge count", () => {
    render(
      <HealthDistribution
        title="Cohort health"
        counts={{ stable: 30, at_risk: 12, critical: 8 }}
      />,
    );
    expect(screen.getByText(/cohort health/i)).toBeInTheDocument();
    expect(screen.getByText(/50 bridges/i)).toBeInTheDocument();
  });

  it("renders the legend with all three buckets and their counts", () => {
    render(
      <HealthDistribution
        title="ML health"
        counts={{ stable: 30, at_risk: 12, critical: 8 }}
      />,
    );
    const root = screen.getByTestId("health-distribution");
    expect(within(root).getByText("Stable")).toBeInTheDocument();
    expect(within(root).getByText("At risk")).toBeInTheDocument();
    expect(within(root).getByText("Critical")).toBeInTheDocument();
    expect(within(root).getByText("30")).toBeInTheDocument();
    expect(within(root).getByText("12")).toBeInTheDocument();
    expect(within(root).getByText("8")).toBeInTheDocument();
  });

  it("handles a zero-total cohort gracefully", () => {
    render(
      <HealthDistribution
        title="empty"
        counts={{ stable: 0, at_risk: 0, critical: 0 }}
      />,
    );
    expect(screen.getByText(/0 bridges/i)).toBeInTheDocument();
  });
});
