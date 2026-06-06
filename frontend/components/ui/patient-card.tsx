import Link from "next/link";
import { Building2, Calendar, MapPin, ShieldCheck, Users } from "lucide-react";

import { HealthBadge } from "@/components/ui/health-badge";
import type { PatientListItem } from "@/lib/api";
import { cn, displayOr, formatDaysRelative, isMissing } from "@/lib/utils";

export function PatientCard({ patient }: { patient: PatientListItem }) {
  return (
    <Link
      href={`/patients/${patient.id}`}
      className={cn(
        "group block rounded-xl border border-white/10 bg-surface/40 p-5",
        "transition-all hover:border-primary/40 hover:bg-surface/60",
        !patient.active && "opacity-60",
      )}
      data-testid="patient-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold text-white">{patient.name}</h3>
            {patient.kell_negative ? (
              <ShieldCheck
                className="h-4 w-4 text-accent"
                aria-label="Kell-negative — alloimmunization risk if mismatched"
              />
            ) : null}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-sm text-white/60">
            <span>{patient.age} years old</span>
            {patient.external_handle ? (
              <span
                className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-white/45"
                title="Source dataset user ID"
              >
                #{patient.external_handle}
              </span>
            ) : null}
          </div>
        </div>
        <span className="rounded-md bg-white/5 px-2 py-0.5 font-mono text-xs text-primary">
          {patient.blood_group}
        </span>
      </div>

      <div className="mt-3 flex items-center gap-1.5 text-xs text-white/50">
        {!isMissing(patient.hospital) && (
          <>
            <Building2 className="h-3 w-3" aria-hidden />
            <span className="truncate">{displayOr(patient.hospital)}</span>
            <span className="text-white/30">·</span>
          </>
        )}
        <MapPin className="h-3 w-3" aria-hidden />
        <span>{displayOr(patient.city)}</span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-white/5 pt-3 text-sm">
        <div className="flex items-center gap-1.5 text-white/70">
          <Calendar className="h-3.5 w-3.5" aria-hidden />
          <span>{formatDaysRelative(patient.days_until_transfusion)}</span>
        </div>
        <div className="flex items-center gap-1.5 text-white/70">
          <Users className="h-3.5 w-3.5" aria-hidden />
          <span>
            {patient.has_bridge ? (
              <>
                <span className="font-medium text-white">{patient.active_donor_count}</span>
                <span className="text-white/50"> donors</span>
              </>
            ) : (
              <span className="text-amber-300/80">No bridge</span>
            )}
          </span>
        </div>
      </div>

      {patient.bridge_health ? (
        <div className="mt-3 flex items-center justify-between text-xs">
          <span className="text-white/40">Cadence: every {patient.transfusion_cadence_days}d</span>
          <HealthBadge health={patient.bridge_health} />
        </div>
      ) : (
        <p className="mt-3 text-xs text-amber-300/70">
          Needs a bridge assigned.
        </p>
      )}
    </Link>
  );
}
