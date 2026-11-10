"use client";

import { usePathname } from "next/navigation";
import { AuthProvider } from "@/lib/auth-context";
import { Sidebar } from "@/components/sidebar";
import { MobileNav } from "@/components/mobile-nav";

const BARE_ROUTES = ["/login", "/signup"];

export function ClientShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <AuthProvider>
      {BARE_ROUTES.includes(pathname) ? (
        children
      ) : (
        <>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-y-auto pb-16 md:pb-0">
              <div className="mx-auto max-w-7xl p-4 md:p-6">{children}</div>
            </main>
          </div>
          <MobileNav />
        </>
      )}
    </AuthProvider>
  );
}
