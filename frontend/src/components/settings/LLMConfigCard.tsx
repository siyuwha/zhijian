'use client';

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  api,
  LLMConfigData,
  LLMConfigUpdatePayload,
  LLMTestResult,
} from '@/lib/api';
import {
  Key,
  Eye,
  EyeOff,
  Zap,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Save,
  RotateCcw,
  Sparkles,
  Globe,
  Bot,
  ExternalLink,
  Sliders,
  ShieldCheck,
  RefreshCw,
} from 'lucide-react';

interface PresetOption {
  id: string;
  label: string;
  description: string;
  baseUrl: string;
  defaultModel: string;
  recommendedModels: string[];
}

const PRESETS: PresetOption[] = [
  {
    id: 'openai_compatible',
    label: 'OpenAI 兼容中转站',
    description: '支持 OneAPI / NewAPI / 各类中转代充平台，兼容标准 /v1/chat/completions',
    baseUrl: 'https://api.openai-proxy.org/v1',
    defaultModel: 'gpt-4o',
    recommendedModels: ['gpt-4o', 'gpt-4o-mini', 'claude-3-5-sonnet', 'deepseek-chat', 'deepseek-reasoner', 'qwen-max'],
  },
  {
    id: 'deepseek',
    label: 'DeepSeek 官方直连',
    description: '深度求索官方开放平台，高性价比大模型',
    baseUrl: 'https://api.deepseek.com/v1',
    defaultModel: 'deepseek-chat',
    recommendedModels: ['deepseek-chat', 'deepseek-reasoner'],
  },
  {
    id: 'openai',
    label: 'OpenAI 官方直连',
    description: 'OpenAI 官方 API 服务 (需外网代理或直连网络)',
    baseUrl: 'https://api.openai.com/v1',
    defaultModel: 'gpt-4o',
    recommendedModels: ['gpt-4o', 'gpt-4o-mini', 'o1-preview', 'o1-mini'],
  },
  {
    id: 'custom',
    label: '自定义端点 / 本地模型',
    description: '支持 Ollama / vLLM / LocalAI 或内网自建推理节点',
    baseUrl: 'http://localhost:11434/v1',
    defaultModel: 'deepseek-r1:latest',
    recommendedModels: ['deepseek-r1:latest', 'qwen2.5:32b', 'llama3.3:70b'],
  },
];

