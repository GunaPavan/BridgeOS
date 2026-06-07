"use client";

import { Loader2 } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppHeader } from "@/components/ui/app-header";
import { DemoModeBanner } from "@/components/ui/demo-mode-banner";
import { Sidebar } from "@/components/ui/sidebar";

/**
 * App shell — wraps every route inside the (app) route group with the
 * persistent sidebar nav + a sticky top bar. The DemoModeBanner mounts
 * at the very top so it stays visible across every authenticated page
 * while the scheduler is in demo mode. AppHeader sits below the banner
 * and exposes a Home button (top right) + the signed-in user menu with
 * a sign-out action.
 *
 * Auth gate: every (app)/* route requires a valid Cognito session. The
 * login flow writes the JWT into sessionStorage; if it's missing we
 * bounce to /login with ?next= preserving the original URL so the
 * post-login redirect lands the user back where they were trying to go.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [authState, setAuthState] = useState<"checking" | "ok" | "redirecting">(
    "checking",
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const token = window.sessionStorage.getItem("idToken");
    if (token) {
      setAuthState("ok");
      return;
    }
    setAuthState("redirecting");
    const next = encodeURIComponent(pathname || "/dashboard");
    router.replace(`/login?next=${next}`);
  }, [pathname, router]);

  if (authState !== "ok") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3 text-white/60">
          <Loader2 className="h-6 w-6 animate-spin" />
          <p className="text-sm">
            {authState === "checking"
              ? "Checking session…"
              : "Redirecting to sign in…"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <DemoModeBanner />
      <AppHeader />
      <div className="flex flex-1 min-h-0">
        <Sidebar />
        <main className="flex-1 overflow-x-hidden">{children}</main>
      </div>
    </div>
  );
}
