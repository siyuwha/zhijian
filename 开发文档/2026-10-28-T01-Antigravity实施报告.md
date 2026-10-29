# T01 模拟统计收尾与页面异常处理实施报告

- 任务编号：T01 / ZJ-SIM-STATS-002
- 实施日期：2026-10-28（北京时间）
- 实施方：Antigravity CLI
- 状态：已按返修单（R1/R2/R3）及复审记录完成全部代码返修、静态类型检查、生产构建与隔离脚本编制；真实浏览器端到端补充验证全量闭环；用户已回传确认本次独立复审通过；待 Work 汇总交付；未提交、未部署、未业务验收。

---

## 一、任务目标与修改范围

### 1. 核心目标
根据 `开发文档/2026-10-28-T01-模拟统计收尾与页面异常处理任务单.md` 与 `开发文档/2026-10-28-T01与T04-01-审查返修单.md`：
1. 模拟统计失败时必须清空旧 `stats` 并持续显示原因，保留 HTTP 409 的流水 ID 与业务原因；
2. 已实现盈亏不可用时（缺失、null 或非数值），已实现盈亏、可用现金、总资产及依赖比例一律展示 `--`，不得假充为 0；
3. 平仓腿数与盈利腿数必须严格使用专属平仓统计字段，缺失/null 时展示 `--`，严禁用买卖流水总数 `total_trades` 代替；仅在 `closed_trades === 0` 时展示“暂无平仓样本”，字段缺失时不得误报；
4. 真实零值（如 0% 胜率、0.00 元已实现）正常展示，与 null 及请求失败明确区分；
5. 请求顺序防竞态控制：较早发出迟到的响应不得覆盖较新响应；刷新恢复成功后清除错误提示；
6. 统计失败时，持仓列表与成交流水列表等独立成功的接口内容必须继续可用。

### 2. 修改文件及业务差异

本次业务代码修改**仅限定于单个文件**：`frontend/src/app/simulation/page.tsx`。

| 代码区域 | 原实现缺陷 | 实施修复方案 |
| --- | --- | --- |
| 状态与顺序控制 | 未处理 `statsRes` 失败拒绝；无请求序号追踪；按钮可重复点击引发重叠 | 增加 `reqSequenceRef` 递增计数，响应返回时比对序列号，过期响应直接丢弃；刷新按钮增加 `isRefreshing \|\| isLoading` 禁用态 |
| 409 与通用错误 | 统计失败保留旧 `stats`，无持续错误文字，依赖通知横幅 4.5s 消失 | 设立独立 `statsError` 状态，失败立即 `setStats(null)` 并保存后端返回原因；Card 4 内嵌入 `role="alert"` 与 `aria-live="assertive"` 持续错误警告框，不随 4.5s 通知消失 |
| 已实现盈亏与资金防线 | `stats?.total_realized_pnl \|\| 0` 将 null 或缺失强转为 0，冒充有效初始资产 | 重构判定为 `isRealizedPnlAvailable`（必须为有限数值 `Number.isFinite`）；缺失或 null 时 `totalRealizedPnl` 为 `null`，可用现金、总资产、总收益率、现金储备率、仓位比例一律为 `null` 并渲染 `--`；收益率中立无红绿样式 |
| 平仓腿与样本判断 | `closed_trades ?? total_trades ?? 0` 将买卖流水总数冒充平仓腿；null 时误报暂无平仓样本 | 独立定义 `closedTradesCount` 与 `winTradesCount`；缺失或 null 时严格渲染 `(-- 盈利 / -- 平仓腿)`；仅当 `closedTradesCount === 0` 时提示“暂无平仓样本” |
| 刷新恢复与成功覆盖 | 刷新可能与旧错误交织 | 统计请求成功且返回有效统计对象时，清空 `statsError`，更新 `stats`，资产指标恢复自洽 |

---

## 二、命令检查与编译构建结果

在当前 Antigravity 明确授权的交互执行上下文中执行：

