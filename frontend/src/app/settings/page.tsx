import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, XCircle } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto space-y-6">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-white">系统设置</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <CardTitle className="text-slate-200">数据源状态</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center p-3 bg-slate-800 rounded-lg">
              <span className="text-slate-300">同花顺 API</span>
              <div className="flex items-center text-green-400 text-sm">
                <CheckCircle2 className="w-4 h-4 mr-1" /> 已连接
              </div>
            </div>
            <div className="flex justify-between items-center p-3 bg-slate-800 rounded-lg">
              <span className="text-slate-300">东方财富数据</span>
              <div className="flex items-center text-green-400 text-sm">
                <CheckCircle2 className="w-4 h-4 mr-1" /> 已连接
              </div>
            </div>
            <div className="flex justify-between items-center p-3 bg-slate-800 rounded-lg">
              <span className="text-slate-300">新闻资讯爬虫</span>
              <div className="flex items-center text-red-400 text-sm">
                <XCircle className="w-4 h-4 mr-1" /> 异常
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <CardTitle className="text-slate-200">定时任务状态</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center p-3 bg-slate-800 rounded-lg">
              <div>
                <div className="text-slate-300">盘后复盘生成</div>
                <div className="text-xs text-slate-500">每天 16:00</div>
              </div>
              <span className="px-2 py-1 text-xs rounded bg-green-500/20 text-green-400">运行中</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-slate-800 rounded-lg">
              <div>
                <div className="text-slate-300">盘前简报生成</div>
                <div className="text-xs text-slate-500">每天 08:30</div>
              </div>
              <span className="px-2 py-1 text-xs rounded bg-green-500/20 text-green-400">运行中</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
