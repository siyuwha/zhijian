import { MonitorPlay } from "lucide-react";

export default function MonitorPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] text-slate-400">
      <MonitorPlay className="w-16 h-16 mb-4 text-teal-400/50" />
      <h2 className="text-2xl font-semibold text-slate-200 mb-2">实时盯盘</h2>
      <p>Coming in Phase 2</p>
    </div>
  );
}
