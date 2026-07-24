"use client";

import {
  Activity,
  Globe,
  LayoutDashboard,
  ListTodo,
  LogOut,
  Newspaper,
  Search,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { logoutRemote } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Brand } from "@/components/logo";

const links = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/jobs", label: "Crawl Jobs", icon: ListTodo },
  { href: "/sources", label: "Sources", icon: Globe },
  { href: "/articles", label: "Articles", icon: Newspaper },
  { href: "/search", label: "Semantic Search", icon: Search },
  { href: "/system", label: "System", icon: Activity },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-slate-800 bg-slate-950">
      <div className="flex items-center gap-2 px-5 py-5">
        <Link href="/" className="flex items-center gap-2">
          <Brand showTagline />
        </Link>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-2">
        {links.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/dashboard"
              ? pathname === "/dashboard"
              : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-slate-800 font-medium text-white"
                  : "text-slate-400 hover:bg-slate-900 hover:text-slate-200",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-slate-800 p-3">
        <button
          onClick={async () => {
            await logoutRemote();
            router.push("/login");
          }}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-slate-900 hover:text-slate-200"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
