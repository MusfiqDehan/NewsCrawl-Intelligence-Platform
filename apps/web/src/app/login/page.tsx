"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Card, ErrorState, Input } from "@/components/ui";
import { Logo } from "@/components/logo";
import { api, getToken, setSession } from "@/lib/api";
import type { TokenResponse } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (getToken()) router.replace("/dashboard");
  }, [router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const token = await api<TokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
        skipAuth: true,
      });
      setSession(token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(14,165,233,0.18),_transparent_55%),linear-gradient(180deg,#020617_0%,#0f172a_100%)]"
      />
      <Card className="relative z-10 w-full max-w-sm">
        <div className="mb-6 text-center">
          <Link href="/" className="mx-auto mb-3 inline-flex">
            <Logo className="h-12 w-12" />
          </Link>
          <h1 className="font-[family-name:var(--font-display)] text-lg font-semibold text-white">
            NewsCrawl
          </h1>
          <p className="text-sm text-slate-500">Sign in to the operations dashboard</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4">
          <Input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full"
          />
          <Input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full"
          />
          {error && <ErrorState message={error} />}
          <Button type="submit" disabled={loading} className="w-full justify-center">
            {loading ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="mt-4 text-center text-xs text-slate-500">
          <Link href="/" className="text-sky-400 hover:text-sky-300">
            ← Back to home
          </Link>
        </p>
      </Card>
    </div>
  );
}
