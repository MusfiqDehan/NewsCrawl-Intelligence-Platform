"use client";

import {
  Activity,
  Globe,
  LayoutDashboard,
  ListTodo,
  LogOut,
  Newspaper,
  Search,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { logoutRemote } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Brand } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";

const links = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/jobs", label: "Crawl Jobs", icon: ListTodo },
  { href: "/sources", label: "Sources", icon: Globe },
  { href: "/articles", label: "Articles", icon: Newspaper },
  { href: "/retention", label: "Deleted Articles", icon: Trash2 },
  { href: "/search", label: "Semantic Search", icon: Search },
  { href: "/system", label: "System", icon: Activity },
];

export function Sidebar({
  mobileOpen = false,
  onNavigate,
}: {
  mobileOpen?: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-50 flex h-screen w-72 shrink-0 flex-col border-r border-slate-200 bg-white transition-transform duration-300 ease-out dark:border-slate-800 dark:bg-slate-950",
        "lg:static lg:z-auto lg:w-60 lg:translate-x-0",
        mobileOpen ? "translate-x-0" : "-translate-x-full",
      )}
    >
      <div className="flex items-center justify-between gap-2 px-5 py-5">
        <Link
          href="/"
          className="flex items-center gap-2 transition-opacity hover:opacity-80"
          onClick={onNavigate}
        >
          <Brand showTagline />
        </Link>
        <button
          onClick={onNavigate}
          aria-label="Close menu"
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-500 dark:hover:bg-slate-900 dark:hover:text-slate-200 lg:hidden"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
        {links.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/dashboard"
              ? pathname === "/dashboard"
              : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              className={cn(
                "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-150",
                active
                  ? "font-medium text-slate-900 dark:text-white"
                  : "text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-200",
              )}
            >
              {active && (
                <span className="nc-scale-in absolute inset-0 rounded-lg bg-slate-100 dark:bg-slate-800" />
              )}
              {active && (
                <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-sky-500" />
              )}
              <Icon
                className={cn(
                  "relative z-10 h-4 w-4 transition-transform duration-150 group-hover:scale-110",
                  active && "text-sky-500",
                )}
              />
              <span className="relative z-10">{label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="space-y-3 border-t border-slate-200 p-3 dark:border-slate-800">
        <div className="flex items-center justify-between px-1">
          <span className="text-xs font-medium text-slate-400 dark:text-slate-500">Theme</span>
          <ThemeToggle />
        </div>
        <button
          onClick={async () => {
            onNavigate?.();
            await logoutRemote();
            router.push("/login");
          }}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-500 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-200"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
