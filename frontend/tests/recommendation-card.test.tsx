import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecommendationCard } from "@/components/ui/recommendation-card";
import { ToastProvider } from "@/components/ui/toast";
import type { BridgeRecommendation } from "@/lib/api";

const sample: BridgeRecommendation = {
  bridge_id: "bridge-aarav",
  bridge_name: "Bridge for Aarav",
  patient_id: "patient-aarav",
  patient_name: "Aarav Reddy",
  patient_age: 8,
  patient_blood_group: "B+",
  patient_hospital: "Apollo Hospitals",
  patient_city: "Hyderabad",
  bridge_health_stub: "stable",
  active_donor_count: 8,
  urgency: "critical",
  weak_donors: [
    {
      membership_id: "m1",
      donor_id: "priya",
      donor_name: "Priya Sharma",
      role: "primary",
      churn_90d: 0.78,
      top_factors: [
        {
          feature: "response_rate",
          label: "Low response rate (32%)",
          direction: "increases_churn",
          impact: 1.4,
        },
      ],
    },
  ],
  candidates: [
    {
      donor: {
        id: "cand-1",
        name: "Aakash Nair",
        age: 28,
        blood_group: "O+",
        rh_negative: false,
        kell_negative: true,
        city: "Hyderabad",
        state: "Telangana",
        last_donation_date: null,
        total_donations: 14,
        response_rate: 0.95,
        is_active: true,
      },
      composite_score: 0.88,
      distance_km: 2.3,
      predicted_churn_90d: 0.12,
      days_until_eligible: 0,
      rationale: [
        { factor: "distance_km", value: 2.3, description: "2.3 km from Apollo Hospitals" },
        { factor: "response_rate", value: 0.95, description: "95% historical response rate" },
        {
          factor: "predicted_churn_90d",
          value: 0.12,
          description: "12% predicted 90-day churn",
        },
        {
          factor: "kell_match",
          value: 1.0,
          description: "Kell-negative match — preferred for repeat-transfused patient",
        },
      ],
    },
  ],
};

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  );
}

describe("RecommendationCard", () => {
  it("renders the patient header with hospital and city", () => {
    renderWithClient(<RecommendationCard rec={sample} />);
    expect(screen.getByRole("heading", { name: /aarav reddy/i })).toBeInTheDocument();
    // "Apollo Hospitals" and "Hyderabad" both appear in the candidate rationale too,
    // so use getAllByText and assert presence rather than uniqueness.
    expect(screen.getAllByText(/apollo hospitals/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/hyderabad/i).length).toBeGreaterThanOrEqual(1);
  });

  it("renders the urgency pill with correct label", () => {
    renderWithClient(<RecommendationCard rec={sample} />);
    expect(screen.getByTestId("urgency-pill")).toHaveTextContent(/critical/i);
  });

  it("renders weak donors with churn percentage", () => {
    renderWithClient(<RecommendationCard rec={sample} />);
    // Priya appears in both the weak-donors list and the "Replaces" hint
    expect(screen.getAllByText(/priya sharma/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/78% churn/i)).toBeInTheDocument();
  });

  it("renders each candidate with a recruit button and match score", () => {
    renderWithClient(<RecommendationCard rec={sample} />);
    const rows = screen.getAllByTestId("candidate-row");
    expect(rows).toHaveLength(1);
    expect(within(rows[0]).getByText(/aakash nair/i)).toBeInTheDocument();
    expect(within(rows[0]).getByText("88")).toBeInTheDocument(); // match score
    expect(within(rows[0]).getByTestId("recruit-button")).toBeInTheDocument();
  });

  it("shows candidate rationale lines", () => {
    renderWithClient(<RecommendationCard rec={sample} />);
    expect(
      screen.getByText(/2\.3 km from apollo hospitals/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/95% historical response rate/i)).toBeInTheDocument();
    expect(
      screen.getByText(/kell-negative match/i),
    ).toBeInTheDocument();
  });

  it("shows 'replaces Priya' hint when there's a weak donor", () => {
    renderWithClient(<RecommendationCard rec={sample} />);
    expect(screen.getByText(/replaces/i)).toBeInTheDocument();
    expect(screen.getAllByText(/priya sharma/i).length).toBeGreaterThan(0);
  });
});
