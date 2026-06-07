"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity,
  BarChart3,
  Bell,
  Cable,
  HeartPulse,
  Inbox,
  LayoutDashboard,
  Mail,
  MessageSquare,
  Network,
  Play,
  Settings,
  Sparkles,
  UserCircle2,
  Users,
  Zap,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { DatasetClockBanner } from "@/components/ui/dataset-clock-banner";
import { decodeTokenClaims, getIdTokenForRequest } from "@/lib/cognito";

type RoleScope = "admin" | "coordinator" | "donor" | "patient" | "any";

interface NavItem {
  label: string;
  href: string;
  icon: typeof LayoutDashboard;
  /**
   * Which signed-in roles see this item.
   * - "any"          — everyone (admin / coordinator / donor / patient)
   * - "admin"        — only admins
   * - "coordinator"  — admins + coordinators (default operational scope)
   * - "donor"        — donors only
   * - "patient"      — patients only
   */
  scope?: RoleScope;
  comingSoon?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/dashboard", icon: LayoutDashboard, scope: "coordinator" },
  { label: "Bridges", href: "/bridges", icon: Network, scope: "coordinator" },
  { label: "Donors", href: "/donors", icon: Users, scope: "coordinator" },
  { label: "Patients", href: "/patients", icon: UserCircle2, scope: "coordinator" },
  { label: "Recommendations", href: "/recommendations", icon: Inbox, scope: "coordinator" },
  { label: "Outreach", href: "/outreach", icon: Zap, scope: "coordinator" },
  { label: "Automation", href: "/system/scheduler", icon: Activity, scope: "coordinator" },
  { label: "Simulator", href: "/simulator", icon: Play, scope: "coordinator" },
  { label: "Analytics", href: "/analytics", icon: BarChart3, scope: "coordinator" },
  { label: "Integrations", href: "/integrations", icon: Cable, scope: "coordinator" },
  { label: "WhatsApp", href: "/whatsapp", icon: MessageSquare, scope: "coordinator" },
  { label: "Email", href: "/emails", icon: Mail, scope: "coordinator" },
  { label: "Care Agent", href: "/agent", icon: Sparkles, scope: "coordinator" },
  // Self-service portal items
  { label: "My donor portal", href: "/donor", icon: HeartPulse, scope: "donor" },
  { label: "My patient portal", href: "/patient", icon: HeartPulse, scope: "patient" },
  // Admin-only — settings change RBAC / system config
  { label: "Settings", href: "/settings", icon: Settings, scope: "admin" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [role, setRole] = useState<RoleScope | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      const tok = await getIdTokenForRequest();
      if (!alive) return;
      if (!tok) {
        // Local dev without Cognito → show coordinator view by default
        setRole("coordinator");
        return;
      }
      const claims = decodeTokenClaims(tok);
      const groups = claims.groups ?? [];
      const priority: RoleScope[] = ["admin", "coordinator", "donor", "patient"];
      const matched = priority.find((p) => groups.includes(p));
      setRole(matched ?? "coordinator");
    })();
    return () => {
      alive = false;
    };
  }, []);

  function isVisible(item: NavItem): boolean {
    if (!role) return false; // wait for role to load
    const scope = item.scope ?? "any";
    if (scope === "any") return true;
    if (scope === "admin") return role === "admin";
    if (scope === "coordinator") return role === "admin" || role === "coordinator";
    if (scope === "donor") return role === "donor";
    if (scope === "patient") return role === "patient";
    return true;
  }

  const visibleItems = NAV_ITEMS.filter(isVisible);

  return (
    <aside className="hidden h-[calc(100vh-3.5rem)] w-64 shrink-0 flex-col border-r border-white/5 bg-surface/30 backdrop-blur md:flex">
      <div className="px-6 py-5">
        <Link href="/" className="block">
          <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-xl font-bold text-transparent">
            Bridge OS
          </span>
        </Link>
        <p className="mt-1 text-[10px] uppercase tracking-widest text-white/30">
          AlgoWarriors · 2026
        </p>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-4" aria-label="Main">
        {visibleItems.map((item) => {
          const active = pathname === item.href || pathname?.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary/15 text-primary"
                  : "text-white/70 hover:bg-white/5 hover:text-white",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
              <span className="flex-1">{item.label}</span>
              {item.comingSoon ? (
                <span className="text-[10px] uppercase tracking-wider text-white/30">
                  soon
                </span>
              ) : null}
            </Link>
          );
        })}
      </nav>

      <DatasetClockBanner />

      <div className="border-t border-white/5 px-6 py-3">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-white/40">
          <Bell className="h-3 w-3" />
          <span>AI for Good Hackathon</span>
        </div>
      </div>
    </aside>
  );
}
