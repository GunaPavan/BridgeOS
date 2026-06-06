import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BedrockModelTag } from "@/components/ui/bedrock-model-tag";

describe("BedrockModelTag", () => {
  it("renders Sonnet label for Claude Sonnet model id", () => {
    render(
      <BedrockModelTag modelId="anthropic.claude-3-5-sonnet-20241022-v2:0" />,
    );
    const tag = screen.getByTestId("bedrock-model-tag");
    expect(tag).toHaveTextContent(/Sonnet/i);
    expect(tag.dataset.family).toBe("sonnet");
  });

  it("renders Haiku label for Claude Haiku model id", () => {
    render(<BedrockModelTag modelId="anthropic.claude-3-haiku-20240307-v1:0" />);
    const tag = screen.getByTestId("bedrock-model-tag");
    expect(tag).toHaveTextContent(/Haiku/i);
    expect(tag.dataset.family).toBe("haiku");
  });

  it("renders Titan label for Titan embeddings model id", () => {
    render(<BedrockModelTag modelId="amazon.titan-embed-text-v2:0" />);
    const tag = screen.getByTestId("bedrock-model-tag");
    expect(tag).toHaveTextContent(/Titan/i);
    expect(tag.dataset.family).toBe("titan");
  });

  it("surfaces task + tokens via the native title tooltip", () => {
    render(
      <BedrockModelTag
        modelId="anthropic.claude-3-5-sonnet-20241022-v2:0"
        task="chat"
        tokens={128}
      />,
    );
    const tag = screen.getByTestId("bedrock-model-tag");
    const title = tag.getAttribute("title") ?? "";
    expect(title).toMatch(/Bedrock model: anthropic\.claude-3-5-sonnet/);
    expect(title).toMatch(/Task: chat/);
    expect(title).toMatch(/128 output tokens/);
    expect(tag.dataset.task).toBe("chat");
  });

  it("falls back to a generic 'Bedrock' label for unknown model families", () => {
    render(<BedrockModelTag modelId="some.unknown-model-id" />);
    expect(screen.getByTestId("bedrock-model-tag")).toHaveTextContent(/Bedrock/i);
  });
});
