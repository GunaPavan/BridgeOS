import Link from "next/link";
import { Droplet, MapPin, Network, ShieldCheck, Zap } from "lucide-react";

import type { DonorListItem } from "@/lib/api";
import { cn, displayOr, formatDate, isMissing } from "@/lib/utils";

export function DonorCard({ donor }: { donor: DonorListItem }) {
  const responsePct = Math.round(donor.response_rate * 100);
  return (
    <Link
      href={`/donors/${donor.id}`}
      className={cn(
        "group block rounded-xl border border-white/10 bg-surface/40 p-5",
        "transition-all hover:border-accent/40 hover:bg-surface/60",
        !donor.is_active && "opacity-60",
      )}
      data-testid="donor-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold text-white">{donor.name}</h3>
            {donor.kell_negative ? (
              <ShieldCheck
                className="h-4 w-4 text-accent"
                aria-label="Kell-negative donor"
              />
            ) : null}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-sm text-white/60">
            <span>{donor.age} years old</span>
            {donor.external_handle ? (
              <span
                className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-white/45"
                title="Source dataset user ID"
              >
                #{donor.external_handle}
              </span>
            ) : null}
          </div>
        </div>
        <span
          className={cn(
            "rounded-md bg-white/5 px-2 py-0.5 font-mono text-xs",
            donor.blood_group.endsWith("-") ? "text-accent" : "text-primary",
          )}
        >
          {donor.blood_group}
        </span>
      </div>

      <div className="mt-3 flex items-center gap-1.5 text-xs text-white/50">
        <MapPin className="h-3 w-3" aria-hidden />
        <span>
          {isMissing(donor.city)
            ? "Location not on file"
            : `${displayOr(donor.city)}, ${displayOr(donor.state)}`}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 border-t border-white/5 pt-3 text-xs">
        <Stat icon={Droplet} label="Donations" value={String(donor.total_donations)} />
        <Stat icon={Zap} label="Response" value={`${responsePct}%`} />
        <Stat icon={Network} label="Bridges" value={String(donor.bridge_count)} />
      </div>

      <div className="mt-3 flex items-center justify-between text-xs">
        <span className="text-white/40">
          Last: {formatDate(donor.last_donation_date)}
        </span>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider",
            donor.is_eligible_to_donate
              ? "bg-emerald-500/15 text-emerald-300"
              : "bg-white/5 text-white/40",
          )}
        >
          {donor.is_eligible_to_donate ? "Eligible" : "Cooldown"}
        </span>
      </div>
    </Link>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Droplet;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-1.5 text-white/70" title={label}>
      <Icon className="h-3 w-3 shrink-0 text-white/40" aria-hidden />
      <span className="text-white">{value}</span>
    </div>
  );
}
