import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RecruitConfirmModal } from "@/components/ui/recruit-confirm-modal";

describe("RecruitConfirmModal", () => {
  it("does not render when open is false", () => {
    render(
      <RecruitConfirmModal
        open={false}
        candidateName="Aishwarya Murthy"
        candidateLanguage="hi"
        replaceDonorName={null}
        patientName="Aarav Reddy"
        isSubmitting={false}
        onCancel={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(screen.queryByTestId("recruit-confirm-modal")).not.toBeInTheDocument();
  });

  it("shows candidate name, patient name, and language selector", () => {
    render(
      <RecruitConfirmModal
        open={true}
        candidateName="Aishwarya Murthy"
        candidateLanguage="te"
        replaceDonorName={null}
        patientName="Aarav Reddy"
        isSubmitting={false}
        onCancel={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByTestId("recruit-confirm-modal")).toBeInTheDocument();
    expect(screen.getByText(/aishwarya murthy/i)).toBeInTheDocument();
    expect(screen.getByText(/aarav reddy's bridge/i)).toBeInTheDocument();

    const select = screen.getByTestId("recruit-modal-language") as HTMLSelectElement;
    expect(select.value).toBe("te");
  });

  it("mentions the replaced donor when present", () => {
    render(
      <RecruitConfirmModal
        open={true}
        candidateName="Aishwarya"
        candidateLanguage="en"
        replaceDonorName="Priya Sharma"
        patientName="Aarav"
        isSubmitting={false}
        onCancel={() => {}}
        onConfirm={() => {}}
      />,
    );
    // Text is split by an inline span — check both pieces are present in the modal
    const modal = screen.getByTestId("recruit-confirm-modal");
    expect(modal).toHaveTextContent(/replaces/i);
    expect(modal).toHaveTextContent(/priya sharma/i);
  });

  it("calls onConfirm with the selected language", () => {
    const onConfirm = vi.fn();
    render(
      <RecruitConfirmModal
        open={true}
        candidateName="Aishwarya"
        candidateLanguage="en"
        replaceDonorName={null}
        patientName="Aarav"
        isSubmitting={false}
        onCancel={() => {}}
        onConfirm={onConfirm}
      />,
    );
    const select = screen.getByTestId("recruit-modal-language");
    fireEvent.change(select, { target: { value: "hi" } });
    fireEvent.click(screen.getByTestId("recruit-modal-confirm"));
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onConfirm).toHaveBeenCalledWith("hi");
  });

  it("calls onCancel when the X button is clicked", () => {
    const onCancel = vi.fn();
    render(
      <RecruitConfirmModal
        open={true}
        candidateName="Aishwarya"
        candidateLanguage="en"
        replaceDonorName={null}
        patientName="Aarav"
        isSubmitting={false}
        onCancel={onCancel}
        onConfirm={() => {}}
      />,
    );
    fireEvent.click(screen.getByLabelText(/close/i));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("disables buttons + selector while isSubmitting", () => {
    render(
      <RecruitConfirmModal
        open={true}
        candidateName="Aishwarya"
        candidateLanguage="en"
        replaceDonorName={null}
        patientName="Aarav"
        isSubmitting={true}
        onCancel={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByTestId("recruit-modal-confirm")).toBeDisabled();
    expect(screen.getByTestId("recruit-modal-cancel")).toBeDisabled();
    expect(screen.getByTestId("recruit-modal-language")).toBeDisabled();
  });

  it("warns when the chosen language differs from the donor's preference", () => {
    render(
      <RecruitConfirmModal
        open={true}
        candidateName="Aishwarya"
        candidateLanguage="hi"
        replaceDonorName={null}
        patientName="Aarav"
        isSubmitting={false}
        onCancel={() => {}}
        onConfirm={() => {}}
      />,
    );
    // Default = "hi", no warning yet
    expect(screen.queryByText(/overriding/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByTestId("recruit-modal-language"), {
      target: { value: "en" },
    });
    expect(screen.getByText(/overriding/i)).toBeInTheDocument();
  });
});
