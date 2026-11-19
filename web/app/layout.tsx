import type { Metadata } from "next";
import { Geist, Geist_Mono, Unbounded } from "next/font/google";
import Link from "next/link";
import Logo from "@/components/Logo";
import "./globals.css";

const display = Unbounded({ subsets: ["latin"], variable: "--font-unbounded", weight: ["400", "500", "600"] });
const body = Geist({ subsets: ["latin"], variable: "--font-geist" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });

export const metadata: Metadata = {
  title: "Competitive Research",
  description: "Find your competitors, their pricing and weak spots, with every claim checked against its source.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`} suppressHydrationWarning>
      <body>
        <header className="site-header">
          <div className="site-header__inner">
            <Link href="/" className="wordmark">
              <Logo />
              Competitive Research
            </Link>
            <span className="chip">
              <span className="dot dot--succeeded" /> Source-verified
            </span>
          </div>
        </header>
        <main className="page">{children}</main>
      </body>
    </html>
  );
}
