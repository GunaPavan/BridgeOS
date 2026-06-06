import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChurnBar } from "@/components/ui/churn-bar";

describe("ChurnBar", () => {
  it("rounds the value to a percentage", () => {
    render(<ChurnBar value={0.4262} label="90d" />);
    expect(screen.getByText("43%")).toBeInTheDocument();
    expect(screen.getByText("90d")).toBeInTheDocument();
  });

  it("clamps values above 1.0", () => {
    render(<ChurnBar value={1.5} label="60d" />);
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("clamps values below 0", () => {
    render(<ChurnBar value={-0.2} label="30d" />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });

  it("renders 0% when value is exactly zero", () => {
    render(<ChurnBar value={0} label="90d" />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });
});
