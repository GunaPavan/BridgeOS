"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Calendar,
  Droplet,
  HeartPulse,
  Inbox,
  Mail,
  MessageSquare,
  Phone,
  Shield,
  Stethoscope,
  UserCircle2,
  Users,
} from "lucide-react";

import { getIdTokenForRequest } from "@/lib/cognito";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Shapes — mirror backend/app/api/patient_portal.py
// ---------------------------------------------------------------------------

interface PatientMe {
  id: string;
  name: string;
  age: number;
  blood_group: string;
  city: string;
  hospital: string;
  transfusion_cadence_days: number;
  last_transfusion_date: string | null;
  next_transfusion_date: string | null;
  caregiver_name: string | null;
  caregiver_email: string | null;
  caregiver_phone: string | null;
  caregiver_relation: string | null;
  caregiver_preferred_channel: string;
  preferred_language: string;
}

interface DonorOnBridge {
  donor_id: string;
  name: string;
  city: string;
  blood_group: string;
  last_donation_date: string | null;
  membership_status: string;
}

interface MyBridge {
  bridge_id: string;
  bridge_status: string;
  active_donors: DonorOnBridge[];
  pending_donors: DonorOnBridge[];
}

interface WaveSummary {
  wave_id: string;
  slot_date: string;
  status: string;
  urgency: string;
  tier: string;
  pings_sent: number;
  pings_accepted: number;
  pings_declined: number;
  pings_no_reply: number;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Auth helper
// ---------------------------------------------------------------------------

async function authedFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getIdTokenForRequest();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${res.status}: ${txt || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PatientPortalPage() {
  const [me, setMe] = useState<PatientMe | null>(null);
  const [bridge, setBridge] = useState<MyBridge | null>(null);
  const [waves, setWaves] = useState<WaveSummary[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [bridgeErr, setBridgeErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const meRes = await authedFetch<PatientMe>("/patient/me");
        if (!alive) return;
        setMe(meRes);
      } catch (e) {
        if (!alive) return;
        setErr((e as Error).message);
        return;
      }
      try {
        const brRes = await authedFetch<MyBridge>("/patient/me/bridge");
        if (alive) setBridge(brRes);
      } catch (e) {
        if (alive) setBridgeErr((e as Error).message);
      }
      try {
        const wvRes = await authedFetch<WaveSummary[]>("/patient/me/outreach");
        if (alive) setWaves(wvRes);
      } catch {
        // outreach is optional view
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  async function updatePrefs(field: string, value: string) {
    setBusy(true);
    setSavedMsg(null);
    try {
      const updated = await authedFetch<PatientMe>("/patient/me/caregiver", {
        method: "PATCH",
        body: JSON.stringify({ [field]: value }),
      });
      setMe(updated);
      setSavedMsg("Preferences updated.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function cancelOutreach() {
    if (!confirm("Cancel all active outreach? Use this if you already found a donor yourselves.")) {
      return;
    }
    setBusy(true);
    try {
      const result = await authedFetch<{ cancelled_waves: number }>(
        "/patient/me/outreach/cancel",
        { method: "POST" },
      );
      setSavedMsg(
        `Cancelled ${result.cancelled_waves} active outreach wave${result.cancelled_waves === 1 ? "" : "s"}.`,
      );
      const wvRes = await authedFetch<WaveSummary[]>("/patient/me/outreach");
      setWaves(wvRes);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (err && !me) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-8">
          <AlertTriangle className="h-6 w-6 text-red-400" />
          <h1 className="mt-4 text-xl font-bold">Couldn't load your portal</h1>
          <p className="mt-2 text-sm text-white/65">{err}</p>
          <p className="mt-4 text-xs text-white/50">
            Most likely your account isn't linked to a patient record yet. Ask
            your coordinator to link it, then refresh this page.
          </p>
          <Link
            href="/login"
            className="mt-6 inline-flex items-center gap-2 rounded-full border border-white/15 px-4 py-2 text-xs hover:border-white/30"
          >
            Back to sign-in
          </Link>
        </div>
      </div>
    );
  }

  if (!me) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16 text-sm text-white/55">
        Loading your portal…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      {/* ---- Hero ---- */}
      <div className="rounded-2xl border border-white/5 bg-gradient-to-br from-primary/10 to-accent/5 p-8">
        <p className="text-xs uppercase tracking-widest text-accent">Patient portal</p>
        <h1 className="mt-2 text-3xl font-bold">{me.name}</h1>
        <p className="mt-2 text-sm text-white/65">
          {me.age} years · {me.blood_group} · {me.hospital}, {me.city}
        </p>

        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat icon={Droplet} label="Blood group" value={me.blood_group} />
          <Stat
            icon={Calendar}
            label="Cadence"
            value={`every ${me.transfusion_cadence_days}d`}
          />
          <Stat
            icon={Calendar}
            label="Last transfusion"
            value={me.last_transfusion_date ?? "—"}
          />
          <Stat
            icon={Calendar}
            label="Next transfusion"
            value={me.next_transfusion_date ?? "—"}
          />
        </div>
      </div>

      {savedMsg ? (
        <div className="mt-4 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-xs text-emerald-300">
          {savedMsg}
        </div>
      ) : null}
      {err ? (
        <div className="mt-4 rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-xs text-red-300">
          {err}
        </div>
      ) : null}

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* ---- Your bridge ---- */}
        <section className="lg:col-span-2 rounded-2xl border border-white/5 bg-surface/40 p-6">
          <div className="mb-4 flex items-center gap-2">
            <HeartPulse className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
              Your bridge
            </h2>
          </div>
          {bridgeErr ? (
            <p className="text-sm text-white/55">
              No bridge yet — your coordinator will create one for you.
            </p>
          ) : !bridge ? (
            <p className="text-sm text-white/55">Loading donors…</p>
          ) : (
            <>
              <p className="mb-3 text-xs uppercase tracking-wider text-white/40">
                {bridge.active_donors.length} active · {bridge.pending_donors.length} pending
              </p>
              {bridge.active_donors.length === 0 && bridge.pending_donors.length === 0 ? (
                <p className="text-sm text-white/55">
                  No donors on your bridge yet. Your coordinator is recruiting.
                </p>
              ) : (
                <ul className="space-y-2">
                  {[...bridge.active_donors, ...bridge.pending_donors].map((d) => (
                    <li
                      key={d.donor_id}
                      className="flex items-start justify-between gap-3 rounded-xl border border-white/5 bg-background/40 p-4"
                    >
                      <div>
                        <p className="font-semibold text-white">
                          {d.name}
                          <span className="ml-2 text-xs text-white/40">
                            {d.blood_group} · {d.city}
                          </span>
                        </p>
                        {d.last_donation_date ? (
                          <p className="mt-1 text-xs text-white/55">
                            Last donated: {d.last_donation_date}
                          </p>
                        ) : null}
                      </div>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider ${d.membership_status === "active" ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30" : "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30"}`}>
                        {d.membership_status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>

        {/* ---- Caregiver preferences ---- */}
        <section className="rounded-2xl border border-white/5 bg-surface/40 p-6">
          <div className="mb-4 flex items-center gap-2">
            <Stethoscope className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
              Caregiver details
            </h2>
          </div>
          <div className="space-y-2 text-xs text-white/65">
            {me.caregiver_name ? (
              <div className="flex items-center gap-2">
                <UserCircle2 className="h-3 w-3 text-white/40" />
                {me.caregiver_name}
                {me.caregiver_relation ? (
                  <span className="text-white/35">({me.caregiver_relation})</span>
                ) : null}
              </div>
            ) : null}
            {me.caregiver_phone ? (
              <div className="flex items-center gap-2">
                <Phone className="h-3 w-3 text-white/40" />
                {me.caregiver_phone}
              </div>
            ) : null}
            {me.caregiver_email ? (
              <div className="flex items-center gap-2">
                <Mail className="h-3 w-3 text-white/40" />
                {me.caregiver_email}
              </div>
            ) : null}
          </div>

          <label className="mt-5 block">
            <span className="text-[11px] uppercase tracking-wider text-white/40">
              Preferred channel
            </span>
            <select
              value={me.caregiver_preferred_channel}
              onChange={(e) => updatePrefs("caregiver_preferred_channel", e.target.value)}
              disabled={busy}
              className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-white"
            >
              <option value="whatsapp">WhatsApp</option>
              <option value="sms">SMS</option>
              <option value="email">Email</option>
              <option value="voice">Phone call</option>
            </select>
          </label>
          <label className="mt-4 block">
            <span className="text-[11px] uppercase tracking-wider text-white/40">
              Preferred language
            </span>
            <select
              value={me.preferred_language}
              onChange={(e) => updatePrefs("preferred_language", e.target.value)}
              disabled={busy}
              className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-white"
            >
              <option value="en">English</option>
              <option value="hi">हिन्दी</option>
              <option value="te">తెలుగు</option>
              <option value="ta">தமிழ்</option>
              <option value="mr">मराठी</option>
              <option value="bn">বাংলা</option>
              <option value="kn">ಕನ್ನಡ</option>
              <option value="gu">ગુજરાતી</option>
            </select>
          </label>
        </section>
      </div>

      {/* ---- Outreach ---- */}
      <section className="mt-6 rounded-2xl border border-white/5 bg-surface/40 p-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Inbox className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
              Outreach in progress
            </h2>
          </div>
          {waves.some((w) => w.status === "active") ? (
            <button
              type="button"
              onClick={cancelOutreach}
              disabled={busy}
              className="rounded-md border border-white/10 px-3 py-1 text-xs text-white/70 hover:border-white/30 hover:text-white disabled:opacity-50"
            >
              We found a donor — cancel all
            </button>
          ) : null}
        </div>
        {waves.length === 0 ? (
          <p className="text-sm text-white/50">
            No active outreach right now. We'll start one as your next transfusion approaches.
          </p>
        ) : (
          <ul className="space-y-2">
            {waves.map((w) => (
              <li
                key={w.wave_id}
                className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-white/5 bg-background/40 p-4"
              >
                <div>
                  <p className="font-medium text-white">
                    Slot {w.slot_date}
                    <span className="ml-2 text-xs text-white/40">
                      created {w.created_at.split("T")[0]}
                    </span>
                  </p>
                  <p className="mt-1 text-xs text-white/55">
                    Tier {w.tier} · {w.urgency}
                  </p>
                  <p className="mt-2 inline-flex flex-wrap gap-2 text-[11px]">
                    <PingBadge label={`sent ${w.pings_sent}`} color="white" />
                    <PingBadge label={`yes ${w.pings_accepted}`} color="emerald" />
                    <PingBadge label={`no ${w.pings_declined}`} color="rose" />
                    <PingBadge label={`silent ${w.pings_no_reply}`} color="amber" />
                  </p>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider ${w.status === "active" ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30" : "bg-white/5 text-white/60 ring-1 ring-white/10"}`}>
                  {w.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ---- Help / contact strip ---- */}
      <div className="mt-6 rounded-2xl border border-white/5 bg-surface/30 p-5 text-xs text-white/55">
        <div className="flex flex-wrap items-center gap-3">
          <Shield className="h-3.5 w-3.5 text-accent" />
          <span>
            Your data is private — only your coordinator and assigned donors see
            it. Your fellow patients never do.
          </span>
        </div>
        <p className="mt-2 text-white/40">
          Want a change to your bridge? Reply to any outreach email or WhatsApp
          and a coordinator will pick it up.
        </p>
      </div>
    </div>
  );
}

function PingBadge({
  label,
  color,
}: {
  label: string;
  color: "white" | "emerald" | "rose" | "amber";
}) {
  const colorClass =
    color === "emerald"
      ? "bg-emerald-500/15 text-emerald-300"
      : color === "rose"
        ? "bg-rose-500/15 text-rose-300"
        : color === "amber"
          ? "bg-amber-500/15 text-amber-300"
          : "bg-white/10 text-white/70";
  return (
    <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 ${colorClass}`}>
      <MessageSquare className="h-2.5 w-2.5" />
      {label}
    </span>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-white/5 bg-background/40 px-4 py-3">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-white/40">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <p className="mt-1 text-base font-semibold text-white">{value}</p>
    </div>
  );
}