| 检查项 | 执行命令 | 实际退出码 | 检查结果与原始输出摘要 |
| --- | --- | --- | --- |
| 前端 TypeScript | `pwsh -Command "cd frontend; .\node_modules\.bin\tsc.cmd --noEmit --incremental false"` | `0` | 通过，无类型错误，类型检查严密匹配 |
| 前端生产构建 | `npm --prefix frontend run build` | `0` | 通过，Compiled successfully，13/13 static pages 生成，包含 `/simulation` (11.7 kB) |
| 后端专项回归（Run 1） | `backend/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/test_simulation_stats.py` | `0` | `13 passed in 5.34s`（日志：`scratch/t04-01-python/test_run_1.log`） |
| 后端专项回归（Run 2） | `backend/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/test_simulation_stats.py` | `0` | `13 passed in 5.45s`（日志：`scratch/t04-01-python/test_run_2.log`） |

> **边界声明**：实施前未做全工作区快照，当前 `git status` 差异反映的是当前工作区状态，不能据此确认实施前后所有历史文件变化。

---

## 三、前端验收样例（AC01—AC10、AC11、AC12）证据分类核对

根据任务单与返修单要求，逐项严格区分【真实浏览器已验证】、【离线模型断言】、【源码判断】与【待 Codex 独立环境复跑】：

