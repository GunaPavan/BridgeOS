import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DonorCard } from "@/components/ui/donor-card";
import type { DonorListItem } from "@/lib/api";

const baseDonor: DonorListItem = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Priya Sharma",
  age: 28,
  blood_group: "B+",
  rh_negative: false,
  kell_negative: true,
  city: "Hyderabad",
  state: "Telangana",
  preferred_language: "te",
  last_donation_date: "2026-05-17",
  days_since_donation: 14,
  total_donations: 12,
  response_rate: 0.42,
  avg_response_hours: 38,
  is_active: true,
  is_eligible_to_donate: false,
  bridge_count: 1,
};

describe("DonorCard", () => {
  it("renders name, age, and blood group", () => {
    render(<DonorCard donor={baseDonor} />);
    expect(screen.getByRole("heading", { name: /priya sharma/i })).toBeInTheDocument();
    expect(screen.getByText(/28 years old/i)).toBeInTheDocument();
    expect(screen.getByText("B+")).toBeInTheDocument();
  });

  it("shows total donations, response rate, and bridge count", () => {
    render(<DonorCard donor={baseDonor} />);
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("shows city and state", () => {
    render(<DonorCard donor={baseDonor} />);
    expect(screen.getByText(/hyderabad, telangana/i)).toBeInTheDocument();
  });

  it("renders the Kell-negative shield when kell_negative is true", () => {
    render(<DonorCard donor={baseDonor} />);
    expect(screen.getByLabelText(/kell-negative/i)).toBeInTheDocument();
  });

  it("hides the Kell shield when kell_negative is false", () => {
    render(<DonorCard donor={{ ...baseDonor, kell_negative: false }} />);
    expect(screen.queryByLabelText(/kell-negative/i)).not.toBeInTheDocument();
  });

  it("shows 'Cooldown' pill when ineligible", () => {
    render(<DonorCard donor={baseDonor} />);
    expect(screen.getByText(/cooldown/i)).toBeInTheDocument();
  });

  it("shows 'Eligible' pill when eligible to donate", () => {
    render(<DonorCard donor={{ ...baseDonor, is_eligible_to_donate: true }} />);
    expect(screen.getByText(/^eligible$/i)).toBeInTheDocument();
  });

  it("links to the donor detail page", () => {
    render(<DonorCard donor={baseDonor} />);
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      `/donors/${baseDonor.id}`,
    );
  });
});
