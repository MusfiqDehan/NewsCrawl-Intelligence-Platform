"use client";

import { useId } from "react";

import { cn } from "@/lib/utils";

type LogoProps = {
  className?: string;
  title?: string;
};

/** News page + radar sweep — crawl + intelligence mark. */
export function Logo({ className, title = "NewsCrawl" }: LogoProps) {
  const gradId = useId().replace(/:/g, "");

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      className={cn("shrink-0", className)}
      role="img"
      aria-label={title}
    >
      <defs>
        <linearGradient
          id={gradId}
          x1="8"
          y1="4"
          x2="56"
          y2="60"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#0369a1" />
          <stop offset="1" stopColor="#0ea5e9" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="14" fill={`url(#${gradId})`} />
      <path
        fill="#f0f9ff"
        d="M15 13h22.5c1.7 0 3 1.3 3 3v4.2L34.3 13H15c-1.7 0-3 1.3-3 3v32c0 1.7 1.3 3 3 3h24c1.7 0 3-1.3 3-3V26.8L46.2 20H48c1.1 0 2 .9 2 2v26c0 2.8-2.2 5-5 5H15c-2.8 0-5-2.2-5-5V16c0-2.8 2.2-5 5-5z"
      />
      <path fill="#7dd3fc" d="M40.5 13v5.5c0 .8.7 1.5 1.5 1.5H48L40.5 13z" />
      <rect x="16" y="24" width="20" height="3.2" rx="1.6" fill="#0284c7" />
      <rect x="16" y="30.5" width="16" height="2.2" rx="1.1" fill="#38bdf8" />
      <rect x="16" y="35.5" width="18" height="2.2" rx="1.1" fill="#38bdf8" />
      <rect x="16" y="40.5" width="12" height="2.2" rx="1.1" fill="#7dd3fc" />
      <circle
        cx="46"
        cy="42"
        r="15"
        fill="none"
        stroke="#e0f2fe"
        strokeWidth="2"
        opacity="0.55"
      />
      <circle
        cx="46"
        cy="42"
        r="9"
        fill="none"
        stroke="#e0f2fe"
        strokeWidth="2"
        opacity="0.8"
      />
      <path
        fill="#ffffff"
        fillOpacity="0.92"
        d="M46 42V27a15 15 0 0 1 13.2 7.8L46 42z"
      />
      <circle cx="46" cy="42" r="3.2" fill="#ffffff" />
    </svg>
  );
}

type BrandProps = {
  className?: string;
  logoClassName?: string;
  showTagline?: boolean;
};

export function Brand({
  className,
  logoClassName = "h-8 w-8",
  showTagline = false,
}: BrandProps) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <Logo className={logoClassName} />
      <span className="min-w-0 leading-tight">
        <span className="block font-[family-name:var(--font-display)] text-sm font-bold tracking-tight text-white">
          NewsCrawl
        </span>
        {showTagline && (
          <span className="block text-xs text-slate-500">
            Intelligence Platform
          </span>
        )}
      </span>
    </span>
  );
}
