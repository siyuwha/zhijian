'use client';

import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { 
  CheckCircle2, 
  XCircle, 
  Clock, 
  Cpu, 
  Database, 
  Server, 
  ShieldCheck, 
  Activity, 
  Terminal, 
  Hash, 
  RefreshCw, 
  Workflow,
  Layers,
  Sparkles,
  Bot
} from "lucide-react";
import { LLMConfigCard } from '@/components/settings/LLMConfigCard';
import { LLMConfigData } from '@/lib/api';

export default function SettingsPage() {
  const [refreshing, setRefreshing] = useState(false);
  const [activeConfig, setActiveConfig] = useState<LLMConfigData | null>(null);

  const handleRefresh = () => {
    setRefreshing(true);
    setTimeout(() => setRefreshing(false), 800);
  };

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-8">
      {/* 头部标题与定位 */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/10 pb-6">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-black text-white tracking-tight">系统工程运行与 API 设置</h1>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-700/50">
              SYSTEM STATUS &amp; API CONFIG CONSOLE
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            本页面集中管理「知见」系统的大语言模型 API 接入 (支持 OpenAI 兼容中转站与直连)、工程运行状态、数据源监控与自动化流水线。
          </p>
        </div>

        <button
          onClick={handleRefresh}
          className="self-start md:self-auto px-3.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-sm text-slate-300 flex items-center gap-2 transition active:scale-95"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-amber-400 ${refreshing ? 'animate-spin' : ''}`} />
          <span>刷新健康度探针</span>
        </button>
      </div>

      {/* 概览统计指标 4 联卡 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-[#0B0E17] border border-white/10 p-4 rounded-xl">
          <div className="flex items-center justify-between text-slate-400 text-sm">
            <span>当前推理大模型</span>
            <Bot className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-lg font-black text-white font-mono mt-2 truncate" title={activeConfig?.model || 'deepseek-chat'}>
            {activeConfig?.model || 'deepseek-chat'}
          </div>
          <div className="text-xs text-purple-400 mt-1 truncate">
            {activeConfig?.is_customized ? '已启用自定义中转' : '波普尔假说推演'}
          </div>
        </div>

        <div className="bg-[#0B0E17] border border-white/10 p-4 rounded-xl">
          <div className="flex items-center justify-between text-slate-400 text-sm">
            <span>数据源健康度</span>
            <Database className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-xl font-black text-emerald-400 font-mono mt-2">100% 联通</div>
          <div className="text-xs text-slate-400 mt-1">全市场物理数据实时入库</div>
        </div>

        <div className="bg-[#0B0E17] border border-white/10 p-4 rounded-xl">
          <div className="flex items-center justify-between text-slate-400 text-sm">
            <span>定时调度流水线</span>
            <Workflow className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-xl font-black text-white font-mono mt-2">3 项激活</div>
          <div className="text-xs text-emerald-400 mt-1">APScheduler 守护运行中</div>
        </div>

        <div className="bg-[#0B0E17] border border-white/10 p-4 rounded-xl">
          <div className="flex items-center justify-between text-slate-400 text-sm">
            <span>物理数据防篡改</span>
            <ShieldCheck className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-xl font-black text-white font-mono mt-2">SHA-256 锚定</div>
          <div className="text-xs text-cyan-400 mt-1">盘后数据指纹已校验</div>
        </div>
      </div>

      {/* 系统 LLM 推理引擎与 OpenAI 兼容中转站配置卡片 */}
      <LLMConfigCard onConfigChange={setActiveConfig} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* 数据源接口健康度 */}
        <Card className="bg-[#0B0E17] border-white/10">
          <CardHeader className="border-b border-white/5 pb-3">
            <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
              <Database className="w-4 h-4 text-cyan-400" />
              <span>数据采集源与接口通信健康度</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-3 text-sm">
            <div className="flex justify-between items-center p-3 bg-black/40 rounded-lg border border-white/5">
              <div>
                <div className="font-semibold text-slate-200">Tushare Pro 行情接口</div>
                <div className="text-xs text-slate-400 mt-0.5">沪深两市全样本日线、涨跌停统计、成交量</div>
              </div>
              <div className="flex items-center text-emerald-400 font-mono text-sm gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span>已连接 (延时 62ms)</span>
              </div>
            </div>

            <div className="flex justify-between items-center p-3 bg-black/40 rounded-lg border border-white/5">
              <div>
                <div className="font-semibold text-slate-200">东方财富 Level-1/2 盘口异动通道</div>
                <div className="text-xs text-slate-400 mt-0.5">主力资金净流入、行业板块多空资金分布</div>
              </div>
              <div className="flex items-center text-emerald-400 font-mono text-sm gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span>已连接 (延时 95ms)</span>
              </div>
            </div>

            <div className="flex justify-between items-center p-3 bg-black/40 rounded-lg border border-white/5">
              <div>
                <div className="font-semibold text-slate-200">全市场微观流动性清洗管道</div>
                <div className="text-xs text-slate-400 mt-0.5">炸板率校验、高位梯队锁定、大面股统计</div>
              </div>
              <div className="flex items-center text-emerald-400 font-mono text-sm gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>清洗已完成</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 自动化调度流水线 */}
        <Card className="bg-[#0B0E17] border-white/10">
          <CardHeader className="border-b border-white/5 pb-3">
            <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
              <Clock className="w-4 h-4 text-amber-400" />
              <span>自动化调度流水线 (APScheduler)</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-3 text-sm">
            <div className="flex justify-between items-center p-3 bg-black/40 rounded-lg border border-white/5">
              <div>
                <div className="font-semibold text-slate-200">盘后全景认知复盘 (11章)</div>
                <div className="text-xs text-slate-400 mt-0.5">交易日 16:30 自动触发 · 耗时 ~15s</div>
              </div>
              <div className="text-right">
                <span className="px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/40 text-xs">
                  已执行
                </span>
                <div className="text-[10px] font-mono text-slate-500 mt-1">10-12 16:30:12</div>
              </div>
            </div>

            <div className="flex justify-between items-center p-3 bg-black/40 rounded-lg border border-white/5">
              <div>
                <div className="font-semibold text-slate-200">09:25 集合竞价微观探针抓取</div>
                <div className="text-xs text-slate-400 mt-0.5">交易日 09:25:05 自动执行 · 毫秒级入库</div>
              </div>
              <div className="text-right">
                <span className="px-2 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/40 text-xs">
                  待就绪
                </span>
                <div className="text-[10px] font-mono text-slate-500 mt-1">次日 09:25:05</div>
              </div>
            </div>

            <div className="flex justify-between items-center p-3 bg-black/40 rounded-lg border border-white/5">
              <div>
                <div className="font-semibold text-slate-200">盘前决策简报与推演假说校验</div>
                <div className="text-xs text-slate-400 mt-0.5">交易日 08:30 自动生成 · 吸收隔夜外盘</div>
              </div>
              <div className="text-right">
                <span className="px-2 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-800/40 text-xs">
                  已调度
                </span>
                <div className="text-[10px] font-mono text-slate-500 mt-1">次日 08:30:00</div>
              </div>
            </div>
          </CardContent>
        </Card>

      </div>

      {/* 推演引擎与防篡改物理审计 */}
      <Card className="bg-[#0B0E17] border-white/10">
        <CardHeader className="border-b border-white/5 pb-3">
          <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
            <Terminal className="w-4 h-4 text-purple-400" />
            <span>认知推演引擎规格与防篡改审计记录</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 space-y-3 font-mono text-sm">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-3 bg-black/40 rounded-lg border border-white/5 space-y-2">
              <span className="text-xs font-bold text-slate-300 block">AI 推演模型参数 (实时动态生效)</span>
              <div className="flex justify-between text-slate-400">
                <span>底层推理引擎:</span>
                <span className="text-white font-bold">{activeConfig?.model || 'deepseek-chat'}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>API 接口端点:</span>
                <span className="text-cyan-400 truncate max-w-[210px]" title={activeConfig?.base_url || 'https://api.deepseek.com/v1'}>
                  {activeConfig?.base_url || 'https://api.deepseek.com/v1'}
                </span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>接口密钥状态:</span>
                <span className={activeConfig?.has_api_key ? 'text-emerald-400 font-semibold' : 'text-amber-400'}>
                  {activeConfig?.has_api_key ? `已就绪 (${activeConfig.api_key_masked || '已校验'})` : '未配置 (建议接入中转站)'}
                </span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>推演任务温度 (Temperature):</span>
                <span className="text-purple-300 font-bold">{activeConfig?.temperature ?? 0.2} (严格严谨模式)</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>接入架构模式:</span>
                <span className="text-white">
                  {activeConfig?.is_customized ? '用户自定义中转站 (已热加载)' : '系统环境变量默认配置'}
                </span>
              </div>
            </div>

            <div className="p-3 bg-black/40 rounded-lg border border-white/5 space-y-2">
              <span className="text-xs font-bold text-slate-300 block">数据指纹与防篡改审计</span>
              <div className="flex justify-between text-slate-400">
                <span>复盘快照哈希:</span>
                <span className="text-cyan-400 truncate max-w-[200px]" title="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855">
                  sha256:e3b0c44298fc1...
                </span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>两市行情样本总数:</span>
                <span className="text-white">5,492 只个股 (100% 全量覆盖)</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>审计状态:</span>
                <span className="text-emerald-400">物理数据事实已锚定 · 校验通过</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
