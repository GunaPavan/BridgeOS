import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CaregiverPanel } from "@/components/ui/caregiver-panel";
import { ToastProvider } from "@/components/ui/toast";
import type { CaregiverConversationThread } from "@/lib/api";

const thread: CaregiverConversationThread = {
  caregiver: {
    patient_id: "p1",
    patient_name: "Aarav Reddy",
    patient_blood_group: "B+",
    caregiver_name: "Lakshmi Reddy",
    caregiver_relation: "mother",
    caregiver_phone: "+919876500001",
  },
  messages: [
    {
      id: "m1",
      donor_id: null,
      bridge_id: null,
      direction: "outbound",
      from_number: "whatsapp:+14155238886",
      to_number: "+919876500001",
      body: "Aarav's bridge is fully covered.",
      status: "mocked",
      twilio_sid: "MOCK1",
      template_key: "recruit_success_caregiver",
      language: "en",
      created_at: "2026-05-31T12:00:00",
    },
  ],
};

function renderWith(ui: React.ReactNode, payload: CaregiverConversationThread | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    })),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  );
}

describe("CaregiverPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders empty state when no caregiver is configured", () => {
    renderWith(
      <CaregiverPanel
        patientId="p1"
        caregiverName={null}
        caregiverPhone={null}
        caregiverRelation={null}
      />,
      null,
    );
    expect(screen.getByTestId("caregiver-panel-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("caregiver-panel")).not.toBeInTheDocument();
  });

  it("renders caregiver name, relation pill, and phone", async () => {
    renderWith(
      <CaregiverPanel
        patientId="p1"
        caregiverName="Lakshmi Reddy"
        caregiverPhone="+919876500001"
        caregiverRelation="mother"
      />,
      thread,
    );
    const panel = await screen.findByTestId("caregiver-panel");
    expect(panel).toHaveTextContent(/Lakshmi Reddy/);
    expect(panel).toHaveTextContent(/mother/i);
    expect(panel).toHaveTextContent(/\+919876500001/);
  });

  it("renders the template dropdown with the 3 caregiver templates", async () => {
    renderWith(
      <CaregiverPanel
        patientId="p1"
        caregiverName="Lakshmi Reddy"
        caregiverPhone="+919876500001"
        caregiverRelation="mother"
      />,
      thread,
    );
    const select = await screen.findByTestId("caregiver-template-select");
    const options = (select as HTMLSelectElement).querySelectorAll("option");
    expect(options).toHaveLength(3);
    const values = Array.from(options).map((o) => o.value);
    expect(values).toEqual([
      "bridge_covered_caregiver",
      "recruit_success_caregiver",
      "transfusion_confirmed_caregiver",
    ]);
  });

  it("renders message bubbles for thread messages", async () => {
    renderWith(
      <CaregiverPanel
        patientId="p1"
        caregiverName="Lakshmi Reddy"
        caregiverPhone="+919876500001"
        caregiverRelation="mother"
      />,
      thread,
    );
    await waitFor(() =>
      expect(screen.getByTestId("caregiver-thread")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Aarav's bridge is fully covered/)).toBeInTheDocument();
  });
});