| 编号 | 场景描述 | 验收要求 | 验证方式与证据状态 | 证据文件 / 路径 |
| --- | --- | --- | --- | --- |
| AC01 | 首次加载等待 | 延迟统计响应，依赖指标显示 `--`，不展示虚构零值 | 【真实浏览器已验证】页面挂载显示“正在获取平仓统计...”，资金卡显示 `--` | `scratch/t01-dispatch/browser-review.cjs` |
| AC02 | 有效零值 | 买 10 卖 9，胜率 0%，已实现 -100 元，盈亏比 null | 【真实浏览器已验证】胜率显示 `0%`，`0 盈利 / 1 平仓腿`，`-100.00 元`，盈亏样本不足 | `scratch/t01-dispatch/browser-review.cjs` |
| AC03 | 无平仓样本 | 仅买入或空仓，平仓腿 0，胜率 null，实现盈亏 0 | 【真实浏览器已验证】显示“暂无平仓样本”，实现盈亏 `0.00 元`，资金区域正常计算 | `scratch/t01-dispatch/browser-review.cjs` |
| AC04 | 首次 409 | 返回 409 且 detail 含流水 ID 42 存在超卖异常 | 【真实浏览器已验证】持续警报显示流水 ID 42，依赖资金指标清空显示 `--` | `scratch/t01-dispatch/browser-review.cjs` |
| AC05 | 成功后失败 | 先成功显示 50% 与 +100 元，刷新返回 409 | 【真实浏览器已验证】旧值清除，指标重置为 `--`，持续警告保持 | 截图：`scratch/t01-dispatch/browser-ac05-409.png` |
| AC06a | 网络断开 | fetch 抛出 TypeError: Failed to fetch | 【真实浏览器已验证】页面不崩溃，提示 Failed to fetch，资金指标清空 | `scratch/t01-dispatch/browser-review.cjs` |
| AC06b | HTTP 500 (JSON) | 500 且返回 `{ detail: "后端服务内部错误" }` | 【真实浏览器已验证】正确解析并提示后端内部错误 | `scratch/t01-dispatch/browser-review.cjs` |
| AC06c | HTTP 500 (非 JSON) | 500 且返回 HTML 错误页面（非 JSON） | 【真实浏览器已验证】页面不崩溃，role="alert" 呈现“后端服务内部错误”，资金指标清空为 `--` | 脚本：`scratch/t01-dispatch/browser-r3-supplementary-v3.cjs`，截图：`scratch/t01-dispatch/browser-r3-v3-500-non-json.png` |
| AC06d | 空统计响应 | HTTP 200 但 `data: null` | 【真实浏览器已验证】显示“统计数据为空或无法解析，请重试” | `scratch/t01-dispatch/browser-review.cjs` |
| AC07 | 恢复成功 | 409 状态下点击刷新返回有效统计 | 【真实浏览器已验证】警报消失，新胜率 50% 与 +100 元展示，资金指标恢复 | 截图：`scratch/t01-dispatch/browser-ac07-recovered.png` |
| AC08a | 部分接口失败（持仓） | 统计 409，但持仓成功 | 【真实浏览器已验证】持仓“验收样例银行”继续展示，统计区域明确失败 | `scratch/t01-dispatch/browser-review.cjs` |
| AC08b | 部分接口失败（策略） | 策略 503 失败，但统计成功 | 【真实浏览器已验证】统计正常展示 50%，未受策略失败污染 | `scratch/t01-dispatch/browser-review.cjs` |
| AC08c | 部分接口失败（流水） | 统计 409 失败，但成交流水非空 | 【真实浏览器已验证】切换成交流水页签，招商银行 600036 买入 1000 股（35,500 元）正常展示，上方 409 持续警报保留 | 脚本：`scratch/t01-dispatch/browser-r3-supplementary-v3.cjs`，截图：`scratch/t01-dispatch/browser-r3-v3-records-usable-409.png` |
| AC09 | 提示独立性 | 409 警报出现后等待超过 4.5 秒（4.7s） | 【真实浏览器已验证】警报仍常驻存在，不随临时交易通知消失 | `scratch/t01-dispatch/browser-review.cjs` |
| AC10a | 请求重叠入口防护 | 刷新进行中检查按钮状态 | 【真实浏览器已验证】刷新按钮呈 disabled 态，无法通过频繁点击制造重叠 | `scratch/t01-dispatch/browser-review.cjs` |
| AC10b | 请求逆序返回防覆盖 | 请求 A 先发后至，请求 B 后发先至 | 【真实浏览器已验证】覆盖新成功（75% 与 +400元保持，旧 30% 丢弃）与新错误（409 警报保持，旧 60% 成功未冲掉错误）双场景；注明强制并发触发机制 | 脚本：`scratch/t01-dispatch/browser-r3-supplementary-v3.cjs`，截图：`scratch/t01-dispatch/browser-r3-v3-race-newer-success.png`、`browser-r3-v3-race-newer-error.png` |
| AC11 | 已实现盈亏缺失/null | `total_realized_pnl` 字段缺失或为 null | 【真实浏览器已验证】每轮独立同步等待与特异性标记断言；缺失与 null 分开验证，资金及比例显示 `--`，胜率与盈亏比正常展示，无错误警告 | 脚本：`scratch/t01-dispatch/browser-r3-supplementary-v3.cjs`，截图：`scratch/t01-dispatch/browser-r3-v3-missing-realized.png`、`browser-r3-v3-null-realized.png` |
| AC12 | 平仓腿缺失/null | `closed_trades` 字段缺失或为 null | 【真实浏览器已验证】每轮独立同步等待；缺失与 null 分别严格展示 `(-- 盈利 / -- 平仓腿)`，不以流水总数冒充，不误报暂无样本；单笔亏损（0%、-100元）与无平仓（--、0.00元）零值场景严格拆分断言 | 脚本：`scratch/t01-dispatch/browser-r3-supplementary-v3.cjs`，截图：`scratch/t01-dispatch/browser-r3-v3-missing-closed.png`、`browser-r3-v3-null-closed.png`、`browser-r3-v3-zero-loss.png`、`browser-r3-v3-zero-nocalls.png` |

---

## 四、R1、R2、R3 返修状态与对照核查

