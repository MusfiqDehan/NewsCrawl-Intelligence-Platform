"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

import { Brand } from "@/components/logo";
import { getToken, subscribeToAuth } from "@/lib/api";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/explore", label: "Search", exact: true },
  { href: "/explore/articles", label: "Browse", exact: false },
];

export default function ExploreLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const token = useSyncExternalStore(subscribeToAuth, getToken, () => null);

  return (
    <div className="min-h-screen bg-[var(--nc-ink)] text-slate-200">
      <header className="border-b border-slate-900 bg-[var(--nc-panel)]/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-6">
            <Link href="/">
              <Brand logoClassName="h-8 w-8" />
            </Link>
            <nav className="flex items-center gap-1 text-sm">
              {nav.map(({ href, label, exact }) => {
                const active = exact
                  ? pathname === href
                  : pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn(
                      "rounded-lg px-3 py-1.5 transition",
                      active
                        ? "bg-slate-800 text-white"
                        : "text-slate-400 hover:text-white",
                    )}
                  >
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-2 text-sm">
            {token ? (
              <Link
                href="/dashboard"
                className="rounded-lg bg-sky-600 px-3 py-1.5 font-medium text-white hover:bg-sky-500"
              >
                Dashboard
              </Link>
            ) : (
              <Link
                href="/login"
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-slate-300 hover:border-slate-500 hover:text-white"
              >
                Sign in
              </Link>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl px-6 py-8">{children}</main>
    </div>
  );
}
