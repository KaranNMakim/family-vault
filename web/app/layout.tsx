import type { Metadata, Viewport } from "next";

import { DemoBanner } from "@/components/ui";
import { SessionProvider } from "@/lib/session";

import "./globals.css";

export const metadata: Metadata = {
  title: "family-vault",
  description: "Know where everything is, before you need to. A demo with synthetic data.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN">
      <body className="min-h-screen">
        <DemoBanner />
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
