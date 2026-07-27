import { AlertTriangle, Inbox } from "lucide-react";

import { cn } from "@/lib/utils";

export function Card({
  className,
  interactive = false,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-slate-200 bg-white/80 p-5 shadow-sm shadow-slate-200/60 backdrop-blur-sm transition-all duration-200",
        "dark:border-slate-800 dark:bg-slate-900/60 dark:shadow-none",
        interactive &&
          "hover:-translate-y-0.5 hover:border-sky-300 hover:shadow-md hover:shadow-sky-900/5 dark:hover:border-slate-700 dark:hover:shadow-black/20",
        className,
      )}
      {...props}
    />
  );
}

export function CardTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn(
        "mb-3 text-sm font-medium text-slate-500 dark:text-slate-400",
        className,
      )}
      {...props}
    />
  );
}

const badgeStyles: Record<string, string> = {
  green:
    "bg-emerald-500/10 text-emerald-600 ring-emerald-500/20 dark:bg-emerald-500/15 dark:text-emerald-400 dark:ring-emerald-500/30",
  red: "bg-rose-500/10 text-rose-600 ring-rose-500/20 dark:bg-rose-500/15 dark:text-rose-400 dark:ring-rose-500/30",
  yellow:
    "bg-amber-500/10 text-amber-600 ring-amber-500/20 dark:bg-amber-500/15 dark:text-amber-400 dark:ring-amber-500/30",
  blue: "bg-sky-500/10 text-sky-600 ring-sky-500/20 dark:bg-sky-500/15 dark:text-sky-400 dark:ring-sky-500/30",
  gray: "bg-slate-500/10 text-slate-600 ring-slate-500/20 dark:bg-slate-500/15 dark:text-slate-400 dark:ring-slate-500/30",
  purple:
    "bg-violet-500/10 text-violet-600 ring-violet-500/20 dark:bg-violet-500/15 dark:text-violet-400 dark:ring-violet-500/30",
};

const dotStyles: Record<string, string> = {
  green: "bg-emerald-500",
  red: "bg-rose-500",
  yellow: "bg-amber-500",
  blue: "bg-sky-500",
  gray: "bg-slate-500",
  purple: "bg-violet-500",
};

export function Badge({
  color = "gray",
  dot = false,
  pulse = false,
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & {
  color?: keyof typeof badgeStyles;
  dot?: boolean;
  pulse?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset transition-colors",
        badgeStyles[color],
        className,
      )}
      {...props}
    >
      {dot && (
        <span className="relative flex h-1.5 w-1.5">
          {pulse && (
            <span
              className={cn(
                "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75",
                dotStyles[color],
              )}
            />
          )}
          <span
            className={cn("relative inline-flex h-1.5 w-1.5 rounded-full", dotStyles[color])}
          />
        </span>
      )}
      {props.children}
    </span>
  );
}

const statusColor: Record<string, keyof typeof badgeStyles> = {
  running: "blue",
  queued: "yellow",
  created: "gray",
  paused: "yellow",
  completed: "green",
  failed: "red",
  cancelled: "gray",
  success: "green",
  retry_pending: "yellow",
  blocked: "red",
  bn: "purple",
  en: "blue",
};

const livelyStatuses = new Set(["running", "queued", "retry_pending"]);

export function StatusBadge({ status }: { status: string }) {
  const color = statusColor[status] ?? "gray";
  return (
    <Badge color={color} dot pulse={livelyStatuses.has(status)}>
      {status}
    </Badge>
  );
}

export function Button({
  className,
  variant = "default",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "outline" | "danger" | "ghost";
}) {
  const variants = {
    default:
      "bg-sky-600 text-white shadow-sm shadow-sky-600/20 hover:bg-sky-500 hover:shadow-md hover:shadow-sky-600/25",
    outline:
      "border border-slate-300 text-slate-600 hover:border-slate-400 hover:bg-slate-100 hover:text-slate-900 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-800 dark:hover:text-white",
    danger:
      "bg-rose-600/90 text-white shadow-sm shadow-rose-600/20 hover:bg-rose-500 hover:shadow-md hover:shadow-rose-600/25",
    ghost:
      "text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white",
  };
  return (
    <button
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/50 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--nc-ink)]",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900 placeholder:text-slate-400 transition-colors duration-150",
        "focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20",
        "dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:placeholder:text-slate-500",
        className,
      )}
      {...props}
    />
  );
}

export function Select({
  className,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900 transition-colors duration-150",
        "focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20",
        "dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200",
        className,
      )}
      {...props}
    />
  );
}

export function Table({
  className,
  ...props
}: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
      <table className={cn("w-full text-left text-sm", className)} {...props} />
    </div>
  );
}

export function Th({
  className,
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "border-b border-slate-200 bg-slate-50 px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-slate-500",
        "dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-500",
        className,
      )}
      {...props}
    />
  );
}

export function Td({
  className,
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={cn(
        "border-b border-slate-100 px-4 py-2.5 text-slate-700 dark:border-slate-800/60 dark:text-slate-300",
        className,
      )}
      {...props}
    />
  );
}

export function Tr({
  className,
  ...props
}: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn(
        "transition-colors duration-150 hover:bg-slate-50 dark:hover:bg-slate-900/50",
        className,
      )}
      {...props}
    />
  );
}

export function Spinner() {
  return (
    <div className="flex justify-center py-12">
      <div className="relative h-8 w-8">
        <div className="absolute inset-0 animate-spin rounded-full border-2 border-slate-200 border-t-sky-500 dark:border-slate-700 dark:border-t-sky-400" />
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("nc-skeleton rounded-lg", className)} />;
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="nc-fade-in flex flex-col items-center gap-2 py-12 text-center text-sm text-slate-500 dark:text-slate-500">
      <Inbox className="h-6 w-6 text-slate-300 dark:text-slate-700" strokeWidth={1.5} />
      {message}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="nc-fade-in flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-400">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      {message}
    </div>
  );
}
