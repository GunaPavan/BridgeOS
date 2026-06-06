import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BarList } from "@/components/ui/bar-list";

describe("BarList", () => {
  it("renders each item with its label and count", () => {
    render(
      <BarList
        title="By blood group"
        total={500}
        items={[
          { label: "O+", count: 187 },
          { label: "B+", count: 161 },
          { label: "A+", count: 113 },
        ]}
      />,
    );
    expect(screen.getByText(/by blood group/i)).toBeInTheDocument();
    expect(screen.getByText(/500 total/i)).toBeInTheDocument();
    const root = screen.getByTestId("bar-list");
    expect(within(root).getByText("O+")).toBeInTheDocument();
    expect(within(root).getByText("187")).toBeInTheDocument();
    expect(within(root).getByText("B+")).toBeInTheDocument();
    expect(within(root).getByText("161")).toBeInTheDocument();
  });

  it("uses a custom testId when provided", () => {
    render(
      <BarList
        title="x"
        items={[{ label: "a", count: 1 }]}
        testId="my-chart"
      />,
    );
    expect(screen.getByTestId("my-chart")).toBeInTheDocument();
  });

  it("omits the total line when not provided", () => {
    render(<BarList title="x" items={[{ label: "a", count: 1 }]} />);
    expect(screen.queryByText(/total/i)).not.toBeInTheDocument();
  });
});
