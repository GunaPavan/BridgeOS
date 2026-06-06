import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Sparkline } from "@/components/ui/sparkline";

describe("Sparkline", () => {
  it("renders an SVG with the right point count", () => {
    render(<Sparkline values={[0.2, 0.3, 0.5, 0.8]} />);
    const svg = screen.getByTestId("sparkline");
    expect(svg.tagName.toLowerCase()).toBe("svg");
    expect(svg.dataset.points).toBe("4");
  });

  it("marks empty data with data-empty attribute", () => {
    render(<Sparkline values={[]} />);
    const svg = screen.getByTestId("sparkline");
    expect(svg.dataset.empty).toBe("true");
  });

  it("forwards width and height attributes to the SVG", () => {
    render(<Sparkline values={[0.1, 0.5, 0.9]} width={200} height={50} />);
    const svg = screen.getByTestId("sparkline");
    expect(svg.getAttribute("width")).toBe("200");
    expect(svg.getAttribute("height")).toBe("50");
  });

  it("draws a path element for non-empty data", () => {
    const { container } = render(<Sparkline values={[0.1, 0.3, 0.5]} />);
    const paths = container.querySelectorAll("path");
    // One area path + one line path = 2 paths
    expect(paths.length).toBeGreaterThanOrEqual(1);
    // The last circle marks the current value
    expect(container.querySelectorAll("circle").length).toBe(1);
  });

  it("can render line only (no area) when showArea is false", () => {
    const { container } = render(
      <Sparkline values={[0.1, 0.5, 0.9]} showArea={false} />,
    );
    const paths = container.querySelectorAll("path");
    expect(paths.length).toBe(1); // line only
  });
});
