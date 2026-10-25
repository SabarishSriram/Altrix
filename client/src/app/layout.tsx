import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { ThemeProvider } from "@/components/providers/theme-provider";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "Altrix", template: "%s · Altrix" },
  description: "NIFTY 100 stock scanner and EMA crossover strategy research. Historical daily data, not real-time.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // next-themes sets the `dark` class before React hydrates, so <html> differs from the server render.
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="min-h-full bg-background">
        <ThemeProvider>
          <TooltipProvider delayDuration={150}>{children}</TooltipProvider>
          <Toaster position="bottom-right" />
        </ThemeProvider>
      </body>
    </html>
  );
}
