import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentMessageBubble } from "@/components/ui/agent-message";
import type { AgentMessage } from "@/lib/api";

const userMsg: AgentMessage = {
  id: "u1",
  session_id: "s1",
  role: "user",
  content: "Why is Priya at risk?",
  donor_id: "d1",
  bridge_id: null,
  patient_id: null,
  language: "en",
  provider: null,
  model: null,
  tokens_in: null,
  tokens_out: null,
  task: null,
  created_at: "2026-05-31T12:00:00",
};

const assistantMsg: AgentMessage = {
  id: "a1",
  session_id: "s1",
  role: "assistant",
  content: "Priya's response rate of 32% is the main churn signal.",
  donor_id: "d1",
  bridge_id: null,
  patient_id: null,
  language: "en",
  provider: "mock",
  model: "bridge-os-mock-v1",
  tokens_in: 120,
  tokens_out: 45,
  task: null,
  created_at: "2026-05-31T12:00:01",
};

const bedrockMsg: AgentMessage = {
  ...assistantMsg,
  id: "a2",
  provider: "bedrock",
  model: "anthropic.claude-3-5-sonnet-20241022-v2:0",
  task: "chat",
};

describe("AgentMessageBubble", () => {
  it("renders user message right-aligned", () => {
    render(<AgentMessageBubble message={userMsg} />);
    const bubble = screen.getByTestId("agent-message");
    expect(bubble.dataset.role).toBe("user");
    expect(bubble.className).toContain("justify-end");
    expect(screen.getByText(/why is priya at risk/i)).toBeInTheDocument();
  });

  it("renders assistant message left-aligned with sparkles avatar", () => {
    render(<AgentMessageBubble message={assistantMsg} />);
    const bubble = screen.getByTestId("agent-message");
    expect(bubble.dataset.role).toBe("assistant");
    expect(bubble.className).toContain("justify-start");
    expect(screen.getByText(/response rate of 32%/i)).toBeInTheDocument();
  });

  it("shows provider + model badges on assistant messages", () => {
    render(<AgentMessageBubble message={assistantMsg} />);
    expect(screen.getByText("mock")).toBeInTheDocument();
    expect(screen.getByText(/bridge-os-mock-v1/)).toBeInTheDocument();
    expect(screen.getByText(/45 tok/)).toBeInTheDocument();
  });

  it("does not show provider badges on user messages", () => {
    render(<AgentMessageBubble message={userMsg} />);
    expect(screen.queryByText("mock")).not.toBeInTheDocument();
  });

  it("omits token count when tokens_out is null", () => {
    const msgWithoutTokens = { ...assistantMsg, tokens_out: null };
    render(<AgentMessageBubble message={msgWithoutTokens} />);
    expect(screen.queryByText(/tok/)).not.toBeInTheDocument();
  });

  it("preserves whitespace in multi-line responses", () => {
    const multi = {
      ...assistantMsg,
      content: "First line.\nSecond line.\n\nThird paragraph.",
    };
    render(<AgentMessageBubble message={multi} />);
    const p = screen.getByText(/first line/i);
    expect(p.className).toContain("whitespace-pre-wrap");
  });

  it("renders BedrockModelTag instead of inline pill when provider is bedrock", () => {
    render(<AgentMessageBubble message={bedrockMsg} />);
    const tag = screen.getByTestId("bedrock-model-tag");
    expect(tag).toBeInTheDocument();
    expect(tag.dataset.family).toBe("sonnet");
    expect(tag.dataset.task).toBe("chat");
    // The raw "bedrock" string should NOT appear as the inline label
    expect(screen.queryByText("bedrock")).not.toBeInTheDocument();
  });

  it("does not render BedrockModelTag for non-bedrock providers", () => {
    render(<AgentMessageBubble message={assistantMsg} />);
    expect(screen.queryByTestId("bedrock-model-tag")).not.toBeInTheDocument();
    // Existing inline pill still renders
    expect(screen.getByText("mock")).toBeInTheDocument();
  });
});
