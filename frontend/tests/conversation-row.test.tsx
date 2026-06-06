import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConversationRow } from "@/components/ui/conversation-row";
import type { ConversationSummary } from "@/lib/api";

const summary: ConversationSummary = {
  kind: "donor",
  donor: {
    id: "d1",
    name: "Priya Sharma",
    blood_group: "B+",
    phone: "+919900000001",
    preferred_language: "en",
    city: "Hyderabad",
  },
  caregiver: null,
  last_message: {
    id: "m1",
    donor_id: "d1",
    bridge_id: null,
    direction: "outbound",
    from_number: "whatsapp:+14155238886",
    to_number: "+919900000001",
    body: "Slot reminder for Aarav this week",
    status: "mocked",
    twilio_sid: "MOCK01",
    template_key: "slot_reminder",
    language: "en",
    created_at: "2026-05-31T12:00:00",
  },
  message_count: 3,
};

const caregiverSummary: ConversationSummary = {
  kind: "caregiver",
  donor: null,
  caregiver: {
    patient_id: "p1",
    patient_name: "Aarav Reddy",
    patient_blood_group: "B+",
    caregiver_name: "Lakshmi Reddy",
    caregiver_relation: "mother",
    caregiver_phone: "+919876500001",
  },
  last_message: {
    id: "m2",
    donor_id: null,
    bridge_id: null,
    direction: "outbound",
    from_number: "whatsapp:+14155238886",
    to_number: "+919876500001",
    body: "Aarav's bridge is fully covered.",
    status: "mocked",
    twilio_sid: "MOCK02",
    template_key: "recruit_success_caregiver",
    language: "en",
    created_at: "2026-05-31T12:30:00",
  },
  message_count: 1,
};

describe("ConversationRow", () => {
  it("renders donor name, blood group, and city", () => {
    render(
      <ConversationRow conversation={summary} selected={false} onSelect={() => {}} />,
    );
    expect(screen.getByText("Priya Sharma")).toBeInTheDocument();
    expect(screen.getByText("B+")).toBeInTheDocument();
    expect(screen.getByText("Hyderabad")).toBeInTheDocument();
  });

  it("renders last message body", () => {
    render(
      <ConversationRow conversation={summary} selected={false} onSelect={() => {}} />,
    );
    expect(screen.getByText(/slot reminder for aarav/i)).toBeInTheDocument();
  });

  it("renders message count with plural", () => {
    render(
      <ConversationRow conversation={summary} selected={false} onSelect={() => {}} />,
    );
    expect(screen.getByText(/3 msgs/i)).toBeInTheDocument();
  });

  it("renders singular 'msg' for count of 1", () => {
    render(
      <ConversationRow
        conversation={{ ...summary, message_count: 1 }}
        selected={false}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText(/1 msg/)).toBeInTheDocument();
    expect(screen.queryByText(/msgs/)).not.toBeInTheDocument();
  });

  it("highlights row when selected", () => {
    render(
      <ConversationRow conversation={summary} selected={true} onSelect={() => {}} />,
    );
    const row = screen.getByTestId("conversation-row");
    expect(row.className).toContain("bg-primary/10");
  });

  it("calls onSelect when clicked", () => {
    const onSelect = vi.fn();
    render(
      <ConversationRow conversation={summary} selected={false} onSelect={onSelect} />,
    );
    screen.getByTestId("conversation-row").click();
    expect(onSelect).toHaveBeenCalledOnce();
  });

  it("includes donor-id data attribute for selection tracking", () => {
    render(
      <ConversationRow conversation={summary} selected={false} onSelect={() => {}} />,
    );
    const row = screen.getByTestId("conversation-row");
    expect(row.dataset.kind).toBe("donor");
    expect(row.dataset.donorId).toBe("d1");
  });

  it("renders a caregiver row with caregiver name + relation + patient", () => {
    render(
      <ConversationRow
        conversation={caregiverSummary}
        selected={false}
        onSelect={() => {}}
      />,
    );
    const row = screen.getByTestId("conversation-row");
    expect(row.dataset.kind).toBe("caregiver");
    expect(row.dataset.patientId).toBe("p1");
    expect(row).toHaveTextContent(/Lakshmi Reddy/);
    expect(row).toHaveTextContent(/caregiver/i);
    expect(row).toHaveTextContent(/mother of Aarav Reddy/i);
    expect(row).toHaveTextContent(/Aarav's bridge is fully covered/);
  });
});
