import type { Metadata } from "next";

import { UnlockScreen } from "@/components/unlock/unlock-screen";

export const metadata: Metadata = { title: "Unlock" };

export default function UnlockPage() {
  return <UnlockScreen />;
}
