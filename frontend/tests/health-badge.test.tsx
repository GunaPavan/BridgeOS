import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HealthBadge } from "@/components/ui/health-badge";

describe("HealthBadge", () => {
  it("renders 'Stable' label for stable health", () => {
    render(<HealthBadge health="stable" />);
    const badge = screen.getByTestId("health-badge");
    expect(badge).toHaveTextContent(/stable/i);
    expect(badge).toHaveAttribute("data-health", "stable");
    expect(badge.className).toMatch(/emerald/);
  });

  it("renders 'At risk' for at_risk health with amber styling", () => {
    render(<HealthBadge health="at_risk" />);
    const badge = screen.getByTestId("health-badge");
    expect(badge).toHaveTextContent(/at risk/i);
    expect(badge.className).toMatch(/amber/);
  });

  it("renders 'Critical' for critical health with red styling", () => {
    render(<HealthBadge health="critical" />);
    const badge = screen.getByTestId("health-badge");
    expect(badge).toHaveTextContent(/critical/i);
    expect(badge.className).toMatch(/red/);
  });

  it("accepts a custom className", () => {
    render(<HealthBadge health="stable" className="custom-class" />);
    expect(screen.getByTestId("health-badge").className).toMatch(/custom-class/);
  });
});
