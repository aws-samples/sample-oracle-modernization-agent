import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Link from "next/link";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "OMA Dashboard",
  description: "Oracle Modernization Agent — Pipeline Dashboard",
};

const navItems = [
  { href: "/", label: "Overview" },
  { href: "/sql", label: "SQL Explorer" },
  { href: "/analysis", label: "FAIL Analysis" },
  { href: "/runs", label: "Run History" },
  { href: "/control", label: "Pipeline" },
  { href: "/settings", label: "Settings" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} dark h-full antialiased`}>
      <body className="min-h-full flex">
        <nav className="w-56 border-r bg-muted/40 p-4 flex flex-col gap-1 shrink-0">
          <h1 className="text-lg font-bold mb-4 px-2">OMA Dashboard</h1>
          {navItems.map(item => (
            <Link
              key={item.href}
              href={item.href}
              className="px-3 py-2 rounded-md text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </body>
    </html>
  );
}
