"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { signUp, type SignupRole } from "@/lib/cognito";

export function SignupForm({
  role,
  accentClass,
  title,
  blurb,
}: {
  role: SignupRole;
  accentClass: string;
  title: string;
  blurb: string;
}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (password !== confirm) {
      setErr("Passwords don't match");
      return;
    }
    if (password.length < 8) {
      setErr("Password must be at least 8 characters with upper, lower, number");
      return;
    }
    setBusy(true);
    try {
      await signUp({
        email,
        password,
        role,
        name: name || undefined,
        phone: phone || undefined,
      });
      sessionStorage.setItem("pendingSignupEmail", email);
      router.push("/signup/confirm");
    } catch (e) {
      setErr((e as Error).message ?? "Signup failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-surface/30 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <Link href="/signup" className="block text-center mb-6 text-xs text-white/40 hover:text-white/70">
          ← Pick a different role
        </Link>
        <div className="rounded-2xl border border-white/10 bg-surface/40 p-8 backdrop-blur">
          <h1 className={`text-2xl font-bold ${accentClass}`}>{title}</h1>
          <p className="mt-1 text-sm text-white/60">{blurb}</p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <Field label="Full name" type="text" value={name} onChange={setName} />
            <Field label="Email" type="email" value={email} onChange={setEmail} required />
            <Field
              label="Phone (E.164, e.g. +91…)"
              type="tel"
              value={phone}
              onChange={setPhone}
              hint="Used for WhatsApp / SMS outreach"
            />
            <Field
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              required
              hint="8+ chars · upper · lower · number"
            />
            <Field
              label="Confirm password"
              type="password"
              value={confirm}
              onChange={setConfirm}
              required
            />
            {err && (
              <div className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
                {err}
              </div>
            )}
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/85 disabled:opacity-50"
            >
              {busy ? "Creating account…" : "Create account"}
            </button>
          </form>
          <p className="mt-4 text-center text-xs text-white/40">
            Already have an account?{" "}
            <Link href="/login" className="text-primary hover:underline">
              Sign in
            </Link>
          </p>
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
  hint,
}: {
  label: string;
  type: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
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
        className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-primary/50 focus:outline-none"
      />
      {hint && <p className="mt-1 text-[10px] text-white/40">{hint}</p>}
    </label>
  );
}
