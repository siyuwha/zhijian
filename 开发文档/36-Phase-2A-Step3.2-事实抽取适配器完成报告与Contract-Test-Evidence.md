# Phase 2A Step 3.2 事实抽取适配器完成报告与 Contract Test 证据链
# （M1/M2/M4/M5/S4 → Canonical Fact → ObservationSnapshot 闭环）

> **报告编号**：`REPORT-PHASE2A-STEP3.2-20260930`  
> **报告版本**：v1.0.0-FINAL  
> **报告日期**：2026-09-30  
> **上位依据**：最高董事会工程授权令（`STEP 3.2 = AUTHORIZED WITH HARD BOUNDARIES`）  
> **实施范围**：**严格限定于 Sub-Step 3.2（M1/M2/M4/M5/S4 事实抽取适配器与 ObservationSnapshotBuilder 组装构建）。严格遵守“只转换、不决策”（Only Transform, No Decisions）铁律，零 LLM 运行时调用，零交易生产链接触，零数据库 Migration。**  
> **验收结论**：**100% PASSED**（适配器单测 7/7 全部通过，Step 3 综合测试 19/19 全部通过，全系统回归 63/63 全部通过，耗时 48.72s）。

---

## 一、 董事会硬约束与适配器工程落实逐条证据

Step 3.2 严格按照董事会授权令规定的十项硬指标逐一实现并闭环：

### 1. 严格恪守“只转换、不决策”（Only Transform, No Decisions）
- **工程动作**：所有适配器继承自 [`BaseFactAdapter`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/base.py)，仅负责原始数据解包、类型规范化、时间戳对齐与指纹计算；
- **红线遵守**：适配器**零 Eligibility 准入决策、零 Conflict Resolution 冲突裁决、零观点加工、零假设生成、零交易信号**。

### 2. M1 盘后复盘事实抽取规范（对齐裁决第五条）
- **模块实现**：[`M1ReviewFactAdapter`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/m1_adapter.py)；
- **落地事实项**：
  - 收盘指数（`indices.sh000001` 等）：精确绑定事件时间 `15:00:00`，未收录核心指数显式标记为 `MISSING`（payload 为 None）；
  - 市场广度（`breadth.summary`）：真实收录总成交额、上涨数、下跌数、平盘数；
  - 涨停梯队（`limit_up.pool`）：收录连板高度与涨停池；当涨停池为空时，按照 Step 3.1 契约准确输出合法 `FactStatus.EMPTY`（`limit_up_count=0`）。
