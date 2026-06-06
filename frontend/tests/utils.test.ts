import { describe, expect, it } from "vitest";

import { cn, formatDate, formatDaysRelative } from "@/lib/utils";

describe("cn", () => {
  it("merges tailwind classes", () => {
    expect(cn("text-sm", "text-lg")).toBe("text-lg");
  });

  it("handles falsy values", () => {
    expect(cn("base", false && "ignored", null, "kept")).toBe("base kept");
  });
});

describe("formatDate", () => {
  it("returns em-dash for null", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
  });

  it("formats an ISO date in en-IN style", () => {
    const result = formatDate("2026-06-15");
    expect(result).toMatch(/15/);
    expect(result).toMatch(/Jun/);
    expect(result).toMatch(/2026/);
  });
});

describe("formatDaysRelative", () => {
  it("returns em-dash for null", () => {
    expect(formatDaysRelative(null)).toBe("—");
  });

  it("renders 'today' for 0", () => {
    expect(formatDaysRelative(0)).toBe("today");
  });

  it("pluralises future days", () => {
    expect(formatDaysRelative(1)).toBe("in 1 day");
    expect(formatDaysRelative(6)).toBe("in 6 days");
  });

  it("renders overdue for past days", () => {
    expect(formatDaysRelative(-1)).toBe("1 day overdue");
    expect(formatDaysRelative(-3)).toBe("3 days overdue");
  });
});
