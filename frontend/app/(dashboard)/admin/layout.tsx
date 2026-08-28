"use client";

import { useAuth } from "@/lib/auth-context";
import { EmptyState } from "@/components/ui/primitives";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }

  if (user?.role !== "admin") {
    return (
      <EmptyState
        title="Admins only"
        body="Your account doesn't have admin access. If you think this is a mistake, ask an existing admin to check your role."
      />
    );
  }

  return <>{children}</>;
}
