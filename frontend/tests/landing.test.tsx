import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "@/app/page";

describe("HomePage (landing)", () => {
  it("renders the Bridge OS wordmark in the hero", () => {
    render(<HomePage />);
    // Wordmark appears in nav + hero — both should have the heading element
    const headings = screen.getAllByRole("heading", { name: /bridge os/i });
    expect(headings.length).toBeGreaterThanOrEqual(1);
  });

  it("shows the tagline", () => {
    render(<HomePage />);
    // Tagline appears in hero + footer
    expect(
      screen.getAllByText(/the operating system for blood bridges/i).length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("credits AlgoWarriors and the AI for Good Hackathon 2026", () => {
    render(<HomePage />);
    // Hackathon mention appears in hero pill and the footer
    expect(
      screen.getAllByText(/algowarriors/i).length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText(/ai for good hackathon 2026/i).length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("renders all four differentiator cards", () => {
    render(<HomePage />);
    const cards = screen.getAllByTestId("differentiator-card");
    expect(cards).toHaveLength(4);
  });

  it("shows the impact stats strip", () => {
    render(<HomePage />);
    // 4 stats render; some use AnimatedCounter which starts at 0 in jsdom (no IntersectionObserver fire)
    expect(screen.getAllByTestId("impact-stat")).toHaveLength(4);
    // Two static stats render their labels verbatim
    // "8–10" appears in impact stats and again in the description prose
    expect(screen.getAllByText(/8–10/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/one bridge — for years/i)).toBeInTheDocument();
    // The two animated stats render their AnimatedCounter wrappers
    expect(screen.getAllByTestId("animated-counter").length).toBe(2);
  });

  it("has primary + secondary hero CTAs", () => {
    render(<HomePage />);
    expect(screen.getByTestId("hero-cta-primary")).toBeInTheDocument();
    expect(screen.getByTestId("hero-cta-secondary")).toBeInTheDocument();
  });

  it("includes the marketing nav and footer", () => {
    render(<HomePage />);
    expect(screen.getByTestId("marketing-nav")).toBeInTheDocument();
    expect(screen.getByTestId("marketing-footer")).toBeInTheDocument();
  });

  it("renders the aurora backdrop in the hero", () => {
    render(<HomePage />);
    const backdrop = screen.getByTestId("aurora-backdrop");
    // Two orbs: aurora-orb-a + aurora-orb-b
    expect(backdrop.querySelectorAll(".aurora-orb").length).toBe(2);
  });
});
