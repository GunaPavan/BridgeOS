"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { confirmSignUp, resendConfirmationCode } from "@/lib/cognito";

export default function ConfirmPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    const stored = sessionStorage.getItem("pendingSignupEmail");
    if (stored) setEmail(stored);
  }, []);

  async function confirm(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      await confirmSignUp(email, code);
      sessionStorage.removeItem("pendingSignupEmail");
      setMsg("Email verified. Redirecting to sign in…");
      setTimeout(() => router.push("/login"), 1200);
    } catch (e) {
      setErr((e as Error).message ?? "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      await resendConfirmationCode(email);
      setMsg("Code resent — check your inbox.");
    } catch (e) {
      setErr((e as Error).message ?? "Couldn't resend");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-surface/30 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <Link href="/" className="block text-center mb-8">
          <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-4xl font-bold text-transparent">
            Bridge OS
          </span>
        </Link>
        <div className="rounded-2xl border border-white/10 bg-surface/40 p-8 backdrop-blur">
          <h1 className="text-2xl font-bold text-white">Confirm your email</h1>
          <p className="mt-1 text-sm text-white/60">
            Enter the 6-digit code we sent to your email.
          </p>
          <form onSubmit={confirm} className="mt-6 space-y-4">
            <Field
              label="Email"
              type="email"
              value={email}
              onChange={setEmail}
              required
            />
            <Field
              label="Verification code"
              type="text"
              value={code}
              onChange={setCode}
              required
              hint="Sent by Amazon Cognito to your inbox"
              autoFocus
            />
            {err && (
              <div className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
                {err}
              </div>
            )}
            {msg && (
              <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-xs text-emerald-300">
                {msg}
              </div>
            )}
            <button
              type="submit"
              disabled={busy || !email || !code}
              className="w-full rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/85 disabled:opacity-50"
            >
              {busy ? "…" : "Confirm"}
            </button>
            <button
              type="button"
              onClick={resend}
              disabled={busy || !email}
              className="w-full rounded-lg border border-white/10 px-4 py-2 text-xs text-white/70 hover:border-white/30 hover:text-white disabled:opacity-50"
            >
              Resend code
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  type,
  value,
  onChange,
  required,
  autoFocus,
  hint,
}: {
  label: string;
  type: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  autoFocus?: boolean;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs uppercase tracking-wider text-white/40">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        autoFocus={autoFocus}
        className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-primary/50 focus:outline-none"
      />
      {hint && <p className="mt-1 text-[10px] text-white/40">{hint}</p>}
    </label>
  );
}
