import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Skeleton, SkeletonRow } from "@/components/ui/skeleton";

describe("Skeleton", () => {
  it("renders with shimmer pseudo via animate class", () => {
    render(<Skeleton className="h-4 w-20" />);
    const el = screen.getByTestId("skeleton");
    expect(el).toBeInTheDocument();
    expect(el.className).toContain("h-4");
    expect(el.className).toContain("w-20");
    expect(el.className).toContain("animate-[shimmer");
  });

  it("merges custom classes with the base shimmer styles", () => {
    render(<Skeleton className="rounded-full" />);
    const el = screen.getByTestId("skeleton");
    expect(el.className).toContain("rounded-full");
    expect(el.className).toContain("bg-white/5");
  });
});

describe("SkeletonRow", () => {
  it("renders three stacked skeleton bars", () => {
    render(<SkeletonRow />);
    const row = screen.getByTestId("skeleton-row");
    const bars = row.querySelectorAll("[data-testid='skeleton']");
    expect(bars.length).toBe(3);
  });
});
