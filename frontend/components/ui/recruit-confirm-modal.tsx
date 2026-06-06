"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Globe, Loader2, MessageSquareText, UserPlus, X } from "lucide-react";

import { cn } from "@/lib/utils";

const LANGUAGES: { code: RecruitLanguage; label: string; native: string }[] = [
  { code: "en", label: "English", native: "English" },
  { code: "hi", label: "Hindi", native: "हिन्दी" },
  { code: "te", label: "Telugu", native: "తెలుగు" },
  { code: "ta", label: "Tamil", native: "தமிழ்" },
  { code: "mr", label: "Marathi", native: "मराठी" },
  { code: "bn", label: "Bengali", native: "বাংলা" },
  { code: "kn", label: "Kannada", native: "ಕನ್ನಡ" },
  { code: "gu", label: "Gujarati", native: "ગુજરાતી" },
];

export type RecruitLanguage =
  | "en"
  | "hi"
  | "te"
  | "ta"
  | "mr"
  | "bn"
  | "kn"
  | "gu";

/**
 * Modal shown when the coordinator clicks Recruit.
 * G1: explicit, language-aware consent — no more one-click silent inserts.
 */
export function RecruitConfirmModal({
  open,
  candidateName,
  candidateLanguage,
  replaceDonorName,
  patientName,
  isSubmitting,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  candidateName: string;
  candidateLanguage: RecruitLanguage;
  replaceDonorName: string | null;
  patientName: string;
  isSubmitting: boolean;
  onCancel: () => void;
  onConfirm: (language: RecruitLanguage) => void;
}) {
  const [language, setLanguage] = useState<RecruitLanguage>(candidateLanguage);

  // Reset selected language when modal re-opens
  useEffect(() => {
    if (open) setLanguage(candidateLanguage);
  }, [open, candidateLanguage]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isSubmitting) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, isSubmitting, onCancel]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          data-testid="recruit-confirm-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="recruit-modal-title"
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => !isSubmitting && onCancel()}
          />

          <motion.div
            className="relative w-full max-w-md rounded-2xl border border-white/10 bg-surface/95 p-6 shadow-2xl"
            initial={{ scale: 0.96, opacity: 0, y: 8 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.96, opacity: 0, y: 8 }}
            transition={{ type: "spring", stiffness: 220, damping: 22 }}
          >
            <button
              type="button"
              onClick={onCancel}
              disabled={isSubmitting}
              aria-label="Close"
              className="absolute right-3 top-3 rounded p-1 text-white/40 transition-colors hover:bg-white/5 hover:text-white disabled:opacity-50"
            >
              <X className="h-4 w-4" />
            </button>

            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-primary/15 p-2 ring-1 ring-primary/30">
                <MessageSquareText className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h3
                  id="recruit-modal-title"
                  className="text-base font-semibold text-white"
                >
                  Send WhatsApp invite?
                </h3>
                <p className="mt-1 text-sm text-white/60">
                  This sends a recruit invite to{" "}
                  <span className="font-medium text-white">{candidateName}</span>{" "}
                  in the language below.{" "}
                  <span className="text-white/80">
                    {candidateName.split(" ")[0]} only joins{" "}
                    {patientName ? `${patientName}'s bridge` : "the bridge"} once
                    they reply YES.
                  </span>
                </p>
                {replaceDonorName ? (
                  <p className="mt-2 text-xs text-white/55">
                    Replaces{" "}
                    <span className="text-white/80">{replaceDonorName}</span>.
                    They stay active until {candidateName.split(" ")[0]}{" "}
                    confirms.
                  </p>
                ) : null}
              </div>
            </div>

            <div className="mt-5">
              <label className="mb-1.5 flex items-center gap-1.5 text-xs uppercase tracking-wider text-white/40">
                <Globe className="h-3 w-3" />
                Invite language
              </label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value as RecruitLanguage)}
                disabled={isSubmitting}
                data-testid="recruit-modal-language"
                className="w-full rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-primary/50 focus:outline-none disabled:opacity-50"
              >
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label} ({l.native})
                  </option>
                ))}
              </select>
              {language !== candidateLanguage ? (
                <p className="mt-1.5 text-[11px] text-amber-300/80">
                  Overriding {candidateName.split(" ")[0]}'s preferred language (
                  {candidateLanguage}).
                </p>
              ) : (
                <p className="mt-1.5 text-[11px] text-white/40">
                  Defaults to the donor's preferred language.
                </p>
              )}
            </div>

            <div className="mt-6 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={onCancel}
                disabled={isSubmitting}
                data-testid="recruit-modal-cancel"
                className={cn(
                  "rounded-md border border-white/10 px-3 py-1.5 text-sm text-white/70 transition-colors hover:bg-white/5 hover:text-white",
                  isSubmitting && "opacity-50",
                )}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => onConfirm(language)}
                disabled={isSubmitting}
                data-testid="recruit-modal-confirm"
                className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white shadow-lg shadow-primary/20 transition hover:bg-primary/80 disabled:opacity-50"
              >
                {isSubmitting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <UserPlus className="h-3.5 w-3.5" />
                )}
                Send invite
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
