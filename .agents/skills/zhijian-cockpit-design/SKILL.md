---
name: zhijian-cockpit-design
description: >-
  机构级A股认知复盘与量化交易系统“知见”的专属UI/UX设计规范技能。
  当需要为“知见”设计或优化前端界面、研报大屏、Bento态势矩阵、微观结构数据看板、情绪状态机、连板天梯或交互抽屉时必须激活此技能。
  严格遵循：A股“红涨绿跌”配色铁律、等宽金融数字排版、机构级沉浸式研报质感，杜绝千篇一律的AI模板化套路。
---

# “知见”机构级金融认知复盘设计规范 (Zhijian Cockpit Design)

本规范专为 **“知见” AI 认知复盘交易系统** 制定，融合了顶级设计系统的设计工程学与金融交易室的严苛审美标准，旨在消除千篇一律的“AI 模板感”，打造具有顶级对冲基金研究台质感的沉浸式体验。

---

## 一、不可动摇的底线原则 (Inviolable Axioms)

### 1. 颜色铁律：严格遵守 A 股“红涨绿跌”规范
国际市场上常用的“绿涨红跌”在本项目中**绝对禁止出现**。
- **上涨 / 净流入 / 强封板 / 偏多**：必须使用**红系**（推荐：`#EF4444` / `#F43F5E` / `#DC2626` / Tailwind `text-rose-400`, `text-red-500`, `bg-rose-500/10`）。
- **下跌 / 净流出 / 炸板杀跌 / 偏空**：必须使用**绿系**（推荐：`#10B981` / `#22C55E` / `#059669` / Tailwind `text-emerald-400`, `text-green-500`, `bg-emerald-500/10`）。
- **基准 / 中立 / 假说 / 警示待证伪**：使用**琥珀金 / 橙系**（推荐：`#F59E0B` / `#D97706` / Tailwind `text-amber-400`, `bg-amber-500/10`）。
- **暗黑底色与卡片**：使用 OLED / 哑光金属深灰（`#090D16` / `#0F172A` / `#1E293B`），边框透明度控制在 `border-white/10` ~ `border-slate-800`，避免过高饱和度的纯白或纯黑刺眼反差。

### 2. 金融数字排版：Tabular Nums 与等宽对齐
- 所有交易价格、涨跌幅、成交额、成交量、资金流向数值，必须声明 `tabular-nums` 以及等宽字体族（`font-mono`，如 `JetBrains Mono`, `Fira Code`, `ui-monospace`）。
- **禁止**让动态波动的数字因为字符宽度不一致导致整行排版左右抖动。

---

## 二、反模板化美学法则 (Anti-Cliché Design Language)

来自 Anthropic `frontend-design` 与顶级对冲基金研报界面的美学反思：

1. **拒绝无意义的圆角卡片堆叠（No Generic SaaS Card Kit）**：
   - 不要把所有信息切成千篇一律的 `rounded-2xl shadow-lg` 卡片。
   - 采用 **Bento Grid（便当盒栅格）** 结合 **细线结构网格（Hairline Grid）**，以层级、跨列（col-span-2, col-span-3）和密度创造节奏感。
2. **拒绝无目的的装饰性渐变（No Purposeless Gradients）**：
   - 不滥用紫粉、蓝青等通用 AI 科技渐变。每一个光效和色彩溢出，必须且仅能代表流动性强弱或资金极性（如红系买盘涌入的光晕、绿系抛压释放的冷雾）。
3. **结构即信息（Structure is Information）**：
   - 数字标签（如 `01` 到 `11` 章）只用于具备明确递进逻辑的序列（宏观→微观→哲学假说）。
   - 使用机构级眉标（Eyebrows）与元数据徽章传达置信度与证据链来源。
4. **克制动效（Tactile Micro-Interactions）**：
   - 杜绝页面初次加载时漫天飞舞的淡入上浮动画。
   - 交互动效只响应用户动作（点击折叠展开、唤出 AI 对话抽屉、点击复制时微缩至 `scale-95` 的触觉反馈）。

---

## 三、“知见”专属核心组件图谱 (Cockpit Core Components)

### 1. Bento 态势矩阵 (Bento Hero Matrix)
- **指数三足鼎立 (Indices Trifecta)**：上证指数、深证成指、创业板指并列，大字号数字展示点位，红绿标签展示涨跌幅与分化程度。
- **多空极性量柱 (Polar Breadth Heatbar)**：将上涨家数与下跌家数放在同一根双极柱上直观对比，一眼看清二八分化。
- **量能收缩差值 (Volume Delta)**：清晰计算较昨日缩量/放量绝对值与百分比。
- **波普尔式核心假说卡 (Popperian Falsification Card)**：琥珀色高亮当日被事实证伪的伪逻辑与明日观察靶点。

### 2. 天际线连板天梯 (Skyline Limit-Up Ladder)
- 纵向梯队层级：高标标杆（如 10 连板）、中军承接（如 6 连板）、细分先锋（如 3 连板）、梯队扩散（2 连板/首板）。
- 伴随风险雷达：显式标明炸板率、晋级率与高位抱团背离度。

### 3. 情绪周期五阶段状态机 (5-Stage Emotion State Machine)
- 状态集合：`冰点分歧 (Ice Divergence)` -> `弱势修复 (Weak Repair)` -> `主线共振 (Resonance)` -> `高潮过热 (Overheating)` -> `退潮恐慌 (Panic Runoff)`。
- 视觉呈现：5 阶段进度指示灯，当前阶段带有光晕呼吸动效与资金应对策略指导（如“严格控仓、拒绝追高”）。

### 4. 伴随式证据链与 AI 对话抽屉 (Interactive Copilot Drawer)
- 研报右下角常驻便捷对话触发器（含快捷提问推荐语，如“为什么今天缩量不能看作洗盘结束？”、“风电与传媒谁更有持续性？”）。
- 抽屉采用右侧滑入，半透明磨砂玻璃背板（`backdrop-blur-md bg-slate-900/90`），支持 Markdown 富文本渲染与免打扰收起。
- 顶部导航提供“一键复制完整 11 章研报 (Markdown)”按钮，带有 2 秒打勾反馈。

---

## 四、执行工作流与工具链

当需要生成、调整或重构“知见”界面时：
1. **调用本地设计数据库快速检索**：
   ```bash
   python .agents/skills/ui-ux-pro-max/scripts/search.py "trading dashboard" --domain style
   python .agents/skills/ui-ux-pro-max/scripts/search.py "dashboard analytics" --domain typography
   ```
2. **检查 A 股色彩规范**：
   - 检查所有颜色类名：涨必须为 `red/rose`，跌必须为 `green/emerald`。
3. **前端代码验证**：
   - 执行 `npm run build` 确保 TypeScript 类型与路由无编译错误。
