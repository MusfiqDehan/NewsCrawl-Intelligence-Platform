"use client";

import { Laptop, Moon, Sun } from "lucide-react";

import { type Theme, useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const options: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light theme", icon: Sun },
  { value: "system", label: "Match system theme", icon: Laptop },
  { value: "dark", label: "Dark theme", icon: Moon },
];

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const activeIndex = options.findIndex((o) => o.value === theme);

  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className={cn(
        "relative inline-flex items-center rounded-full border border-slate-200 bg-slate-100 p-1 dark:border-slate-800 dark:bg-slate-900",
        className,
      )}
    >
      <span
        aria-hidden
        className="absolute inset-y-1 left-1 w-8 rounded-full bg-white shadow-sm transition-transform duration-300 ease-out dark:bg-slate-700"
        style={{ transform: `translateX(${Math.max(activeIndex, 0) * 2}rem)` }}
      />
      {options.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={theme === value}
          title={label}
          onClick={() => setTheme(value)}
          className={cn(
            "relative z-10 flex h-8 w-8 items-center justify-center rounded-full transition-colors duration-200",
            theme === value
              ? "text-sky-600 dark:text-sky-400"
              : "text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300",
          )}
        >
          <Icon className="h-4 w-4" strokeWidth={2} />
        </button>
      ))}
    </div>
  );
}
