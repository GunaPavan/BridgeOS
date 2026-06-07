"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Droplet,
  Heart,
  HeartPulse,
  Inbox,
  Mail,
  MessageSquare,
  Phone,
  Shield,
  User,
} from "lucide-react";

import { getIdTokenForRequest } from "@/lib/cognito";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// API shapes — mirror backend/app/api/donor_portal.py
// ---------------------------------------------------------------------------

interface DonorMe {
  id: string;
  name: string;
  age: number;
  blood_group: string;
  phone: string;
  email: string | null;
  city: string;
  state: string;
  preferred_language: string;
  preferred_channel: string;
  total_donations: number;
  response_rate: number;
  is_active: boolean;
}

interface DonorBridge {
  bridge_id: string;
  patient_name: string;
  patient_age: number;
  patient_blood_group: string;
  hospital: string;
  city: string;
  membership_status: string;
  role: string | null;
  next_transfusion_date: string | null;
  other_active_donor_count: number;
}

interface Cooldown {
  reason: string;
  patient_id: string | null;
  patient_name: string | null;
  expires_at: string;
  days_remaining: number;
  notes: string | null;
}

interface PingHistory {
  ping_id: string;
  wave_id: string;
  patient_name: string;
  sent_at: string | null;
  response: string;
  response_at: string | null;
  template_key: string | null;
  language: string | null;
}

// ---------------------------------------------------------------------------
// Fetch helpers — attach Cognito ID token automatically
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

