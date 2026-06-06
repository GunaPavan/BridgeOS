"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bell,
  Cable,
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

interface NavItem {
  label: string;
  href: string;
  icon: typeof LayoutDashboard;
  comingSoon?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { label: "Bridges", href: "/bridges", icon: Network },
  { label: "Donors", href: "/donors", icon: Users },
  { label: "Patients", href: "/patients", icon: UserCircle2 },
  { label: "Recommendations", href: "/recommendations", icon: Inbox },
  { label: "Outreach", href: "/outreach", icon: Zap },
  { label: "Automation", href: "/system/scheduler", icon: Activity },
  { label: "Simulator", href: "/simulator", icon: Play },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
  { label: "Integrations", href: "/integrations", icon: Cable },
  { label: "WhatsApp", href: "/whatsapp", icon: MessageSquare },
  { label: "Email", href: "/emails", icon: Mail },
  { label: "Care Agent", href: "/agent", icon: Sparkles },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden h-screen w-64 shrink-0 flex-col border-r border-white/5 bg-surface/30 backdrop-blur md:flex">
      <div className="px-6 py-6">
        <Link href="/" className="block">
          <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-2xl font-bold text-transparent">
            Bridge OS
          </span>
        </Link>
        <p className="mt-1 text-xs text-white/40">AlgoWarriors · 2026</p>
      </div>

      <nav className="flex-1 space-y-0.5 px-3" aria-label="Main">
        {NAV_ITEMS.map((item) => {
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

      <div className="border-t border-white/5 px-6 py-4">
        <div className="flex items-center gap-2 text-xs text-white/40">
          <Bell className="h-3.5 w-3.5" />
          <span>AI for Good Hackathon</span>
        </div>
      </div>
    </aside>
  );
}
