"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { signIn } from "@/lib/cognito";

const ROLE_HOMES: Record<string, string> = {
  admin: "/dashboard",
  coordinator: "/dashboard",
  donor: "/donor",
  patient: "/patient",
};

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // ?next=<urlencoded path> lets the (app) auth guard tell us where the
  // user originally tried to go, so we land them back there after login
  // instead of always bouncing to the role default.
  const nextPath = searchParams?.get("next");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [forcePassword, setForcePassword] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const result = await signIn(email, password, {
        newPassword: forcePassword ? newPassword : undefined,
      });
      // Persist tokens so subsequent fetches can attach them
      sessionStorage.setItem("idToken", result.tokens.idToken);
      const dest =
        nextPath && nextPath.startsWith("/") ? nextPath : pickHome(result.groups);
      router.push(dest);
    } catch (e) {
      const code = (e as { code?: string }).code;
      const msg = (e as Error).message ?? "Login failed";
      if (code === "FORCE_CHANGE_PASSWORD") {
        setForcePassword(true);
        setErr("First-time login: please choose a new password.");
      } else {
        setErr(msg);
      }
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
          <h1 className="text-2xl font-bold text-white">Sign in</h1>
          <p className="mt-1 text-sm text-white/60">
            Admins, coordinators, donors, caregivers — all welcome.
          </p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <Field
              label="Email"
              type="email"
              value={email}
              onChange={setEmail}
              required
              autoFocus
            />
            <Field
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              required
            />
            {forcePassword && (
              <Field
                label="New password"
                type="password"
                value={newPassword}
                onChange={setNewPassword}
                required
                hint="At least 8 chars with upper, lower, number"
              />
            )}
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
              {busy ? "…" : forcePassword ? "Set new password" : "Sign in"}
            </button>
          </form>
          <div className="mt-6 grid grid-cols-2 gap-2 border-t border-white/10 pt-6 text-sm">
            <Link
              href="/signup/donor"
              className="rounded-lg border border-white/10 px-3 py-2 text-center text-white/80 hover:border-white/30 hover:text-white"
            >
              Sign up as donor
            </Link>
            <Link
              href="/signup/patient"
              className="rounded-lg border border-white/10 px-3 py-2 text-center text-white/80 hover:border-white/30 hover:text-white"
            >
              Sign up as caregiver
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function pickHome(groups: string[]): string {
  for (const g of ["admin", "coordinator", "donor", "patient"]) {
    if (groups.includes(g)) return ROLE_HOMES[g];
  }
  return "/dashboard";
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
      <span className="text-xs uppercase tracking-wider text-white/40">
        {label}
      </span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        autoFocus={autoFocus}
        className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-primary/50 focus:outline-none"
      />
      {hint && <p className="mt-1 text-[10px] text-white/40">{hint}</p>}
    </label>
  );
}