export function LLMConfigCard({ onConfigChange }: { onConfigChange?: (config: LLMConfigData) => void }) {
  const [config, setConfig] = useState<LLMConfigData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [resetting, setResetting] = useState(false);

  // 表单状态
  const [providerType, setProviderType] = useState('openai_compatible');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [model, setModel] = useState('');
  const [temperature, setTemperature] = useState(0.2);
  const [timeoutSeconds, setTimeoutSeconds] = useState(60);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // 测试与操作反馈信息
  const [testResult, setTestResult] = useState<LLMTestResult | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // 获取服务端当前生效配置
  const fetchConfig = async () => {
    try {
      setLoading(true);
      const res = await api.getLLMConfig();
      setConfig(res);
      setProviderType(res.provider_type || 'openai_compatible');
      setBaseUrl(res.base_url || '');
      setModel(res.model || '');
      setTemperature(res.temperature ?? 0.2);
      setTimeoutSeconds(res.timeout_seconds ?? 60);
      setApiKey(''); // 安全清空明文输入框
      if (onConfigChange) onConfigChange(res);
    } catch (err: any) {
      setFeedback({ type: 'error', message: `获取配置失败: ${err.message || '网络连接异常'}` });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  // 选择预设
  const handleSelectPreset = (preset: PresetOption) => {
    setProviderType(preset.id);
    setBaseUrl(preset.baseUrl);
    setModel(preset.defaultModel);
    setTestResult(null);
    setFeedback(null);
  };

  // 发起连通性握手测试
  const handleTest = async () => {
    if (!baseUrl) {
      setFeedback({ type: 'error', message: '请先填写 API 接口地址 (Base URL)' });
      return;
    }
    if (!model) {
      setFeedback({ type: 'error', message: '请先填写待测试的推理模型名称' });
      return;
    }

    try {
      setTesting(true);
      setTestResult(null);
      setFeedback(null);

      const res = await api.testLLMConnection({
        base_url: baseUrl,
        api_key: apiKey || null, // 若为空则后端尝试使用已保存的密钥
        model,
        timeout_seconds: 25,
      });

      setTestResult(res);
      if (res.success) {
        setFeedback({ type: 'success', message: res.message });
      } else {
        setFeedback({ type: 'error', message: `${res.message}: ${res.error || '测试未通过'}` });
      }
    } catch (err: any) {
      setTestResult({
        success: false,
        latency_ms: 0,
        message: '连接失败',
        error: err.message || '网络或中转端点异常',
      });
      setFeedback({ type: 'error', message: `测试握手失败: ${err.message}` });
    } finally {
      setTesting(false);
    }
  };

  // 保存并应用
  const handleSave = async () => {
    if (!baseUrl) {
      setFeedback({ type: 'error', message: 'API 端点地址 (Base URL) 不能为空' });
      return;
    }
    if (!model) {
      setFeedback({ type: 'error', message: '模型名称 (Model) 不能为空' });
      return;
    }

    try {
      setSaving(true);
      setFeedback(null);

      const payload: LLMConfigUpdatePayload = {
        provider_type: providerType,
        base_url: baseUrl,
        model,
        api_key: apiKey ? apiKey.trim() : null,
        temperature,
        timeout_seconds: timeoutSeconds,
      };

      const res = await api.updateLLMConfig(payload);
      setConfig(res);
      setApiKey(''); // 安全清空输入的明文
      setFeedback({
        type: 'success',
        message: `配置已热加载生效！系统当前推理模型已切换为 [${res.model}]，中转端点: [${res.base_url}]`,
      });
      if (onConfigChange) onConfigChange(res);
    } catch (err: any) {
      setFeedback({ type: 'error', message: `保存失败: ${err.message || '未知错误'}` });
    } finally {
      setSaving(false);
    }
  };

  // 恢复系统默认
  const handleReset = async () => {
    if (!window.confirm('确认重置为系统默认环境变量配置吗？已自定义的中转站地址与密钥将被清除。')) {
      return;
    }

    try {
      setResetting(true);
      setFeedback(null);
      setTestResult(null);

      const res = await api.resetLLMConfig();
      setConfig(res);
      setProviderType(res.provider_type || 'openai_compatible');
      setBaseUrl(res.base_url);
      setModel(res.model);
      setTemperature(res.temperature);
      setTimeoutSeconds(res.timeout_seconds);
      setApiKey('');
      setFeedback({ type: 'success', message: '已恢复为系统默认环境变量配置！' });
      if (onConfigChange) onConfigChange(res);
    } catch (err: any) {
      setFeedback({ type: 'error', message: `重置失败: ${err.message}` });
    } finally {
      setResetting(false);
    }
  };

  // 获取当前预设推荐模型列表
  const currentPreset = PRESETS.find((p) => p.id === providerType) || PRESETS[0];

  return (
    <Card className="bg-[#0B0E17] border-white/10 shadow-2xl relative overflow-hidden">
      {/* 顶部微光装饰边线 */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-purple-500 via-amber-400 to-cyan-400 opacity-80" />

      <CardHeader className="border-b border-white/5 pb-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-purple-950/80 border border-purple-500/40 flex items-center justify-center text-purple-300 shadow-md">
              <Bot className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <CardTitle className="text-base font-bold text-white tracking-wide">
                  系统 LLM 推理引擎与 API 接入设置
                </CardTitle>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-950/60 text-cyan-300 border border-cyan-700/50">
                  OPENAI-COMPATIBLE RELAY
                </span>
                {config?.is_customized ? (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950/60 text-emerald-300 border border-emerald-700/50">
                    自定义配置已激活
                  </span>
                ) : (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-white/10">
                    环境变量默认值
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                支持通用 OpenAI 格式中转站 (OneAPI / NewAPI / 代理站) 及官方直连。系统操盘内参、全景研报复盘与 AI 深度问答将直接由此引擎推演驱动。
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-start md:self-auto">
            <button
              onClick={fetchConfig}
              disabled={loading}
              className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition"
              title="重新加载当前配置"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-purple-400' : ''}`} />
            </button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-5 space-y-6 text-xs">
        {/* 1. 快捷预设接入模式 */}
        <div className="space-y-2">
          <label className="text-slate-300 font-semibold flex items-center gap-1.5">
            <Globe className="w-3.5 h-3.5 text-cyan-400" />
            <span>选择接入模式 / 常用服务商预设</span>
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
            {PRESETS.map((p) => {
              const active = providerType === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleSelectPreset(p)}
                  className={`p-3 rounded-xl border text-left transition-all relative ${
                    active
                      ? 'bg-purple-950/40 border-purple-500 text-white shadow-lg shadow-purple-950/30 ring-1 ring-purple-500/50'
                      : 'bg-black/30 border-white/5 hover:border-white/20 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <div className="font-bold text-xs flex items-center justify-between">
                    <span>{p.label}</span>
                    {active && <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-ping" />}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                    {p.description}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* 2. 表单核心项：Base URL + Model + API Key */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Base URL (中转站 / 接口端点地址) */}
          <div className="space-y-1.5 md:col-span-2">
            <div className="flex items-center justify-between">
              <label className="text-slate-300 font-semibold flex items-center gap-1.5">
                <ExternalLink className="w-3.5 h-3.5 text-amber-400" />
                <span>API 接口地址 (Base URL)</span>
                <span className="text-rose-400">*</span>
              </label>
              <span className="text-[10px] text-slate-500 font-mono">
                标准格式: https://api.your-relay.com/v1
              </span>
            </div>
            <div className="relative">
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="例如: https://api.openai-proxy.org/v1 或 https://api.deepseek.com/v1"
                className="w-full bg-black/50 border border-white/10 focus:border-purple-500/80 rounded-xl px-3.5 py-2.5 text-xs text-white font-mono placeholder:text-slate-600 focus:outline-none transition"
              />
            </div>
            <p className="text-[10px] text-slate-500">
              💡 中转站（OneAPI / NewAPI / 独立反代）通常以 <code className="text-cyan-300">/v1</code> 结尾。系统会自动对接标准的 <code className="text-cyan-300">/chat/completions</code> 规范。
            </p>
          </div>

          {/* API Key */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-slate-300 font-semibold flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5 text-purple-400" />
                <span>API Key (接口密钥)</span>
                {config?.has_api_key && (
                  <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" /> 已配置生效 ({config.api_key_masked})
                  </span>
                )}
              </label>
            </div>
            <div className="relative">
              <input
                type={showApiKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={config?.has_api_key ? '已保存有效 Key (若无需更换请留空)' : '请输入 sk-xxxx 接口密钥'}
                className="w-full bg-black/50 border border-white/10 focus:border-purple-500/80 rounded-xl px-3.5 py-2.5 pr-10 text-xs text-white font-mono placeholder:text-slate-600 focus:outline-none transition"
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-3 top-2.5 text-slate-500 hover:text-slate-300 transition"
                title={showApiKey ? '隐藏密钥' : '显示密钥'}
              >
                {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-[10px] text-slate-500">
              🔒 密钥仅在服务端安全调用，绝不在浏览器端暴露，保存时自动更新持久化存储。
            </p>
          </div>

          {/* 模型名称 (Model Name) */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-slate-300 font-semibold flex items-center gap-1.5">
                <Bot className="w-3.5 h-3.5 text-emerald-400" />
                <span>推理模型名称 (Model)</span>
                <span className="text-rose-400">*</span>
              </label>
              <span className="text-[10px] text-slate-500 font-mono">
                当前: {model || '--'}
              </span>
            </div>
            <div className="relative">
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="例如: gpt-4o 或 deepseek-chat"
                className="w-full bg-black/50 border border-white/10 focus:border-purple-500/80 rounded-xl px-3.5 py-2.5 text-xs text-white font-mono placeholder:text-slate-600 focus:outline-none transition"
              />
            </div>
            {/* 快速填入推荐模型药丸按钮 */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[10px] text-slate-500">常用模型:</span>
              {currentPreset.recommendedModels.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setModel(m)}
                  className={`text-[10px] font-mono px-2 py-0.5 rounded-full border transition ${
                    model === m
                      ? 'bg-purple-900/60 text-purple-200 border-purple-500 font-bold'
                      : 'bg-white/[0.03] text-slate-400 border-white/10 hover:border-white/20 hover:text-white'
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* 3. 高级超参数设置折叠栏 */}
        <div className="border border-white/5 rounded-xl p-3 bg-black/20">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full flex items-center justify-between text-xs text-slate-400 hover:text-slate-200 transition"
          >
            <div className="flex items-center gap-2">
              <Sliders className="w-3.5 h-3.5 text-cyan-400" />
              <span className="font-semibold text-slate-300">高级推演参数 (Temperature &amp; 超时)</span>
            </div>
            <span className="text-[10px] text-slate-500 font-mono">
              {showAdvanced ? '收起 ▲' : '展开 ▼'}
            </span>
          </button>

          {showAdvanced && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3 pt-3 border-t border-white/5">
              <div className="space-y-1.5">
                <div className="flex justify-between text-[11px]">
                  <span className="text-slate-400">采样温度 (Temperature):</span>
                  <span className="font-mono text-purple-300 font-bold">{temperature}</span>
                </div>
                <input
                  type="range"
                  min="0.0"
                  max="1.0"
                  step="0.05"
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value))}
                  className="w-full accent-purple-500 cursor-pointer"
                />
                <div className="flex justify-between text-[9px] text-slate-500">
                  <span>0.0 (绝对严谨)</span>
                  <span className="text-purple-400 font-semibold">0.2 推荐 (量化严密)</span>
                  <span>1.0 (高创意)</span>
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex justify-between text-[11px]">
                  <span className="text-slate-400">请求超时秒数 (Timeout):</span>
                  <span className="font-mono text-cyan-300 font-bold">{timeoutSeconds}s</span>
                </div>
                <input
                  type="range"
                  min="15"
                  max="180"
                  step="5"
                  value={timeoutSeconds}
                  onChange={(e) => setTimeoutSeconds(parseInt(e.target.value))}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
                <div className="flex justify-between text-[9px] text-slate-500">
                  <span>15s</span>
                  <span className="text-cyan-400 font-semibold">60s 推荐 (研报推理)</span>
                  <span>180s</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 4. 操作与诊断反馈横幅 */}
        {feedback && (
          <div
            className={`p-3 rounded-xl border flex items-start gap-2.5 transition animate-in fade-in duration-200 ${
              feedback.type === 'success'
                ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-300'
                : 'bg-rose-950/30 border-rose-500/40 text-rose-300'
            }`}
          >
            {feedback.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            )}
            <div className="text-xs leading-relaxed flex-1">
              {feedback.message}
            </div>
          </div>
        )}

        {/* 5. 连通性测试诊断结果面板 */}
        {testResult && (
          <div
            className={`p-3.5 rounded-xl border space-y-2 ${
              testResult.success
                ? 'bg-gradient-to-r from-emerald-950/40 via-teal-950/30 to-black/40 border-emerald-500/40'
                : 'bg-gradient-to-r from-rose-950/40 via-red-950/30 to-black/40 border-rose-500/40'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-bold flex items-center gap-1.5">
                {testResult.success ? (
                  <>
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span className="text-emerald-300">中转站 API 握手连通成功</span>
                  </>
                ) : (
                  <>
                    <XCircle className="w-4 h-4 text-rose-400" />
                    <span className="text-rose-300">中转站 API 握手测试未通过</span>
                  </>
                )}
              </span>
              <span className="font-mono text-xs px-2 py-0.5 rounded bg-black/50 border border-white/10 text-slate-300">
                耗时: <strong className={testResult.latency_ms < 500 ? 'text-emerald-400' : 'text-amber-400'}>{testResult.latency_ms} ms</strong>
              </span>
            </div>

            <div className="text-xs text-slate-300 font-mono">
              <div><strong>测试模型:</strong> {testResult.model_used || model}</div>
              {testResult.reply_preview && (
                <div className="mt-1 text-slate-400 text-[11px]">
                  <strong>模型响应片段:</strong> <span className="text-emerald-300 bg-black/40 px-1 py-0.5 rounded">&ldquo;{testResult.reply_preview}&rdquo;</span>
                </div>
              )}
              {testResult.error && (
                <div className="mt-1 text-rose-300 text-[11px] bg-black/40 p-2 rounded border border-rose-500/20">
                  <strong>错误详情:</strong> {testResult.error}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 6. 操作按钮工具条 */}
        <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-white/5">
          <div className="flex items-center gap-2 w-full sm:w-auto">
            {/* 连通性测试按钮 */}
            <button
              type="button"
              onClick={handleTest}
              disabled={testing || saving}
              className="flex-1 sm:flex-initial px-4 py-2 rounded-xl bg-cyan-950/60 hover:bg-cyan-900/60 border border-cyan-500/40 hover:border-cyan-400 text-cyan-300 font-bold text-xs flex items-center justify-center gap-2 transition active:scale-95 disabled:opacity-50"
            >
              <Zap className={`w-3.5 h-3.5 text-cyan-400 ${testing ? 'animate-bounce' : ''}`} />
              <span>{testing ? '正在握手测试...' : '测试中转站连通性'}</span>
            </button>

            {/* 恢复默认按钮 */}
            <button
              type="button"
              onClick={handleReset}
              disabled={resetting || saving || testing}
              className="px-3 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-400 hover:text-white text-xs flex items-center gap-1.5 transition active:scale-95 disabled:opacity-50"
              title="清除自定义中转站配置，恢复为系统默认环境变量"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${resetting ? 'animate-spin' : ''}`} />
              <span>恢复默认</span>
            </button>
          </div>

          {/* 保存并应用配置按钮 */}
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || testing}
            className="w-full sm:w-auto px-6 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-purple-900/30 border border-purple-400/40 transition active:scale-95 disabled:opacity-50"
          >
            <Save className={`w-3.5 h-3.5 ${saving ? 'animate-spin' : ''}`} />
            <span>{saving ? '正在保存并热加载...' : '保存并应用此 API 设置'}</span>
          </button>
        </div>
      </CardContent>
    </Card>
  );
}
