"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Sidebar, MobileSidebarDrawer } from "@/components/nav/Sidebar";
import { MobileTopBar } from "@/components/nav/MobileTopBar";

function AuthRedirect({ pathname }: { pathname: string }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (loading || user) return;
    const query = searchParams.toString();
    const current = query ? `${pathname}?${query}` : pathname;
    router.replace(`/login?next=${encodeURIComponent(current)}`);
  }, [loading, user, router, pathname, searchParams]);

  return null;
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  // Belt-and-suspenders: also close the drawer on any route change, not
  // just link taps inside it (covers back/forward navigation, redirects,
  // etc. that don't go through the drawer's own onNavigate handler).
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  return (
    <>
      <Suspense fallback={null}>
        <AuthRedirect pathname={pathname} />
      </Suspense>
      {loading || !user ? (
        <div className="flex h-screen items-center justify-center bg-base font-mono text-sm text-ink-muted">
          Loading…
        </div>
      ) : (
        <div className="flex h-screen flex-col bg-base md:flex-row">
          <Sidebar />
          <MobileSidebarDrawer open={menuOpen} onClose={() => setMenuOpen(false)} />
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <MobileTopBar onOpenMenu={() => setMenuOpen(true)} />
            <main className="flex-1 overflow-y-auto overflow-x-hidden p-3 md:p-6">{children}</main>
          </div>
        </div>
      )}
    </>
  );
}
