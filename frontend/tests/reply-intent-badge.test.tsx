import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ReplyIntentBadge } from "@/components/ui/reply-intent-badge";

describe("ReplyIntentBadge", () => {
  it("renders the label for each intent", () => {
    const cases = [
      { intent: "accept", label: "Accept" },
      { intent: "decline", label: "Decline" },
      { intent: "reschedule_request", label: "Reschedule" },
      { intent: "out_of_town", label: "Out of town" },
      { intent: "medical_defer", label: "Medical defer" },
      { intent: "unrelated_question", label: "Question" },
      { intent: "stop", label: "Opt-out" },
      { intent: "unknown", label: "Unknown" },
    ] as const;

    for (const c of cases) {
      const { unmount } = render(<ReplyIntentBadge intent={c.intent} />);
      const badge = screen.getByTestId("reply-intent-badge");
      expect(badge).toHaveAttribute("data-intent", c.intent);
      expect(badge).toHaveTextContent(c.label);
      unmount();
    }
  });

  it("uses different colour classes per intent", () => {
    const a = render(<ReplyIntentBadge intent="accept" />);
    const aBadge = a.container.querySelector("[data-testid='reply-intent-badge']");
    a.unmount();

    const d = render(<ReplyIntentBadge intent="decline" />);
    const dBadge = d.container.querySelector("[data-testid='reply-intent-badge']");
    expect(aBadge?.className).not.toBe(dBadge?.className);
    d.unmount();
  });

  it("falls back to Unknown style for an unmapped value", () => {
    // @ts-expect-error — intentionally bogus
    render(<ReplyIntentBadge intent="garbage" />);
    expect(screen.getByTestId("reply-intent-badge")).toHaveTextContent("Unknown");
  });
});
