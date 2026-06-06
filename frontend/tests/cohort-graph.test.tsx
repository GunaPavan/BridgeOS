import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CohortGraph } from "@/components/ui/cohort-graph";
import type { CohortMemberState } from "@/lib/api";

const cohort: CohortMemberState[] = [
  {
    donor_id: "d1",
    donor_name: "Priya Sharma",
    blood_group: "B+",
    churn_30d: 0.32,
    churn_60d: 0.55,
    churn_90d: 0.78,
  },
  {
    donor_id: "d2",
    donor_name: "Karan Trivedi",
    blood_group: "B+",
    churn_30d: 0.05,
    churn_60d: 0.10,
    churn_90d: 0.15,
  },
  {
    donor_id: "d3",
    donor_name: "Sneha Iyer",
    blood_group: "B+",
    churn_30d: 0.12,
    churn_60d: 0.22,
    churn_90d: 0.30,
  },
];

describe("CohortGraph", () => {
  it("renders one donor-tile per cohort member with the right name", () => {
    render(
      <CohortGraph
        patientName="Aarav Reddy"
        patientBloodGroup="B+"
        cohort={cohort}
        ejectedSet={new Set()}
        onToggle={() => {}}
      />,
    );
    const tiles = screen.getAllByTestId("donor-tile");
    expect(tiles).toHaveLength(3);
    expect(screen.getByText(/priya sharma/i)).toBeInTheDocument();
    expect(screen.getByText(/karan trivedi/i)).toBeInTheDocument();
  });

  it("marks ejected donors with data-ejected attribute", () => {
    render(
      <CohortGraph
        patientName="Aarav Reddy"
        patientBloodGroup="B+"
        cohort={cohort}
        ejectedSet={new Set(["d1"])}
        onToggle={() => {}}
      />,
    );
    const tiles = screen.getAllByTestId("donor-tile");
    const priya = tiles.find((t) => t.dataset.donorId === "d1");
    expect(priya?.dataset.ejected).toBe("true");
    const karan = tiles.find((t) => t.dataset.donorId === "d2");
    expect(karan?.dataset.ejected).toBe("false");
  });

  it("renders the patient node at the centre with name and blood group", () => {
    render(
      <CohortGraph
        patientName="Aarav Reddy"
        patientBloodGroup="B+"
        cohort={cohort}
        ejectedSet={new Set()}
        onToggle={() => {}}
      />,
    );
    const patient = screen.getByTestId("graph-patient-node");
    expect(patient).toHaveTextContent(/aarav reddy/i);
    expect(patient).toHaveTextContent(/B\+/);
  });

  it("mounts inside a cohort-graph container", () => {
    render(
      <CohortGraph
        patientName="Aarav Reddy"
        patientBloodGroup="B+"
        cohort={cohort}
        ejectedSet={new Set()}
        onToggle={() => {}}
      />,
    );
    expect(screen.getByTestId("cohort-graph")).toBeInTheDocument();
  });
});
