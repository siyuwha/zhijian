import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "@/components/layout/Navbar";

export const metadata: Metadata = {
  title: "知见 · AI 认知复盘交易系统",
  description: "AI-driven trading cognition system with Aurora Night UI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh" className="dark">
      <body className="font-sans antialiased bg-[#07090E] text-slate-100 selection:bg-purple-500 selection:text-white min-h-screen flex relative overflow-x-hidden">
        {/* 全局底层弥散流光氛围（固定背景层，不阻挡交互） */}
        <div
          aria-hidden="true"
          className="fixed top-[-10%] left-[-5%] w-[600px] h-[600px] rounded-full bg-purple-600/10 blur-[150px] pointer-events-none -z-10"
        />
        <div
          aria-hidden="true"
          className="fixed bottom-[-10%] right-[-5%] w-[600px] h-[600px] rounded-full bg-cyan-500/08 blur-[160px] pointer-events-none -z-10"
        />

        <Navbar />
        <main className="flex-1 pb-[calc(5rem+env(safe-area-inset-bottom,0px))] md:pb-0 overflow-auto relative z-0">
          {children}
        </main>
      </body>
    </html>
  );
}
