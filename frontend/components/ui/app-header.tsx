"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Home, LogOut, ShieldCheck, User } from "lucide-react";

import { decodeTokenClaims, getIdTokenForRequest, signOut } from "@/lib/cognito";

/**
 * AppHeader — sticky top bar inside the (app) route group.
 *
 * Left:  Bridge OS brand (links to landing page)
 * Right: Role chip · email · Home button · Sign-out button
 *
 * The user info is read from the cached Cognito ID token, so this works
 * even when the backend is briefly unavailable. If there's no session
 * (e.g. local dev without Cognito), the auth controls render as "Sign in".
 */
export function AppHeader() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      const tok = await getIdTokenForRequest();
      if (!alive || !tok) return;
      const claims = decodeTokenClaims(tok);
      setEmail(claims.email ?? null);
      const groups = claims.groups ?? [];
      // Pick the highest-privilege group as the displayed role
      const priority = ["admin", "coordinator", "donor", "patient"];
      const matched = priority.find((p) => groups.includes(p));
      setRole(matched ?? null);
    })();
    return () => {
      alive = false;
    };
  }, []);

  function handleSignOut() {
    signOut();
    router.push("/");
  }

  return (
    <header
      data-testid="app-header"
      className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-white/5 bg-background/85 px-6 backdrop-blur"
    >
      <Link href="/" className="flex items-center gap-2">
        <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-lg font-bold text-transparent">
          Bridge OS
        </span>
        <span className="hidden text-[10px] uppercase tracking-widest text-white/30 sm:inline">
          dashboard
        </span>
      </Link>

      <div className="flex items-center gap-2">
        {role ? (
          <span
            data-testid="app-header-role"
            className="hidden items-center gap-1 rounded-full border border-accent/20 bg-accent/5 px-2.5 py-0.5 text-[10px] uppercase tracking-wider text-accent sm:inline-flex"
          >
            <ShieldCheck className="h-3 w-3" />
            {role}
          </span>
        ) : null}

        <Link
          href="/"
          data-testid="app-header-home"
          className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-3 py-1.5 text-xs font-medium text-white/80 transition-colors hover:border-white/30 hover:text-white"
          title="Back to the home page"
        >
          <Home className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Home</span>
        </Link>

        {email ? (
          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-xs text-white/80 hover:border-white/30 hover:text-white"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              data-testid="app-header-user"
            >
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-gradient-to-br from-primary to-accent text-[10px] font-bold text-background">
                {email.slice(0, 1).toUpperCase()}
              </span>
              <span className="hidden max-w-[140px] truncate sm:inline">{email}</span>
            </button>
            {menuOpen ? (
              <div
                role="menu"
                className="absolute right-0 top-full mt-2 min-w-[220px] rounded-xl border border-white/10 bg-background/95 p-1.5 text-sm shadow-xl backdrop-blur"
              >
                <div className="px-3 py-2 text-[11px] text-white/50">
                  Signed in as
                  <p className="mt-0.5 truncate text-xs text-white/85">{email}</p>
                </div>
                {role === "donor" ? (
                  <Link
                    href="/donor"
                    role="menuitem"
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-2 rounded-md px-3 py-2 text-xs text-white/80 hover:bg-white/5"
                  >
                    <User className="h-3.5 w-3.5" />
                    My donor portal
                  </Link>
                ) : null}
                {role === "patient" ? (
                  <Link
                    href="/patient"
                    role="menuitem"
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-2 rounded-md px-3 py-2 text-xs text-white/80 hover:bg-white/5"
                  >
                    <User className="h-3.5 w-3.5" />
                    My patient portal
                  </Link>
                ) : null}
                {(role === "admin" || role === "coordinator") ? (
                  <Link
                    href="/settings"
                    role="menuitem"
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-2 rounded-md px-3 py-2 text-xs text-white/80 hover:bg-white/5"
                  >
                    <User className="h-3.5 w-3.5" />
                    Settings
                  </Link>
                ) : null}
                <button
                  type="button"
                  onClick={handleSignOut}
                  role="menuitem"
                  data-testid="app-header-signout"
                  className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-xs text-red-300 hover:bg-red-500/10"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  Sign out
                </button>
              </div>
            ) : null}
          </div>
        ) : (
          <Link
            href="/login"
            className="inline-flex items-center gap-1.5 rounded-full bg-primary/15 px-3 py-1.5 text-xs font-medium text-primary ring-1 ring-primary/30 hover:bg-primary/25"
          >
            Sign in
          </Link>
        )}
      </div>
    </header>
  );
}
