import { Suspense } from "react";

import { AccessGuard } from "@/components/layout/access-guard";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { ScannerProvider } from "@/components/providers/scanner-provider";

// The sidebar and top bar read the URL (active page), so they stream in
// inside Suspense; their fallbacks keep the layout from shifting.
// AccessGuard sends a tab that hasn't entered the access code to /unlock.
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AccessGuard>
      <ScannerProvider>
        <div className="flex min-h-svh">
          <Suspense fallback={<div className="hidden w-56 shrink-0 border-r lg:block" />}>
            <Sidebar />
          </Suspense>
          <div className="flex min-w-0 flex-1 flex-col">
            <Suspense fallback={<div className="h-[57px] border-b" />}>
              <Topbar />
            </Suspense>
            <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-5 sm:px-6 sm:py-6">{children}</main>
          </div>
        </div>
      </ScannerProvider>
    </AccessGuard>
  );
}
