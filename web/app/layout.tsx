import type { Metadata } from "next";
import { Bricolage_Grotesque, IBM_Plex_Mono, Source_Serif_4 } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const display = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-bricolage", weight: ["600", "700", "800"] });
const body = Source_Serif_4({ subsets: ["latin"], variable: "--font-source-serif" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], variable: "--font-plex-mono", weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "Competitive Research",
  description: "Find your competitors, their pricing and weak spots, with every claim checked against its source.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body>
        <header className="site-header">
          <div className="site-header__inner">
            <Link href="/" className="wordmark">
              Competitive <span>Research</span>
            </Link>
            <span className="mono muted">every claim, sourced</span>
          </div>
        </header>
        <main className="page">{children}</main>
      </body>
    </html>
  );
}
