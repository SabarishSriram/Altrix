import type { Metadata } from "next";

import { InvestmentsView } from "@/components/investments/investments-view";

export const metadata: Metadata = { title: "Investments" };

export default function InvestmentsPage() {
  return <InvestmentsView />;
}
