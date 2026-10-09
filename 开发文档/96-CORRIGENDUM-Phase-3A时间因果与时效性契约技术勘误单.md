# 【技术勘误单 · CORRIGENDUM-DOC-96-01】Phase 3A 时间因果与时效性契约技术勘误

**勘误编号：** `CORRIGENDUM-DOC-96-01-20261009`  
**关联裁决：** 最高董事会《VERDICT-PHASE3A-CLOSE-PHASE3B1-GATE-20261009》第一条第 3 款  
**被勘误对象：** DOC-96 / DOC-97 中关于四维时间因果与新鲜度计算的技术描述  
**签署生效：** 研发中枢 (`fe71a91e-b398-4fee-8916-0b6a1f009657`)  
**密级状态：** 永久归档基线技术勘误  

---

## 一、 勘误背景与缺陷界定

在早前 DOC-97 及初步时序测试中，研发团队将时间因果简述为 $T_{hypothesis} < T_{observed} \le T_{evaluated} \le T_{requested}$，并将新鲜度定义为 $|T_{evaluated} - T_{observed}|$。最高董事会敏锐指出此定义的逻辑缺陷：
1. **未区分实时在线求值与缓存命中场景的时序颠倒**：
   - 在实时求值场景下，必须是客户端先发起 HTTP 请求，服务端接收到请求后方才触发波普尔引擎求值，故物理上应当是 $T_{requested} \le T_{evaluated}$；
   - 仅在预先计算好的缓存命中场景下，$T_{evaluated}$ 方可先于 $T_{requested}$。
2. **时效性与数据新鲜度的虚假归零**：
   - 原测试中若将 $T_{evaluated}$ 与 $T_{observed}$ 均设置为请求快照时间字符串（如 `"10:00:00"`），两者的差值必然恒等于 0，但这并非真实的数据年龄（Data Age），属于概念偷换。

---

## 二、 勘误后的规范时间因果全序契约 (Corrected Temporal Axioms)

### 1. 核心时戳定义
- **$T_{hypothesis}$（假说登记时戳）**：基准日（T-1日）复盘战报归档固化时间（如 `2026-10-08T18:00:00+08:00`）。
- **$T_{observed}$（物理观测采样时戳）**：连续竞价微观行情切片的真实物理采集时戳（如 `2026-10-09T10:00:00+08:00`）。
- **$T_{requested}$（请求到达时戳）**：客户端发起的 API 请求到达网关或服务端的瞬时物理时戳。
- **$T_{evaluated}$（判定执行时戳）**：波普尔判定器执行证伪逻辑并得出对账结果的物理时戳。

### 2. 双场景全序公理
#### 场景 A：实时未命中 / 在线即时求值 (Cache Miss / Live Evaluation)
客户端先发起请求，服务端随后调起引擎求值：
$$T_{hypothesis} < T_{observed} \le T_{requested} \le T_{evaluated}$$

#### 场景 B：预计算 / 缓存命中 (Cache Hit)
服务端已先于请求生成判定并缓存，客户端随后查询：
$$T_{hypothesis} < T_{observed} \le T_{evaluated} \le T_{requested}$$

### 3. 规范数据新鲜度与时效性定义 (Physical Data Age)
- **物理数据年龄 (Physical Data Age)**：
  $$\text{Data Age} = T_{requested} - T_{observed}$$
- **缓存驻留年龄 (Cache Dwell Age)**：
  $$\text{Cache Age} = T_{requested} - T_{evaluated}$$
- **时效性分级标准**：
  - **FRESH（新鲜）**：$\text{Data Age} \le 180\text{s}$（3分钟以内）；
  - **DELAYED / STALE（延迟预警）**：$180\text{s} < \text{Data Age} \le 600\text{s}$（发出黄色时效降级警告）；
  - **EXPIRED（过期作废）**：$\text{Data Age} > 600\text{s}$（强制清退缓存并阻断实时决策）。

---

## 三、 测试门禁勘误与全覆盖验证

研发团队已同步修正 [`backend/tests/test_phase3a_temporal_and_freshness_gates.py`](file:///d:/项目库/AI认知复盘交易系统/backend/tests/test_phase3a_temporal_and_freshness_gates.py)，增补包含：
1. `test_gate_temporal_live_evaluation_causality`: 验证在线求值 $T_{requested} \le T_{evaluated}$；
2. `test_gate_temporal_cached_evaluation_causality`: 验证缓存命中 $T_{evaluated} \le T_{requested}$；
3. `test_gate_temporal_physical_data_age_calculation`: 验证真实物理数据年龄 $\text{Data Age}$ 计算；
4. `test_gate_temporal_delayed_data_staleness_flag`: 验证超出 180s 延迟数据精准识别；
5. `test_gate_temporal_cache_expiration_and_recomputation`: 验证过期自动淘汰与重算。

本勘误单作为系统永久基线资产予以封存。
