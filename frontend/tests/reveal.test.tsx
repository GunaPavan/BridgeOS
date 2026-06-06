import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Reveal } from "@/components/ui/reveal";

describe("Reveal", () => {
  it("renders its children inside a motion wrapper", () => {
    render(
      <Reveal>
        <p>Inside the reveal</p>
      </Reveal>,
    );
    expect(screen.getByText(/inside the reveal/i)).toBeInTheDocument();
  });

  it("forwards a className to the wrapper element", () => {
    render(
      <Reveal className="custom-class">
        <span data-testid="child">x</span>
      </Reveal>,
    );
    const child = screen.getByTestId("child");
    expect(child.parentElement?.className).toContain("custom-class");
  });
});
