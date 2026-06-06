import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind class names safely. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Format an ISO date string for display, e.g. "12 Jun 2026". */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/** Format "in N days" / "N days ago". */
export function formatDaysRelative(days: number | null | undefined): string {
  if (days === null || days === undefined) return "—";
  if (days === 0) return "today";
  if (days > 0) return `in ${days} day${days === 1 ? "" : "s"}`;
  const abs = Math.abs(days);
  return `${abs} day${abs === 1 ? "" : "s"} overdue`;
}

/** Display a value or "—" if it's missing / a placeholder.
 *
 * Real Blood Warriors data has many fields with placeholder values like
 * "(unspecified)" (when ingest couldn't resolve the source), "Unknown",
 * or "null" string. Render those as em-dash so the UI doesn't shout
 * meaningless tokens at coordinators.
 */
const PLACEHOLDER_TOKENS = new Set([
  "(unspecified)",
  "unknown",
  "null",
  "none",
  "n/a",
  "",
]);

export function displayOr(
  value: string | null | undefined,
  fallback = "—",
): string {
  if (value === null || value === undefined) return fallback;
  const trimmed = String(value).trim();
  if (PLACEHOLDER_TOKENS.has(trimmed.toLowerCase())) return fallback;
  return trimmed;
}

/** True if the value would render as the em-dash fallback. Use for
 *  conditional hiding of "Hospital: —" labels and similar. */
export function isMissing(value: string | null | undefined): boolean {
  return displayOr(value) === "—";
}