### 1. R1：Python 环境启动诊断对照（保持未闭环）
- **Codex 失败证据**：
  - `scratch/t04-01-python/codex-review-version-failure.json`：执行 `backend/.venv/Scripts/python.exe --version` 报 `Unable to create process using '...'`，退出码 `101`；
  - `scratch/t04-01-python/codex-review-base-access.json`：可正常读取基础解释器元数据（大小 104952 字节），表明文件系统并非绝对不可访问；
  - `scratch/t04-01-python/codex-review-base-launch.json`：直接启动基础解释器报 `StandardOutputEncoding is only supported when standard output is redirected`，退出码为 null（PowerShell 宿主输出流重定向异常）；
  - 用户专项测试运行退出码为 `1`。
- **Antigravity 成功证据**：
  - 在当前明确授权的交互终端下执行 `backend/.venv/Scripts/python.exe --version` 退出码 `0`，输出 `Python 3.12.10`；两次专项测试均 `13 passed in 5.34s/5.45s`，退出码 `0`。
- **返修结论**：
  - 由于执行方无法进入 Codex 的实际沙箱环境进行交互排查，根因**未最终确认**；
  - 当前成果仅证明在 Antigravity 授权上下文中可用，不声称所有宿主全局修复；
  - **R1 状态：保持未闭环（待 Codex 独立对照验证）**。

### 2. R2：HTTP 409 响应透传验证（已通过隔离验证）
- **现状核查**：既有 `test_simulation_stats.py` 中的 2 个 409 用例仅断言服务层抛出 `fastapi.HTTPException`，未直接验证路由层 ASGI/HTTP 响应序列化；
- **返修措施与隔离执行**：已修正 `scratch/t04-01-python/test_http_409_passthrough.py`（解决路由导入与 `DataService` 注入），使用纯内存 SQLite (`sqlite+aiosqlite:///:memory:`)、`StaticPool`、`dependency_overrides` 及 `MockDataService` 运行：
  - 执行命令：`& '.\backend\.venv\Scripts\python.exe' '.\scratch\t04-01-python\test_http_409_passthrough.py' 2>&1 | Tee-Object -FilePath '.\scratch\t04-01-python\http_409_passthrough-console.log'`
  - 退出码：`0`
  - 场景 A（无成本卖出）：返回 HTTP 409，detail 准确包含流水 ID 1 和“无成本卖出”；
  - 场景 B（超卖异常）：返回 HTTP 409，detail 准确包含流水 ID 2 和“超卖”；
  - 场景 C（正常流水）：返回 HTTP 200，透传完整统计结构；
  - 日志文件：`scratch/t04-01-python/http_409_passthrough.log` 与 `scratch/t04-01-python/http_409_passthrough-console.log`。
- **R2 状态：Antigravity 隔离自检通过，待 Codex 独立复审**。

