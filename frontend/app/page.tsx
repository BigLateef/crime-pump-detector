"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export default function RootPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/scanner" : "/login");
  }, [loading, user, router]);

  return (
    <div className="flex h-screen items-center justify-center bg-base text-ink-muted font-mono text-sm">
      Loading…
    </div>
  );
}