- **测试证据**：[`test_01_m1_adapter_contract`](file:///d:/项目库/AI认知复盘交易系统/backend/tests/test_cognition_step3_adapters.py#L46-L95) PASSED。

### 3. M2 盘前宏观事实抽取规范（对齐裁决第五条）
- **模块实现**：[`M2PremarketFactAdapter`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/m2_adapter.py)；
- **落地事实项**：
  - 隔夜外盘（`macro.overnight`）：纯事实列表（纳指、道指、A50、恒指等）；
  - 宏观要闻（`macro.news_digest`）：纯原始文本事实，**零主观观点加工，零情绪润色**；
  - 盘前观察点（`macro.today_focus`）：纯客观观察维度与免责声明。
- **测试证据**：[`test_02_m2_adapter_contract`](file:///d:/项目库/AI认知复盘交易系统/backend/tests/test_cognition_step3_adapters.py#L97-L131) PASSED。

### 4. M4 早盘竞价 09:25 时间契约与零填充防伪（对齐裁决第五条）
- **模块实现**：[`M4AuctionFactAdapter`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/m4_adapter.py)；
- **落地事实项**：
  - 开盘指数（`auction.indices`）：严格将 `event_time` 锁定为 `09:25:00`，绝不与 `observed_time` 或盘中数据混淆；
  - 竞价量能比值（`auction.volume_ratio`）：当竞价总额缺失时，**强制置为 `MISSING` 且 `payload=None`，严禁填 `0.0 亿` 伪造**；
  - 高标开盘溢价（`auction.high_open_stats`）与一字板家数（`auction.one_word_count`）。
- **测试证据**：[`test_03_m4_0925_temporal_contract_and_no_zero_fill`](file:///d:/项目库/AI认知复盘交易系统/backend/tests/test_cognition_step3_adapters.py#L133-L173) PASSED。

### 5. M5 结算价超时与缓存降级真实状态保留（对齐裁决第五条）
- **模块实现**：[`M5SettlementFactAdapter`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/m5_adapter.py)；
- **落地事实项**：
  - Baostock 超时故障时，真实保留 `FactStatus.TIMEOUT`，`payload=None`；
  - 超时后读取本地缓存时，真实保留 `FactStatus.STALE` 与 `Freshness.STALE`，**绝不冒充 AVAILABLE**，并记录 `fallback_occurred=True`。
- **测试证据**：[`test_04_m5_settlement_timeout_and_stale_contract`](file:///d:/项目库/AI认知复盘交易系统/backend/tests/test_cognition_step3_adapters.py#L175-L210) PASSED。

### 6. S4 资讯双源与 Fallback 不是替换而是 Provenance（对齐裁决第四条）
- **模块实现**：[`S4NewsFactAdapter`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/s4_adapter.py)；
- **落地事实项**：
  - 当 CLS 超时切换至 Sina 备源时，在 [`Provenance`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/contracts.py#L112-L123) 完整保全：`primary_source="cls"`、`primary_error_detail="asyncio.TimeoutError"`、`fallback_source="sina"`、`fallback_reason="CLS_TIMEOUT_AFTER_5000MS"`；
  - 重复快讯到达时，记录 `duplicate_detected=True` 与 `duplicate_count`，保留 `original_arrival_order`，绝不静默删除原始证据。
- **测试证据**：[`test_05_s4_fallback_provenance_and_duplicate_preservation`](file:///d:/项目库/AI认知复盘交易系统/backend/tests/test_cognition_step3_adapters.py#L212-L248) PASSED。

### 7. 强制 Nested Immutability Gate（对齐裁决第六条）
- **工程动作**：在 [`BaseFactAdapter`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/base.py#L31-L36) 与 [`ObservationSnapshotBuilder`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/builder.py#L42-L46) 实施强制 `deep_detach` 深度解耦复制；
- **防护实测**：外部调用方在生成 `FactItem` 或 `ObservationSnapshot` 后，恶意原地修改传入的原始字典（如 `dict["indices"][0]["price"] = 99999.0`），已生成的内部快照与指纹**100% 保持完全不变（零污染）**。
- **测试证据**：[`test_06_nested_immutability_gate`](file:///d:/项目库/AI认知复盘交易系统/backend/tests/test_cognition_step3_adapters.py#L250-L272) PASSED。

### 8. 快照构建器装配与整体质量分层（对齐裁决第九条）
- **模块实现**：[`ObservationSnapshotBuilder`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/builder.py)；
- **聚合效果**：
  - 聚合 M1、M5 多源事实切片；
  - 自动运行 `aggregate_overall_quality`；当注入 STALE 事实时，快照整体质量确定性定格为 `QualityLevel.DEGRADED` 并记录降级字段 `settlement.600519`；
  - 自动固化 64 位 RFC 8785 JCS `snapshot_fingerprint`。
- **测试证据**：[`test_07_snapshot_builder_assembly_and_quality_aggregation`](file:///d:/项目库/AI认知复盘交易系统/backend/tests/test_cognition_step3_adapters.py#L274-L330) PASSED。

---

## 二、 Sub-Step 3.2 交付源码索引

```text
backend/app/cognition/observation/
├── adapters/
│   ├── __init__.py           # 适配器包导出定义
│   ├── base.py               # BaseFactAdapter 抽象基类 (强制 deep_detach 深度解耦)
│   ├── m1_adapter.py         # M1ReviewFactAdapter (收盘指数/广度/涨停池)
│   ├── m2_adapter.py         # M2PremarketFactAdapter (隔夜外盘/要闻客观提取)
│   ├── m4_adapter.py         # M4AuctionFactAdapter (09:25:00 竞价开盘与量能比)
│   ├── m5_adapter.py         # M5SettlementFactAdapter (结算价超时/缓存真实保留)
│   └── s4_adapter.py         # S4NewsFactAdapter (双源快讯与 Fallback Provenance)
└── builder.py                # ObservationSnapshotBuilder (嵌套不可变装配与整体质量聚合)
```

---

## 三、 测试执行证据链（Test Execution Evidence）

### 1. Step 3.2 适配器专项测试（[`test_cognition_step3_adapters.py`](file:///d:/项目库/AI认知复盘交易系统/backend/tests/test_cognition_step3_adapters.py)）
```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
collected 7 items

tests\test_cognition_step3_adapters.py::test_01_m1_adapter_contract PASSED [ 14%]
tests\test_cognition_step3_adapters.py::test_02_m2_adapter_contract PASSED [ 28%]
tests\test_cognition_step3_adapters.py::test_03_m4_0925_temporal_contract_and_no_zero_fill PASSED [ 42%]
tests\test_cognition_step3_adapters.py::test_04_m5_settlement_timeout_and_stale_contract PASSED [ 57%]
tests\test_cognition_step3_adapters.py::test_05_s4_fallback_provenance_and_duplicate_preservation PASSED [ 71%]
tests\test_cognition_step3_adapters.py::test_06_nested_immutability_gate PASSED [ 85%]
tests\test_cognition_step3_adapters.py::test_07_snapshot_builder_assembly_and_quality_aggregation PASSED [100%]

============================== 7 passed in 0.14s ==============================
```

### 2. Step 3 全量测试（契约 12 项 + 适配器 7 项 = 19 项全部通过）
```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
collected 19 items

tests\test_cognition_step3_contract.py::test_01 ~ test_12 PASSED [ 63%]
tests\test_cognition_step3_adapters.py::test_01 ~ test_07 PASSED [100%]

============================= 19 passed in 0.15s ==============================
```

### 3. 系统全量回归测试（63/63 项测试 100% 通过，耗时 48.72s）
覆盖 Track A 生产就绪、Step 1 WORM Hardening、Step 2 Hash Chain、Step 3.1 Contracts、Step 3.2 Adapters、P2 弹性容灾、Red Team 攻击及交易核心生命周期：
```text
======================= 63 passed, 4 warnings in 48.72s =======================
```
**零测试红灯，零功能回退！**

---

## 四、 当前工程边界与提请授权事项

### 1. 严格恪守的禁区状态
- **Sub-Step 3.3（Eligibility Engine & Prompt Renderer）**：**尚未启动，代码未写**；
- **LLM Runtime**：**零调用，零 SDK**；
- **交易链**：**零介入**；
- **M6 模块**：**维持 C 级架构缺口隔离**；
- **数据库**：**零 Migration**。

### 2. 提请最高董事会审议与授权
Sub-Step 3.2 事实抽取适配器已完全达成“无业务决策污染、无事实丢失、无 zero-fill、无 stale 冒充、无 fallback provenance 丢失、Nested Immutability 绝对保全”的准入标准。  
**提请董事会审议验收《Step 3.2 完成报告》，并签发 Sub-Step 3.3 工程授权令（准予受控开启 Eligibility 准入准出过滤网、多源冲突消解引擎与 Prompt 安全渲染器开发）。**
