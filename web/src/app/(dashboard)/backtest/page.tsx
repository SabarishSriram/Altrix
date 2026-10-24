import type { Metadata } from "next";

import { BacktestView } from "@/components/backtest/backtest-view";

export const metadata: Metadata = { title: "Backtesting" };

export default function BacktestPage() {
  return <BacktestView />;
}
