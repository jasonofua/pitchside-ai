import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pitchside AI",
  description:
    "Live, explained, personalized match intelligence for fictional football: seven agents, one source of truth.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#06080c",
};

const NAV = [
  { href: "/", label: "Start" },
  { href: "/three/", label: "Three Fans" },
  { href: "/analyst/", label: "Analyst" },
  { href: "/recap/", label: "Recap" },
  { href: "/director/", label: "Director" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="flex items-center gap-4 border-b border-line px-3 py-2 md:gap-6 md:px-6">
          <Link href="/" className="display flex shrink-0 items-center gap-2 whitespace-nowrap text-lg font-bold tracking-wide md:text-xl">
            <span className="inline-block h-3 w-3 rotate-45 bg-accent" aria-hidden />
            PITCHSIDE AI
          </Link>
          <nav className="flex gap-4 overflow-x-auto text-sm text-muted">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className="whitespace-nowrap hover:text-text">
                {n.label}
              </Link>
            ))}
          </nav>
          <span className="ml-auto hidden text-xs text-muted md:block">
            Fictional clubs and players. Synthetic data only.
          </span>
        </header>
        {children}
      </body>
    </html>
  );
}
