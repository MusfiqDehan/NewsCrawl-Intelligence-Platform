"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

import { Brand } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
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
    <div className="min-h-screen bg-[var(--nc-ink)] text-slate-700 dark:text-slate-200">
      <header className="border-b border-slate-200 bg-[var(--nc-panel)]/80 backdrop-blur dark:border-slate-900">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3 sm:px-6 sm:py-4">
          <div className="flex items-center gap-3 sm:gap-6">
            <Link href="/">
              <Brand logoClassName="h-7 w-7 sm:h-8 sm:w-8" />
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
                      "rounded-lg px-2.5 py-1.5 transition sm:px-3",
                      active
                        ? "bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-white"
                        : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white",
                    )}
                  >
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <ThemeToggle />
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
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-slate-700 hover:border-slate-400 hover:text-slate-900 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-500 dark:hover:text-white"
              >
                Sign in
              </Link>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 sm:py-8">{children}</main>
    </div>
  );
}
