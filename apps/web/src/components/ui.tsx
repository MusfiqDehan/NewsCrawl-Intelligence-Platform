import { cn } from "@/lib/utils";

export function Card({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-sm",
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
      className={cn("mb-3 text-sm font-medium text-slate-400", className)}
      {...props}
    />
  );
}

const badgeStyles: Record<string, string> = {
  green: "bg-emerald-500/15 text-emerald-400 ring-emerald-500/30",
  red: "bg-rose-500/15 text-rose-400 ring-rose-500/30",
  yellow: "bg-amber-500/15 text-amber-400 ring-amber-500/30",
  blue: "bg-sky-500/15 text-sky-400 ring-sky-500/30",
  gray: "bg-slate-500/15 text-slate-400 ring-slate-500/30",
  purple: "bg-violet-500/15 text-violet-400 ring-violet-500/30",
};

export function Badge({
  color = "gray",
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { color?: keyof typeof badgeStyles }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        badgeStyles[color],
        className,
      )}
      {...props}
    />
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

export function StatusBadge({ status }: { status: string }) {
  return <Badge color={statusColor[status] ?? "gray"}>{status}</Badge>;
}

export function Button({
  className,
  variant = "default",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "outline" | "danger" | "ghost";
}) {
  const variants = {
    default: "bg-sky-600 text-white hover:bg-sky-500",
    outline:
      "border border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-white",
    danger: "bg-rose-600/80 text-white hover:bg-rose-500",
    ghost: "text-slate-400 hover:bg-slate-800 hover:text-white",
  };
  return (
    <button
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
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
        "rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none",
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
        "rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:border-sky-500 focus:outline-none",
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
    <div className="overflow-x-auto rounded-xl border border-slate-800">
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
        "border-b border-slate-800 bg-slate-900/80 px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-slate-500",
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
      className={cn("border-b border-slate-800/60 px-4 py-2.5 text-slate-300", className)}
      {...props}
    />
  );
}

export function Spinner() {
  return (
    <div className="flex justify-center py-12">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-600 border-t-sky-500" />
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="py-12 text-center text-sm text-slate-500">{message}</div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-rose-900/50 bg-rose-950/30 px-4 py-3 text-sm text-rose-400">
      {message}
    </div>
  );
}
