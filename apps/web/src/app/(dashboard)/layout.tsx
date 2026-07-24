"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Sidebar } from "@/components/sidebar";
import { bootstrapSessionRefresh, getToken, subscribeToAuth } from "@/lib/api";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  // Wait until the client has mounted before trusting localStorage / redirecting.
  // Prerender + hydration start with a null server snapshot; redirecting on that
  // null value was logging users out on every dashboard reload.
  const [ready, setReady] = useState(false);
  const token = useSyncExternalStore(subscribeToAuth, getToken, () => null);

  useEffect(() => {
    setReady(true);
    bootstrapSessionRefresh();
  }, []);

  useEffect(() => {
    if (!ready) return;
    if (token === null) router.replace("/login");
  }, [ready, token, router]);

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950 text-sm text-slate-500">
        Restoring session…
      </div>
    );
  }

  if (!token) return null;

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">{children}</main>
    </div>
  );
}
