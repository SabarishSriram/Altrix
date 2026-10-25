import type { Metadata } from "next";

import { StockPicker } from "@/components/stocks/stock-picker";

export const metadata: Metadata = { title: "Stock Analysis" };

export default function StocksPage() {
  return <StockPicker />;
}
