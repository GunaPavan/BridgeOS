import Link from "next/link";
import { Calendar, MapPin, Users } from "lucide-react";

import { HealthBadge } from "@/components/ui/health-badge";
import type { BridgeListItem } from "@/lib/api";
import { cn, displayOr, formatDaysRelative, isMissing } from "@/lib/utils";

export function BridgeCard({ bridge }: { bridge: BridgeListItem }) {
  return (
    <Link
      href={`/bridges/${bridge.id}`}
      className={cn(
        "group block rounded-xl border border-white/10 bg-surface/40 p-5",
        "transition-all hover:border-primary/40 hover:bg-surface/60",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-white/40">
            {bridge.blood_group}
          </p>
          <h3 className="mt-1 text-lg font-semibold text-white">
            {bridge.patient_name}
          </h3>
          <p className="text-sm text-white/60">{bridge.patient_age} years old</p>
        </div>
        <HealthBadge health={bridge.health} />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-white/5 pt-4 text-sm">
        <div className="flex items-center gap-1.5 text-white/70">
          <Users className="h-3.5 w-3.5" aria-hidden />
          <span>
            <span className="font-medium text-white">{bridge.active_donor_count}</span>
            <span className="text-white/50"> donors</span>
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-white/70">
          <Calendar className="h-3.5 w-3.5" aria-hidden />
          <span>{formatDaysRelative(bridge.days_until_transfusion)}</span>
        </div>
        <div className="col-span-2 flex items-center gap-1.5 text-white/60">
          <MapPin className="h-3.5 w-3.5" aria-hidden />
          <span>
            {isMissing(bridge.hospital)
              ? displayOr(bridge.city)
              : `${displayOr(bridge.hospital)} · ${displayOr(bridge.city)}`}
          </span>
        </div>
      </div>
    </Link>
  );
}
