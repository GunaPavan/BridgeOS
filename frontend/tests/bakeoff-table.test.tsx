import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BakeoffTable } from "@/components/ui/bakeoff-table";
import type { MlBakeoffReport } from "@/lib/api";

function churnPayload(): MlBakeoffReport {
  return {
    model_name: "churn",
    winner: "XGBoost",
    n_algorithms_tested: 7,
    rows: [
      {
        name: "XGBoost",
        cv_macro_f1_mean: 0.804,
        cv_macro_f1_std: 0.021,
        test_macro_f1: 0.81,
        test_binary_auc: 0.979,
        inference_time_us: 570,
      },
      {
        name: "LightGBM",
        cv_macro_f1_mean: 0.806,
        cv_macro_f1_std: 0.012,
        test_macro_f1: 0.797,
        test_binary_auc: 0.975,
        inference_time_us: 1548,
      },
      {
        name: "CatBoost",
        cv_macro_f1_mean: 0.778,
        cv_macro_f1_std: 0.009,
        test_macro_f1: 0.771,
        test_binary_auc: 0.975,
        inference_time_us: 472,
      },
      {
        name: "RandomForest",
        cv_macro_f1_mean: 0.785,
        cv_macro_f1_std: 0.012,
        test_macro_f1: 0.781,
        test_binary_auc: 0.974,
        inference_time_us: 53870,
      },
      {
        name: "MLP",
        cv_macro_f1_mean: 0.706,
        cv_macro_f1_std: 0.022,
        test_macro_f1: 0.712,
        test_binary_auc: 0.945,
        inference_time_us: 251,
      },
      {
        name: "LogisticRegression",
        cv_macro_f1_mean: 0.675,
        cv_macro_f1_std: 0.027,
        test_macro_f1: 0.703,
        test_binary_auc: 0.942,
        inference_time_us: 150,
      },
      {
        name: "SVM_RBF",
        cv_macro_f1_mean: 0.632,
        cv_macro_f1_std: 0.015,
        test_macro_f1: 0.589,
        test_binary_auc: 0.933,
        inference_time_us: 262,
      },
    ],
  };
}

function survivalPayload(): MlBakeoffReport {
  return {
    model_name: "survival",
    winner: "GradientBoostingSurvival",
    n_algorithms_tested: 3,
    rows: [
      {
        name: "GradientBoostingSurvival",
        c_index_test: 0.751,
        c_index_train: 0.806,
        inference_time_us: 297,
      },
      {
        name: "XGBoost_AFT",
        c_index_test: 0.718,
        c_index_train: 0.813,
        inference_time_us: 463,
      },
      {
        name: "Weibull_AFT",
        c_index_test: 0.663,
        c_index_train: 0.653,
        inference_time_us: 6638,
      },
    ],
  };
}

function renderWithClient(p: MlBakeoffReport, model: "churn" | "survival") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => p,
      text: async () => JSON.stringify(p),
    })),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <BakeoffTable model={model} />
    </QueryClientProvider>,
  );
}

describe("BakeoffTable — churn", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders 5 rows by default with the winner row marked", async () => {
    renderWithClient(churnPayload(), "churn");
    await waitFor(() => screen.getByTestId("bakeoff-table-churn"));
    const table = screen.getByTestId("bakeoff-table-rows-churn");
    expect(table.querySelectorAll("tbody tr")).toHaveLength(5);
    expect(screen.getByTestId("bakeoff-row-XGBoost").dataset.winner).toBe("true");
    expect(screen.getByTestId("bakeoff-winner-badge")).toBeInTheDocument();
  });

  it("expands to all algorithms when Show all is clicked", async () => {
    renderWithClient(churnPayload(), "churn");
    await waitFor(() => screen.getByTestId("bakeoff-show-all-churn"));
    fireEvent.click(screen.getByTestId("bakeoff-show-all-churn"));
    const table = screen.getByTestId("bakeoff-table-rows-churn");
    expect(table.querySelectorAll("tbody tr")).toHaveLength(7);
  });

  it("renders churn-specific columns (CV F1 + Test F1 + AUC)", async () => {
    renderWithClient(churnPayload(), "churn");
    await waitFor(() => screen.getByTestId("bakeoff-table-churn"));
    expect(screen.getByText("CV F1")).toBeInTheDocument();
    expect(screen.getByText("Test F1")).toBeInTheDocument();
    expect(screen.getByText("AUC")).toBeInTheDocument();
  });
});

describe("BakeoffTable — survival", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders survival-specific columns (C-test + C-train)", async () => {
    renderWithClient(survivalPayload(), "survival");
    await waitFor(() => screen.getByTestId("bakeoff-table-survival"));
    expect(screen.getByText("C-test")).toBeInTheDocument();
    expect(screen.getByText("C-train")).toBeInTheDocument();
  });

  it("marks the GradientBoostingSurvival row as winner", async () => {
    renderWithClient(survivalPayload(), "survival");
    await waitFor(() => screen.getByTestId("bakeoff-table-survival"));
    expect(
      screen.getByTestId("bakeoff-row-GradientBoostingSurvival").dataset.winner,
    ).toBe("true");
  });
});