### 3. R3：T01 实施报告与真实浏览器补证（v3 独立复审返修版已全量闭环）
- **复审返修脚本**：`scratch/t01-dispatch/browser-r3-supplementary-v3.cjs`
  - **同步等待机制**：每轮刷新前重置受控 Promise 拦截器，严格等待该轮 `window.fetch` 发起被捕获后才注入响应；每轮注入具备唯一性标记的数据（如独特的胜率、已实现盈亏与盈亏比），必须等待该轮特异标记反映在 DOM 中且页面完全回归 Idle 态才执行断言，彻底避免沿用上一轮状态；
  - **双逆序并发防覆盖与机制说明**：
    - *机制说明*：由于生产页面在刷新中通过 `button.disabled` 阻止了正常用户高频重复点击，为专项验证并发请求到达时后端响应乱序的防御逻辑（即前端序列号防御 `reqSequenceRef` 这一深层防线），脚本通过 React 内部属性 `button.__reactProps$.onClick` 连续同步派发两轮 `loadAllData()` 请求，模拟网络重叠；
    - *场景 2a（较新成功 vs 较早成功）*：请求 B（较新）先返回并渲染 75% 与 +400.00 元，请求 A（较早）迟到返回 30% 与 +20.00 元被 `reqSequenceRef` 丢弃，画面保持 75% 与 +400.00 元；
    - *场景 2b（较新错误 vs 较早成功）*：请求 D（较新）先返回 HTTP 409 异常（流水 ID 99），界面进入 409 警报与指标清空态；请求 C（较早）迟到返回 60% 成功，被 `reqSequenceRef` 丢弃，409 持续警报与指标清空态未被冲掉或复活；
  - **字段缺失、为 null 与零值场景独立拆分**：
    - *3a（total_realized_pnl 缺失）*：独有标记 `win_rate: 51.0%`，资金与比例清空为 `--`，胜率与盈亏比正常展示；
    - *3b（total_realized_pnl 为 null）*：独有标记 `win_rate: 52.0%`，资金与比例清空为 `--`，胜率与盈亏比正常展示；
    - *3c（closed_trades 缺失）*：独有标记 `realized: +103.00 元`，严格展示 `(-- 盈利 / -- 平仓腿)`，不以流水总数冒充，不误报暂无样本；
    - *3d（closed_trades 为 null）*：独有标记 `realized: +104.00 元`，严格展示 `(-- 盈利 / -- 平仓腿)`，不以流水总数冒充，不误报暂无样本；
    - *3e（单笔亏损有效零值）*：胜率 `0%`，腿数 `(0 盈利 / 1 平仓腿)`，已实现 `-100.00 元`，说明“盈亏样本不足”，资金正常按 `-100.00 元` 计算；
    - *3f（无平仓有效零值）*：平仓腿 `0`，胜率 `--`，已实现 `0.00 元`，提示“暂无平仓样本”，资金正常按 `0.00 元` 计算；
  - **统计失败但非空流水可用**：
    - 统计接口 409 失败，上方平仓统计卡片保留流水 ID 42 持续警报；
    - 成交流水接口独立成功返回招商银行流水（600036 买入 1000 股，35,500 元），切换页签后表格完整正确渲染，上方 409 提示保持存在。
- **执行命令与结果**：
  - 执行命令：`node 'scratch\t01-dispatch\browser-r3-supplementary-v3.cjs'`
  - 实际退出码：`0`（`NODE_EXIT_CODE=0`）
  - 全部场景 100% 通过（4/4 Passed，含 3a-3f 及 2a-2b 各子项）。
- **交付凭证文件**：
  - 结构化 JSON 报告：`scratch/t01-dispatch/browser-r3-v3-results.json`
  - 完整执行日志：`scratch/t01-dispatch/browser-r3-v3-execution.log`
  - 10 份全幅真实页面截图：
    - `scratch/t01-dispatch/browser-r3-v3-500-non-json.png`
    - `scratch/t01-dispatch/browser-r3-v3-race-newer-success.png`
    - `scratch/t01-dispatch/browser-r3-v3-race-newer-error.png`
    - `scratch/t01-dispatch/browser-r3-v3-missing-realized.png`
    - `scratch/t01-dispatch/browser-r3-v3-null-realized.png`
    - `scratch/t01-dispatch/browser-r3-v3-missing-closed.png`
    - `scratch/t01-dispatch/browser-r3-v3-null-closed.png`
    - `scratch/t01-dispatch/browser-r3-v3-zero-loss.png`
    - `scratch/t01-dispatch/browser-r3-v3-zero-nocalls.png`
    - `scratch/t01-dispatch/browser-r3-v3-records-usable-409.png`
  - 既有历史截图与 v2 证据均完整保留。
- **R3 状态：Codex 复审意见已完成闭环返修，用户已回传确认本次复审通过**。

---

## 五、操作边界与未部署声明

1. **未提交工作保护**：未执行 `git reset` 或 `git clean`，已有修改及文档均完好保留；
2. **零业务写入与生产隔离**：未连接券商，未写入生产交易流水，未启动自动后台调度；
3. **未提交与未部署**：未执行 `git commit`，未 `git push`，未重启生产服务，未部署到线上环境；
4. **交接说明**：本报告作为 Antigravity 实施与返修记录交 Work 汇总；用户已回传确认 Codex 独立复审通过；未部署，业务验收由项目负责人最终决定。
