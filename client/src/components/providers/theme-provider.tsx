"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

/** Light / dark / system theme, stored per browser. Adds the `dark` class to <html>. */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      {children}
    </NextThemesProvider>
  );
}
