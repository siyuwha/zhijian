"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { 
  ArrowUpRight, 
  ArrowDownRight, 
  Activity, 
  Calendar, 
  FileText, 
  Sun, 
  Clock, 
  Radio,
  ShieldCheck,
  RefreshCw
} from "lucide-react";
import { api } from "@/lib/api";
import { IndexData } from "@/types/market";
import { DailyReviewDetail, DailyReviewSummaryItem } from "@/types/report";

export default function Dashboard() {
  const [indices, setIndices] = useState<IndexData[]>([]);
  const [latestReview, setLatestReview] = useState<DailyReviewDetail | null>(null);
  const [reviewSummary, setReviewSummary] = useState<DailyReviewSummaryItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. 获取核心指数实时/收盘数据
      const indexRes = await api.getMarketIndices();
      if (Array.isArray(indexRes)) {
        setIndices(indexRes);
      }

      // 2. 获取最新复盘概要与详情
      const reviewListRes = await api.getDailyReviews(1, 0);
      if (reviewListRes && reviewListRes.items && reviewListRes.items.length > 0) {
        const topSummary = reviewListRes.items[0];
        setReviewSummary(topSummary);
        try {
          const detailRes = await api.getDailyReview(topSummary.date);
          setLatestReview(detailRes);
        } catch {
          // 详情获取失败时仅使用概要
        }
      }

      setLastRefreshed(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
    } catch (err: any) {
      console.error("加载市场总览数据失败:", err);
      setError(err?.message || "数据加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // 提取客观度量指标（安全回退）
  const marketState = latestReview?.market_state;
  const stateLabel = marketState?.state_label || reviewSummary?.state_label || "--";
  const dataQuality = latestReview?.data_quality || reviewSummary?.data_quality || "--";
  const reportDate = latestReview?.date || reviewSummary?.date || "--";

  // 提取广度与连板统计
  const breadthMetrics = marketState?.dimensions?.D2?.metrics || {};
  const upCount = breadthMetrics?.up_count ?? null;
  const downCount = breadthMetrics?.down_count ?? null;

  const sentimentMetrics = marketState?.dimensions?.D3?.metrics || {};
  const maxHeight = sentimentMetrics?.max_board_height ?? null;
  const limitUpCount = sentimentMetrics?.limit_up_count ?? null;
  const limitDownCount = sentimentMetrics?.limit_down_count ?? null;

  const liquidityMetrics = marketState?.dimensions?.D6?.metrics || {};
  const totalAmountYi = liquidityMetrics?.total_amount != null
    ? Math.round(liquidityMetrics.total_amount / 100000000)
    : null;

  return (
    <div className="p-4 md:p-8 space-y-6 max-w-7xl mx-auto">
      {/* 头部标题与刷新信息 */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            <Activity className="w-6 h-6 text-teal-400" />
            A股全天候客观认知与市场事实雷达
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            覆盖盘前推演、开盘竞价、盘中分时与收盘复盘全生命周期的纯客观时间序列测量
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefreshed && (
            <span className="text-xs text-slate-500 font-mono">
              更新于 {lastRefreshed}
            </span>
          )}
          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 transition border border-slate-700 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-950/40 border border-red-800/60 rounded text-xs text-red-300">
          ⚠️ 数据加载提示: {error} (可尝试点击右上角刷新)
        </div>
      )}

      {/* 第一区: 核心指数行情 (真实数据) */}
      <div>
        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
          核心大盘指数快照
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {(indices.length > 0 ? indices : [
            { name: "上证指数", price: null, pct_change: null },
            { name: "深证成指", price: null, pct_change: null },
            { name: "创业板指", price: null, pct_change: null },
            { name: "科创50", price: null, pct_change: null },
          ]).slice(0, 4).map((idx) => {
            const pct = idx.pct_change ?? (idx as any).changePercent ?? null;
            const isUp = pct != null && pct > 0;
            const isDown = pct != null && pct < 0;
            const colorClass = isUp ? "text-red-400" : isDown ? "text-emerald-400" : "text-slate-300";

            return (
              <Card key={idx.name} className="bg-slate-900 border-slate-800 hover:border-slate-700 transition">
                <CardContent className="p-4 flex flex-col justify-between h-full">
                  <div className="text-sm font-medium text-slate-400">{idx.name}</div>
                  <div className="mt-2 text-2xl font-bold font-mono text-slate-100">
                    {idx.price != null ? idx.price.toFixed(2) : "--"}
                  </div>
                  <div className="mt-1 flex items-center text-xs font-mono font-medium">
                    {pct != null ? (
                      <span className={`flex items-center ${colorClass}`}>
                        {isUp ? <ArrowUpRight className="w-3.5 h-3.5 mr-0.5" /> : isDown ? <ArrowDownRight className="w-3.5 h-3.5 mr-0.5" /> : null}
                        {pct > 0 ? `+${pct.toFixed(2)}` : pct.toFixed(2)}%
                      </span>
                    ) : (
                      <span className="text-slate-500">--</span>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {/* 第二区: 市场客观状态与微观生态结构 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 卡片 1: 市场全景客观状态标签 (M1.4 状态向量) */}
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader className="pb-3 border-b border-slate-800/80">
            <div className="flex justify-between items-center">
              <CardTitle className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-teal-400" />
                最新收盘市场客观状态向量
              </CardTitle>
              <span className="text-xs text-slate-500 font-mono">基准日: {reportDate}</span>
            </div>
          </CardHeader>
          <CardContent className="pt-4 space-y-4">
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-slate-700/50">
              <div>
                <div className="text-xs text-slate-400">客观全景状态刻度</div>
                <div className="text-xl font-bold text-teal-300 mt-0.5">{stateLabel}</div>
              </div>
              <div className="text-right">
                <div className="text-xs text-slate-400">数据质量</div>
                <span className="inline-block mt-0.5 px-2 py-0.5 text-xs font-mono rounded bg-slate-700 text-slate-200">
                  {dataQuality}
                </span>
              </div>
            </div>

            <div className="text-xs text-slate-400 leading-relaxed bg-slate-950/40 p-3 rounded border border-slate-800/80">
              💡 <span className="text-slate-300 font-medium">抗标量塌缩与零买卖建议原则</span>：本系统严格废除“单一加权打分”与“做多/做空判断”，D1~D6 全维度保持独立正交测量。
            </div>
          </CardContent>
        </Card>

        {/* 卡片 2: 全市场微观结构与流动性 */}
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader className="pb-3 border-b border-slate-800/80">
            <div className="flex justify-between items-center">
              <CardTitle className="text-sm font-semibold text-slate-200">
                微观广度与连板流动性 (物理事实)
              </CardTitle>
              <span className="text-xs text-slate-500">真实客观测量</span>
            </div>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-slate-800/60 p-3 rounded border border-slate-700/40">
                <div className="text-xs text-slate-400">上涨 / 下跌家数</div>
                <div className="text-lg font-bold font-mono text-slate-200 mt-1">
                  {upCount != null && downCount != null ? (
                    <span>
                      <span className="text-red-400">{upCount}</span>
                      <span className="text-slate-500 mx-1.5">/</span>
                      <span className="text-emerald-400">{downCount}</span>
                    </span>
                  ) : (
                    "--"
                  )}
                </div>
              </div>

              <div className="bg-slate-800/60 p-3 rounded border border-slate-700/40">
                <div className="text-xs text-slate-400">涨停 / 跌停家数</div>
                <div className="text-lg font-bold font-mono text-slate-200 mt-1">
                  {limitUpCount != null ? (
                    <span>
                      <span className="text-red-400">{limitUpCount}</span>
                      <span className="text-slate-500 mx-1.5">/</span>
                      <span className="text-emerald-400">{limitDownCount ?? "--"}</span>
                    </span>
                  ) : (
                    "--"
                  )}
                </div>
              </div>

              <div className="bg-slate-800/60 p-3 rounded border border-slate-700/40">
                <div className="text-xs text-slate-400">最高空间连板</div>
                <div className="text-lg font-bold font-mono text-amber-400 mt-1">
                  {maxHeight != null ? `${maxHeight} 板` : "--"}
                </div>
              </div>

              <div className="bg-slate-800/60 p-3 rounded border border-slate-700/40">
                <div className="text-xs text-slate-400">全天成交总额</div>
                <div className="text-lg font-bold font-mono text-slate-200 mt-1">
                  {totalAmountYi != null ? `${totalAmountYi} 亿元` : "--"}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 第三区: 四大事实雷达全日生命周期快速导航 */}
      <div>
        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
          四大核心事实雷达 (全生命周期协同)
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Link href="/briefing" className="group">
            <Card className="bg-slate-900 border-slate-800 hover:border-amber-500/50 hover:bg-slate-800/50 transition h-full">
              <CardContent className="p-4 flex flex-col justify-between h-full">
                <div>
                  <div className="flex items-center gap-2 text-amber-400 mb-2">
                    <Sun className="w-5 h-5" />
                    <span className="font-semibold text-sm">盘前简报</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    08:00 自动生成 · 隔夜外盘三大股指、富时 A50、大宗商品及早盘观察重点
                  </p>
                </div>
                <div className="mt-4 flex items-center text-xs text-amber-400 font-medium group-hover:underline">
                  查看简报看板 &rarr;
                </div>
              </CardContent>
            </Card>
          </Link>

          <Link href="/auction" className="group">
            <Card className="bg-slate-900 border-slate-800 hover:border-emerald-500/50 hover:bg-slate-800/50 transition h-full">
              <CardContent className="p-4 flex flex-col justify-between h-full">
                <div>
                  <div className="flex items-center gap-2 text-emerald-400 mb-2">
                    <Clock className="w-5 h-5" />
                    <span className="font-semibold text-sm">竞价事实</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    09:26 自动生成 · 09:25 开盘集合竞价总额、竞价量能比与高标开盘承接
                  </p>
                </div>
                <div className="mt-4 flex items-center text-xs text-emerald-400 font-medium group-hover:underline">
                  查看竞价看板 &rarr;
                </div>
              </CardContent>
            </Card>
          </Link>

          <Link href="/monitor" className="group">
            <Card className="bg-slate-900 border-slate-800 hover:border-cyan-500/50 hover:bg-slate-800/50 transition h-full">
              <CardContent className="p-4 flex flex-col justify-between h-full">
                <div>
                  <div className="flex items-center gap-2 text-cyan-400 mb-2">
                    <Radio className="w-5 h-5" />
                    <span className="font-semibold text-sm">盘中动态</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    盘中 60 秒轮询 · 分时走势、量能投影 W(T)、边沿跃迁与系统性共振雷达
                  </p>
                </div>
                <div className="mt-4 flex items-center text-xs text-cyan-400 font-medium group-hover:underline">
                  进入盘中雷达 &rarr;
                </div>
              </CardContent>
            </Card>
          </Link>

          <Link href="/review" className="group">
            <Card className="bg-slate-900 border-slate-800 hover:border-indigo-500/50 hover:bg-slate-800/50 transition h-full">
              <CardContent className="p-4 flex flex-col justify-between h-full">
                <div>
                  <div className="flex items-center gap-2 text-indigo-400 mb-2">
                    <FileText className="w-5 h-5" />
                    <span className="font-semibold text-sm">盘后复盘</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    15:35 自动生成 · 全景六维认知向量 D1~D6、市场广度、连板生态全景归档
                  </p>
                </div>
                <div className="mt-4 flex items-center text-xs text-indigo-400 font-medium group-hover:underline">
                  查看复盘归档 &rarr;
                </div>
              </CardContent>
            </Card>
          </Link>
        </div>
      </div>

      {/* 第四区: 底部法定免责声明 */}
      <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-400 leading-relaxed">
        <span className="text-slate-300 font-semibold">【客观物理事实测量提示】</span>
        本系统所有模块（盘后复盘、盘前简报、竞价事实、盘中动态）仅对市场量价、流动性及衍生数据进行客观时间序列测量与物理结构呈现，绝不提供任何买卖建议、交易信号或主观投资咨询。所有客观度量均需结合投资者个人独立研判。
      </div>
    </div>
  );
}
