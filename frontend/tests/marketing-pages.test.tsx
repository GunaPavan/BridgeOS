import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AboutPage from "@/app/about/page";
import HowItWorksPage from "@/app/how-it-works/page";

describe("HowItWorksPage", () => {
  it("renders the architecture diagram", () => {
    render(<HowItWorksPage />);
    const diagram = screen.getByTestId("architecture-diagram");
    expect(diagram).toBeInTheDocument();
    expect(diagram).toHaveTextContent(/FRONTEND/);
    expect(diagram).toHaveTextContent(/BACKEND/);
    expect(diagram).toHaveTextContent(/DATA/);
  });

  it("renders all four differentiator deep-dive cards", () => {
    render(<HowItWorksPage />);
    expect(screen.getAllByTestId("differentiator-deepdive")).toHaveLength(4);
  });

  it("mentions the four differentiators by name", () => {
    render(<HowItWorksPage />);
    // Differentiator 1: real-data ML stack (churn classifier + survival model)
    expect(screen.getByText(/Multi-class Churn Classifier/i)).toBeInTheDocument();
    expect(screen.getByText(/Rotation Scheduler/i)).toBeInTheDocument();
    expect(screen.getByText(/Live Cohort Simulator/i)).toBeInTheDocument();
    expect(screen.getByText(/Multilingual LLM Care Agent/i)).toBeInTheDocument();
  });

  it("includes both nav and footer", () => {
    render(<HowItWorksPage />);
    expect(screen.getByTestId("marketing-nav")).toBeInTheDocument();
    expect(screen.getByTestId("marketing-footer")).toBeInTheDocument();
  });
});

describe("AboutPage", () => {
  it("credits Gunaputra Nagendra Pavan Yedida and Aakash Jangeeti", () => {
    render(<AboutPage />);
    // Both names appear in team cards
    expect(
      screen.getAllByText(/Gunaputra Nagendra Pavan Yedida/i).length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText(/Aakash Jangeeti/i).length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("renders both team cards", () => {
    render(<AboutPage />);
    expect(screen.getAllByTestId("team-card")).toHaveLength(2);
  });

  it("links to the Blood Warriors Foundation", () => {
    render(<AboutPage />);
    const link = screen.getByTestId("blood-warriors-link");
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "https://bloodwarriors.in");
  });

  it("credits Blend360 + Blood Warriors + HackCulture as impact partners", () => {
    render(<AboutPage />);
    // Blend360 = organising sponsor; Blood Warriors + HackCulture = impact partners.
    expect(screen.getAllByText(/Blend360/i).length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText(/Blood Warriors/i).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/HackCulture/i).length).toBeGreaterThanOrEqual(1);
    // Removed sponsors should be gone everywhere on the about page.
    expect(screen.queryByText(/Microsoft/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/SVP India/i)).not.toBeInTheDocument();
  });
});
