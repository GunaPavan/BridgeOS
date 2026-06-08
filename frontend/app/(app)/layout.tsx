import { AppHeader } from "@/components/ui/app-header";
import { DemoModeBanner } from "@/components/ui/demo-mode-banner";
import { Sidebar } from "@/components/ui/sidebar";

/**
 * App shell — wraps every route inside the (app) route group with the
 * persistent sidebar nav + a sticky top bar. The DemoModeBanner mounts
 * at the very top so it stays visible across every page while the
 * scheduler is in demo mode. AppHeader sits below the banner and exposes
 * a Home button (top right) + the signed-in user menu when authenticated.
 *
 * The dashboard is open for local browsing — there's no client-side
 * Cognito gate here. The production deployment fronted this shell with
 * Cognito + JWT auth (see `frontend/app/login/page.tsx` for the sign-in
 * flow); for self-host / portfolio use the shell renders directly so
 * anyone cloning the repo can explore every page without configuring
 * a user pool.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
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