export default function DonorPortalPage() {
  const [me, setMe] = useState<DonorMe | null>(null);
  const [bridges, setBridges] = useState<DonorBridge[]>([]);
  const [cooldowns, setCooldowns] = useState<Cooldown[]>([]);
  const [pings, setPings] = useState<PingHistory[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [meRes, brRes, cdRes, pgRes] = await Promise.all([
          authedFetch<DonorMe>("/donor/me"),
          authedFetch<DonorBridge[]>("/donor/me/bridges"),
          authedFetch<Cooldown[]>("/donor/me/cooldowns"),
          authedFetch<PingHistory[]>("/donor/me/pings?limit=20"),
        ]);
        if (!alive) return;
        setMe(meRes);
        setBridges(brRes);
        setCooldowns(cdRes);
        setPings(pgRes);
      } catch (e) {
        if (!alive) return;
        setErr((e as Error).message);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  async function updatePreferences(
    field: "preferred_channel" | "preferred_language",
    value: string,
  ) {
    setBusy(true);
    setSavedMsg(null);
    setErr(null);
    try {
      const updated = await authedFetch<DonorMe>("/donor/me/preferences", {
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

  async function optOut() {
    if (!confirm("Stop all future outreach for 12 months? You can rejoin any time by asking your coordinator.")) {
      return;
    }
    setBusy(true);
    try {
      await authedFetch<{ opted_out: boolean }>("/donor/me/opt-out", {
        method: "POST",
      });
      setSavedMsg("You've been opted out. Thank you for everything you did.");
      const meRes = await authedFetch<DonorMe>("/donor/me");
      setMe(meRes);
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
            Most likely your account isn't linked to a donor record yet. Ask
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
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-widest text-accent">Donor portal</p>
            <h1 className="mt-2 text-3xl font-bold">Welcome, {me.name.split(" ")[0]}</h1>
            <p className="mt-2 text-sm text-white/65">
              The patients you donate to, your donation history, and your outreach
              preferences — all in one place.
            </p>
          </div>
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${me.is_active ? "bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30" : "bg-white/5 text-white/60 ring-1 ring-white/10"}`}>
            <Shield className="h-3 w-3" />
            {me.is_active ? "Active donor" : "Opted out"}
          </span>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat icon={Droplet} label="Blood group" value={me.blood_group} />
          <Stat icon={Heart} label="Donations" value={String(me.total_donations)} />
          <Stat
            icon={CheckCircle2}
            label="Response rate"
            value={`${Math.round(me.response_rate * 100)}%`}
          />
          <Stat icon={User} label="City" value={me.city} />
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
        {/* ---- Patients I serve ---- */}
        <section className="lg:col-span-2 rounded-2xl border border-white/5 bg-surface/40 p-6">
          <div className="mb-4 flex items-center gap-2">
            <HeartPulse className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
              Patients you donate to
            </h2>
          </div>
          {bridges.length === 0 ? (
            <p className="text-sm text-white/50">
              You're not assigned to any active bridge yet. Your coordinator will
              add you when a match comes up.
            </p>
          ) : (
            <ul className="space-y-3">
              {bridges.map((b) => (
                <li
                  key={b.bridge_id}
                  className="rounded-xl border border-white/5 bg-background/40 p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-white">
                        {b.patient_name}
                        <span className="ml-2 text-xs text-white/40">
                          {b.patient_age} yrs · {b.patient_blood_group}
                        </span>
                      </p>
                      <p className="mt-1 text-xs text-white/55">
                        {b.hospital} · {b.city}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-accent ring-1 ring-accent/20">
                        {b.membership_status}
                      </span>
                      {b.role ? (
                        <span className="text-[10px] uppercase tracking-wider text-white/40">
                          {b.role}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-white/60">
                    {b.next_transfusion_date ? (
                      <span className="inline-flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        Next slot: {b.next_transfusion_date}
                      </span>
                    ) : null}
                    <span className="inline-flex items-center gap-1">
                      <User className="h-3 w-3" />
                      {b.other_active_donor_count} fellow donor
                      {b.other_active_donor_count === 1 ? "" : "s"} on this
                      bridge
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-[10px] text-white/30">
            Privacy note: we hide fellow donor identities to respect each
            donor's privacy. Coordinators see the full cohort.
          </p>
        </section>

        {/* ---- Preferences ---- */}
        <section className="rounded-2xl border border-white/5 bg-surface/40 p-6">
          <div className="mb-4 flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
              How we contact you
            </h2>
          </div>
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider text-white/40">
              Preferred channel
            </span>
            <select
              value={me.preferred_channel}
              onChange={(e) => updatePreferences("preferred_channel", e.target.value)}
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
              onChange={(e) => updatePreferences("preferred_language", e.target.value)}
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

          <div className="mt-6 space-y-2 border-t border-white/5 pt-4 text-xs text-white/55">
            <div className="flex items-center gap-2">
              <Phone className="h-3 w-3 text-white/40" />
              {me.phone}
            </div>
            {me.email ? (
              <div className="flex items-center gap-2">
                <Mail className="h-3 w-3 text-white/40" />
                {me.email}
              </div>
            ) : null}
          </div>

          {me.is_active ? (
            <button
              type="button"
              onClick={optOut}
              disabled={busy}
              className="mt-6 w-full rounded-md border border-red-500/30 bg-red-500/5 px-3 py-2 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-50"
            >
              Stop all outreach for now
            </button>
          ) : (
            <p className="mt-6 rounded-md border border-white/10 bg-white/5 p-3 text-[11px] text-white/55">
              You're currently opted out. Talk to your coordinator when you're
              ready to come back.
            </p>
          )}
        </section>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* ---- Cooldowns ---- */}
        <section className="rounded-2xl border border-white/5 bg-surface/40 p-6">
          <div className="mb-4 flex items-center gap-2">
            <Calendar className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
              Current cooldowns
            </h2>
          </div>
          {cooldowns.length === 0 ? (
            <p className="text-sm text-white/50">
              You're not on any cooldown right now — eligible to donate.
            </p>
          ) : (
            <ul className="space-y-2">
              {cooldowns.map((c, i) => (
                <li
                  key={i}
                  className="flex items-start justify-between gap-3 rounded-md border border-white/5 bg-background/40 p-3"
                >
                  <div>
                    <p className="text-sm font-medium text-white/85">
                      {c.reason.replaceAll("_", " ")}
                      {c.patient_name ? (
                        <span className="ml-2 text-xs text-white/40">
                          · {c.patient_name}
                        </span>
                      ) : null}
                    </p>
                    {c.notes ? (
                      <p className="mt-1 text-xs text-white/50">{c.notes}</p>
                    ) : null}
                  </div>
                  <span className="rounded bg-white/5 px-2 py-0.5 text-[10px] text-white/70">
                    {c.days_remaining}d left
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ---- Outreach history ---- */}
        <section className="rounded-2xl border border-white/5 bg-surface/40 p-6">
          <div className="mb-4 flex items-center gap-2">
            <Inbox className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
              Recent outreach
            </h2>
          </div>
          {pings.length === 0 ? (
            <p className="text-sm text-white/50">No outreach in your history yet.</p>
          ) : (
            <ul className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {pings.map((p) => (
                <li
                  key={p.ping_id}
                  className="flex items-start justify-between gap-3 rounded-md border border-white/5 bg-background/40 p-3"
                >
                  <div>
                    <p className="text-xs text-white/80">{p.patient_name}</p>
                    <p className="text-[10px] uppercase tracking-wider text-white/40">
                      {p.template_key ?? "manual"} · {p.language ?? "en"}
                    </p>
                  </div>
                  <span className={`rounded px-2 py-0.5 text-[10px] uppercase tracking-wider ${pingColor(p.response)}`}>
                    {p.response.replaceAll("_", " ")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function pingColor(r: string): string {
  if (r === "accepted") return "bg-emerald-500/15 text-emerald-300";
  if (r === "declined") return "bg-rose-500/15 text-rose-300";
  if (r === "no_reply" || r === "no-reply") return "bg-amber-500/15 text-amber-300";
  if (r === "cancelled") return "bg-white/10 text-white/60";
  return "bg-sky-500/15 text-sky-300";
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
      <p className="mt-1 text-lg font-semibold text-white">{value}</p>
    </div>
  );
}
