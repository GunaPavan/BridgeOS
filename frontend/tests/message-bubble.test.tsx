import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageBubble } from "@/components/ui/message-bubble";
import type { WhatsAppMessage } from "@/lib/api";

const base: WhatsAppMessage = {
  id: "m1",
  donor_id: "d1",
  bridge_id: null,
  direction: "outbound",
  from_number: "whatsapp:+14155238886",
  to_number: "+919900000001",
  body: "Hello Priya — please confirm next slot.",
  status: "mocked",
  twilio_sid: "MOCK01",
  template_key: null,
  language: null,
  created_at: "2026-05-31T12:00:00",
};

describe("MessageBubble", () => {
  it("renders message body", () => {
    render(<MessageBubble message={base} />);
    expect(screen.getByText(/please confirm next slot/i)).toBeInTheDocument();
  });

  it("right-aligns outbound messages", () => {
    render(<MessageBubble message={base} />);
    const bubble = screen.getByTestId("message-bubble");
    expect(bubble.className).toContain("ml-auto");
    expect(bubble.dataset.direction).toBe("outbound");
  });

  it("left-aligns inbound messages", () => {
    render(<MessageBubble message={{ ...base, direction: "inbound" }} />);
    const bubble = screen.getByTestId("message-bubble");
    expect(bubble.className).toContain("mr-auto");
    expect(bubble.dataset.direction).toBe("inbound");
  });

  it("shows status text for outbound messages", () => {
    render(<MessageBubble message={base} />);
    expect(screen.getByText("mocked")).toBeInTheDocument();
  });

  it("hides status for inbound messages", () => {
    render(<MessageBubble message={{ ...base, direction: "inbound" }} />);
    expect(screen.queryByText("mocked")).not.toBeInTheDocument();
  });

  it("shows template tag when template_key is present", () => {
    render(
      <MessageBubble
        message={{ ...base, template_key: "slot_reminder" }}
      />,
    );
    expect(screen.getByText("slot_reminder")).toBeInTheDocument();
  });

  it("does not show template tag when template_key is null", () => {
    render(<MessageBubble message={base} />);
    expect(screen.queryByText("slot_reminder")).not.toBeInTheDocument();
  });

  it("shows the G4 language chip when language is set on an outbound message", () => {
    render(
      <MessageBubble
        message={{ ...base, template_key: "slot_reminder", language: "hi" }}
      />,
    );
    const chip = screen.getByTestId("message-language-chip");
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveTextContent(/hi/);
  });

  it("does not show language chip on inbound messages", () => {
    render(
      <MessageBubble
        message={{ ...base, direction: "inbound", language: "hi" }}
      />,
    );
    expect(screen.queryByTestId("message-language-chip")).not.toBeInTheDocument();
  });
});
