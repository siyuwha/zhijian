import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "@/components/layout/Navbar";

export const metadata: Metadata = {
  title: "AI 认知复盘交易系统",
  description: "AI-driven trading cognition system",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh">
      <body className="font-sans antialiased bg-slate-950 text-slate-50 min-h-screen flex">
        <Navbar />
        <main className="flex-1 pb-[calc(5rem+env(safe-area-inset-bottom,0px))] md:pb-0 overflow-auto">
          {children}
        </main>
      </body>
    </html>
  );
}
