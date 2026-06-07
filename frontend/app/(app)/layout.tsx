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
