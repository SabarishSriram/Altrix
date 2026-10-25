import type { Metadata } from "next";

import { SmartMoneyView } from "@/components/smart-money/smart-money-view";

export const metadata: Metadata = { title: "Smart Money" };

export default function SmartMoneyPage() {
  return <SmartMoneyView />;
}
