import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BridgeCard } from "@/components/ui/bridge-card";
import type { BridgeListItem } from "@/lib/api";

const sample: BridgeListItem = {
  id: "11111111-1111-1111-1111-111111111111",
  patient_id: "22222222-2222-2222-2222-222222222222",
  patient_name: "Aarav Reddy",
  patient_age: 8,
  blood_group: "B+",
  city: "Hyderabad",
  state: "Telangana",
  hospital: "Apollo Hospitals",
  status: "active",
  active_donor_count: 8,
  total_donor_count: 10,
  health: "at_risk",
  last_transfusion_date: "2026-05-19",
  next_transfusion_date: "2026-06-06",
  days_until_transfusion: 6,
  created_at: "2026-01-01T00:00:00Z",
};

describe("BridgeCard", () => {
  it("renders patient name, age, and blood group", () => {
    render(<BridgeCard bridge={sample} />);
    expect(screen.getByRole("heading", { name: /aarav reddy/i })).toBeInTheDocument();
    expect(screen.getByText(/8 years old/i)).toBeInTheDocument();
    expect(screen.getByText("B+")).toBeInTheDocument();
  });

  it("shows active donor count", () => {
    render(<BridgeCard bridge={sample} />);
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText(/donors/i)).toBeInTheDocument();
  });

  it("shows days until next transfusion", () => {
    render(<BridgeCard bridge={sample} />);
    expect(screen.getByText(/in 6 days/i)).toBeInTheDocument();
  });

  it("shows hospital and city", () => {
    render(<BridgeCard bridge={sample} />);
    expect(
      screen.getByText(/apollo hospitals.*hyderabad/i),
    ).toBeInTheDocument();
  });

  it("renders the health badge", () => {
    render(<BridgeCard bridge={sample} />);
    expect(screen.getByTestId("health-badge")).toHaveAttribute(
      "data-health",
      "at_risk",
    );
  });

  it("wraps the card in a link to the bridge detail page", () => {
    render(<BridgeCard bridge={sample} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", `/bridges/${sample.id}`);
  });
});
