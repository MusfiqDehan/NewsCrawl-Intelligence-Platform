"use client";

import { Menu } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Brand } from "@/components/logo";
import { Sidebar } from "@/components/sidebar";
import { bootstrapSessionRefresh, getToken, subscribeToAuth } from "@/lib/api";

const noopSubscribe = () => () => {};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  // Wait until the client has mounted before trusting localStorage / redirecting.
  // Prerender + hydration start with a null server snapshot; redirecting on that
  // null value was logging users out on every dashboard reload. useSyncExternalStore's
  // distinct server/client snapshots make this reveal hydration-safe without an effect.
  const ready = useSyncExternalStore(noopSubscribe, () => true, () => false);
  const token = useSyncExternalStore(subscribeToAuth, getToken, () => null);

  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  // Close the mobile drawer whenever the route changes, adjusted during render
  // (React's sanctioned pattern) rather than via an effect.
  const [lastPathname, setLastPathname] = useState(pathname);
  if (pathname !== lastPathname) {
    setLastPathname(pathname);
    setMobileNavOpen(false);
  }

  useEffect(() => {
    bootstrapSessionRefresh();
  }, []);

  useEffect(() => {
    if (!ready) return;
    if (token === null) router.replace("/login");
  }, [ready, token, router]);

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center bg-white text-sm text-slate-500 dark:bg-slate-950 dark:text-slate-500">
        Restoring session…
      </div>
    );
  }

  if (!token) return null;

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 dark:bg-slate-950">
      {mobileNavOpen && (
        <div
          aria-hidden
          onClick={() => setMobileNavOpen(false)}
          className="fixed inset-0 z-40 bg-slate-950/50 lg:hidden"
        />
      )}
      <Sidebar mobileOpen={mobileNavOpen} onNavigate={() => setMobileNavOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950 lg:hidden">
          <button
            onClick={() => setMobileNavOpen(true)}
            aria-label="Open menu"
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-200"
          >
            <Menu className="h-5 w-5" />
          </button>
          <Brand logoClassName="h-7 w-7" />
        </header>
        <main
          key={pathname}
          className="nc-fade-in flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
