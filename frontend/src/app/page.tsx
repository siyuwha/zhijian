import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowUpRight, ArrowDownRight, Activity } from "lucide-react";

const indexData = [
  { name: "上证指数", price: 3020.15, change: 0.12 },
  { name: "深证成指", price: 9550.62, change: -0.24 },
  { name: "创业板指", price: 1860.33, change: 0.45 },
  { name: "科创50", price: 815.12, change: 1.25 },
];

export default function Dashboard() {
  return (
    <div className="p-4 md:p-8 space-y-6">
      <h2 className="text-2xl font-bold tracking-tight text-white mb-6">市场总览</h2>
      
      {/* Index Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {indexData.map((idx) => {
          const isUp = idx.change >= 0;
          return (
            <Card key={idx.name} className="bg-slate-900 border-slate-800">
              <CardContent className="p-4 flex flex-col justify-between h-full">
                <div className="text-sm text-slate-400">{idx.name}</div>
                <div className="mt-2 text-2xl font-semibold text-slate-100">
                  {idx.price.toFixed(2)}
                </div>
                <div className={`mt-1 flex items-center text-sm ${isUp ? 'text-red-500' : 'text-green-500'}`}>
                  {isUp ? <ArrowUpRight className="w-4 h-4 mr-1" /> : <ArrowDownRight className="w-4 h-4 mr-1" />}
                  {Math.abs(idx.change)}%
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Emotion Gauge Placeholder */}
        <Card className="bg-slate-900 border-slate-800 min-h-[300px]">
          <CardHeader>
            <CardTitle className="text-slate-200">市场情绪温度计</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-center h-[200px]">
            <div className="relative flex flex-col items-center">
              <Activity className="w-16 h-16 text-teal-400 mb-4" />
              <div className="text-4xl font-bold text-teal-400">65°</div>
              <div className="text-sm text-slate-400 mt-2">情绪偏暖</div>
            </div>
          </CardContent>
        </Card>

        {/* Today Summary */}
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <CardTitle className="text-slate-200">今日概况</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-800 p-4 rounded-lg">
                <div className="text-sm text-slate-400">涨跌停比</div>
                <div className="text-xl font-semibold text-slate-200 mt-1">45 / 12</div>
              </div>
              <div className="bg-slate-800 p-4 rounded-lg">
                <div className="text-sm text-slate-400">最高连板</div>
                <div className="text-xl font-semibold text-red-500 mt-1">5板</div>
              </div>
              <div className="bg-slate-800 p-4 rounded-lg col-span-2">
                <div className="text-sm text-slate-400">今日主线</div>
                <div className="text-lg font-medium text-teal-400 mt-1">人工智能 / 算力</div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Latest Reports */}
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <CardTitle className="text-slate-200">最新报告</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <a href="/briefing" className="block p-4 rounded-lg bg-slate-800 hover:bg-slate-700 transition">
              <div className="flex justify-between items-center">
                <span className="font-medium text-slate-200">今日盘前简报</span>
                <span className="text-xs text-slate-400">08:30</span>
              </div>
            </a>
            <a href="/review" className="block p-4 rounded-lg bg-slate-800 hover:bg-slate-700 transition">
              <div className="flex justify-between items-center">
                <span className="font-medium text-slate-200">昨日复盘报告</span>
                <span className="text-xs text-slate-400">昨日 16:00</span>
              </div>
            </a>
          </CardContent>
        </Card>

        {/* Portfolio Summary */}
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <CardTitle className="text-slate-200">持仓及备选</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="p-4 rounded-lg border border-slate-700">
              <div className="text-sm text-slate-400 mb-2">当前仓位</div>
              <div className="text-xl font-semibold text-slate-200">45%</div>
            </div>
            <div className="p-4 rounded-lg border border-slate-700 flex justify-between items-center">
              <div>
                <div className="text-sm text-slate-400">备选池标的</div>
                <div className="text-lg font-semibold text-slate-200">8 只</div>
              </div>
              <a href="/monitor" className="text-teal-400 text-sm hover:underline">去盯盘 &rarr;</a>
            </div>
          </CardContent>
        </Card>

      </div>
    </div>
  );
}
