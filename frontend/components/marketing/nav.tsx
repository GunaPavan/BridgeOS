"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { ArrowRight, Menu, X } from "lucide-react";

import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/about", label: "About" },
];

export function MarketingNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header
      className="sticky top-0 z-40 border-b border-white/5 bg-background/80 backdrop-blur-md"
      data-testid="marketing-nav"
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        <Link href="/" className="group flex items-center gap-2">
          <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-2xl font-bold text-transparent">
            Bridge OS
          </span>
          <span className="hidden text-[10px] uppercase tracking-widest text-white/30 sm:inline">
            by AlgoWarriors
          </span>
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          {NAV_LINKS.map((l) => {
            const active = pathname === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm transition-colors",
                  active
                    ? "text-white"
                    : "text-white/60 hover:text-white",
                )}
              >
                {l.label}
              </Link>
            );
          })}
          <Link
            href="/bridges"
            data-testid="nav-dashboard-cta"
            className="ml-2 inline-flex items-center gap-1.5 rounded-full bg-primary/15 px-4 py-1.5 text-sm font-medium text-primary ring-1 ring-primary/30 transition-colors hover:bg-primary/25"
          >
            Open dashboard
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </nav>

        {/* Mobile menu button */}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="md:hidden inline-flex h-8 w-8 items-center justify-center rounded-md border border-white/10 text-white/70"
          aria-label="Toggle menu"
        >
          {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </button>
      </div>

      {open ? (
        <div className="border-t border-white/5 px-6 py-3 md:hidden">
          {NAV_LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className="block py-2 text-sm text-white/70"
            >
              {l.label}
            </Link>
          ))}
          <Link
            href="/bridges"
            onClick={() => setOpen(false)}
            className="mt-2 block rounded-md bg-primary/15 px-3 py-2 text-center text-sm font-medium text-primary"
          >
            Open dashboard →
          </Link>
        </div>
      ) : null}
    </header>
  );
}
