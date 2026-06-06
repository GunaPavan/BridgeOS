import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PatientCard } from "@/components/ui/patient-card";
import type { PatientListItem } from "@/lib/api";

const baseAarav: PatientListItem = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Aarav Reddy",
  age: 8,
  blood_group: "B+",
  rh_negative: false,
  kell_negative: true,
  city: "Hyderabad",
  state: "Telangana",
  hospital: "Apollo Hospitals",
  preferred_language: "te",
  transfusion_cadence_days: 18,
  last_transfusion_date: "2026-05-19",
  next_transfusion_date: "2026-06-06",
  days_until_transfusion: 6,
  active: true,
  has_bridge: true,
  bridge_health: "stable",
  active_donor_count: 8,
};

describe("PatientCard", () => {
  it("renders name, age, and blood group", () => {
    render(<PatientCard patient={baseAarav} />);
    expect(screen.getByRole("heading", { name: /aarav reddy/i })).toBeInTheDocument();
    expect(screen.getByText(/8 years old/i)).toBeInTheDocument();
    expect(screen.getByText("B+")).toBeInTheDocument();
  });

  it("shows hospital and city", () => {
    render(<PatientCard patient={baseAarav} />);
    expect(screen.getByText("Apollo Hospitals")).toBeInTheDocument();
    expect(screen.getByText("Hyderabad")).toBeInTheDocument();
  });

  it("shows days until next transfusion", () => {
    render(<PatientCard patient={baseAarav} />);
    expect(screen.getByText(/in 6 days/i)).toBeInTheDocument();
  });

  it("shows active donor count", () => {
    render(<PatientCard patient={baseAarav} />);
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText(/donors/i)).toBeInTheDocument();
  });

  it("renders the Kell-negative shield when kell_negative is true", () => {
    render(<PatientCard patient={baseAarav} />);
    expect(screen.getByLabelText(/kell-negative/i)).toBeInTheDocument();
  });

  it("renders the bridge health badge", () => {
    render(<PatientCard patient={baseAarav} />);
    expect(screen.getByTestId("health-badge")).toHaveAttribute(
      "data-health",
      "stable",
    );
  });

  it("warns about missing bridge when has_bridge is false", () => {
    render(
      <PatientCard
        patient={{
          ...baseAarav,
          has_bridge: false,
          bridge_health: null,
          active_donor_count: 0,
        }}
      />,
    );
    expect(screen.getByText(/no bridge/i)).toBeInTheDocument();
    expect(screen.getByText(/needs a bridge/i)).toBeInTheDocument();
    expect(screen.queryByTestId("health-badge")).not.toBeInTheDocument();
  });

  it("links to the patient profile page", () => {
    render(<PatientCard patient={baseAarav} />);
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      `/patients/${baseAarav.id}`,
    );
  });
});
