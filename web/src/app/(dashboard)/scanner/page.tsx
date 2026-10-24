import type { Metadata } from "next";
import { Suspense } from "react";

import { ScannerView } from "@/components/scanner/scanner-view";

export const metadata: Metadata = { title: "Stock Scanner" };

export default function ScannerPage() {
  return (
    <Suspense>
      <ScannerView />
    </Suspense>
  );
}
