import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ToastProvider, useToast } from "@/components/ui/toast";

function Pusher({ kind }: { kind: "success" | "error" | "info" }) {
  const { show } = useToast();
  return (
    <button
      onClick={() =>
        show({
          title: `${kind} title`,
          description: `${kind} description text`,
          variant: kind,
        })
      }
      data-testid={`push-${kind}`}
    >
      push
    </button>
  );
}

describe("ToastProvider + useToast", () => {
  it("renders a toast region by default", () => {
    render(
      <ToastProvider>
        <div />
      </ToastProvider>,
    );
    expect(screen.getByTestId("toast-region")).toBeInTheDocument();
  });

  it("pushes a success toast with title + description", async () => {
    render(
      <ToastProvider>
        <Pusher kind="success" />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByTestId("push-success"));
    const toast = await screen.findByTestId("toast");
    expect(toast.dataset.variant).toBe("success");
    expect(toast).toHaveTextContent(/success title/i);
    expect(toast).toHaveTextContent(/success description/i);
  });

  it("pushes an error toast", async () => {
    render(
      <ToastProvider>
        <Pusher kind="error" />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByTestId("push-error"));
    const toast = await screen.findByTestId("toast");
    expect(toast.dataset.variant).toBe("error");
  });

  it("dismisses when the X button is clicked", async () => {
    render(
      <ToastProvider>
        <Pusher kind="info" />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByTestId("push-info"));
    const toast = await screen.findByTestId("toast");
    expect(toast).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/dismiss/i));
    await waitFor(() => {
      expect(screen.queryByTestId("toast")).not.toBeInTheDocument();
    });
  });

  it("throws if useToast is called outside the provider", () => {
    function Bad() {
      useToast();
      return null;
    }
    // Suppress React's error noise during the assertion
    const consoleError = console.error;
    console.error = () => {};
    expect(() => render(<Bad />)).toThrow(/inside a <ToastProvider/);
    console.error = consoleError;
  });
});
