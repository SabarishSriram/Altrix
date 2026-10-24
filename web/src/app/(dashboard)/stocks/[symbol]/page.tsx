import type { Metadata } from "next";
import { Suspense } from "react";

import { StockDetail } from "@/components/stocks/stock-detail";

export const metadata: Metadata = { title: "Stock Analysis" };

export default function StockPage() {
  return (
    <Suspense>
      <StockDetail />
    </Suspense>
  );
}
