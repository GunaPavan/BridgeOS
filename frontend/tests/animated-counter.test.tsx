import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnimatedCounter } from "@/components/ui/animated-counter";

describe("AnimatedCounter", () => {
  it("renders an initial 0 value before scroll-in", () => {
    render(<AnimatedCounter value={500} />);
    const span = screen.getByTestId("animated-counter");
    // SSR-safe: starts at the formatted zero
    expect(span.textContent).toBe("0");
    // target attribute carries the value for assertions
    expect(span.dataset.target).toBe("500");
  });

  it("respects a custom format function", () => {
    render(<AnimatedCounter value={1234} format={(n) => `${Math.round(n)} units`} />);
    expect(screen.getByTestId("animated-counter").textContent).toBe("0 units");
  });

  it("threads a custom className onto the rendered span", () => {
    render(<AnimatedCounter value={10} className="font-mono" />);
    const span = screen.getByTestId("animated-counter");
    expect(span.className).toContain("font-mono");
  });
});
