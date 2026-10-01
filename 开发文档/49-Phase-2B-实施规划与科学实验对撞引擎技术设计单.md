# Phase 2B 实施规划与科学实验对撞引擎技术设计单
**文档编号**: `PLAN-PHASE2B-20261001`  
**实施项目**: Cognition Phase 2B — 科学实验、认知重放与五维差异对撞引擎  
**上位依据**:  
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》v1.2.1-FINAL (第6节 & 第9节)  
2. 《开发文档/48-Phase-2A-Step6-终局验收与红队审计总报告.md》  
**执行基准**: 纯沙箱实现（Pure Sandbox）、Zero LLM Runtime（试点前）、Zero Trading Side-Effect、Zero DB Migration  
**当前状态**: **PENDING BOARD REVIEW / 待董事会审议**  

---

## 一、 Phase 2B 背景与工程使命

在 Phase 2A 100% 验收封口后，系统已具备不可篡改、WORM 存证、四维时间解耦与事后证伪闭环的物理底座。

**Phase 2B 的核心使命**是构建**科学实验闭环（Scientific Experimentation Loop）**：
允许量化研究员与策略系统面对历史同一客观事实切片，换用新 Prompt、新模型或不同参数配置，实施“反事实（Counterfactual）”历史认知重放与差异对撞，回答关键问题：
> **“面对历史同一客观市场环境，换用新的认知推演策略，系统的假设质量与防御性是否发生了正向改善？”**

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Phase 2B 认知重放与科学差异对撞架构                             │
└────────────────────────────────────────────────────────────────────────────────────────┘

 [历史父记录 Parent CognitionRecord]
       │
       ├─ 提取: Historical ObservationSnapshot (事实基准 100% 不变)
       ├─ 提取: Historical MarketHypothesisDefinition (原假说基准)
       ├─ 载入: Target PromptSpec (可相同或升级)
       ├─ 载入: Target ModelSpec (可相同或升级)
       ├─ 载入: Target InferenceConfig (Seed, Temperature, ReplayType)
       ▼
┌────────────────────────────────────────────────────────┐
│  2B.2 Replay Runner (参数化重放执行器)                 │
└──────────────────────────┬─────────────────────────────┘
                           ▼
产生 [衍生记录 Derived CognitionRecord]
       │
       ├─ parent_cognition_id = Parent.cognition_id (严格指向父记录)
       ├─ replay_type = "EXACT_REPLAY" | "DIFF_SHADOW"
       └─ deterministic_level = 明确分级标注
                           │
                           ├─────────────────────────────┐
                           ▼                             ▼
┌────────────────────────────────────────────────────────┐│
│  2B.3 Cognition Diff Engine (五维差异对撞引擎)         ││
│  • Observation Diff: 事实关注点差异                    ││
│  • Reasoning Diff: 推演归因链条差异                    ││
│  • Hypothesis Diff: 假说命题与断言严格度差异            ││
│  • Confidence Diff: 置信度漂移检测 (过度自信识别)      ││
│  • Outcome Comparison Matrix: 结果对照矩阵 (无排行榜)  ││
└──────────────────────────┬─────────────────────────────┘│
                           ▼                             ▼
              [CognitionDiffReport 对照报告]    [Append-Only 衍生账本]
```

---

## 二、 Phase 2B 刚性工程不变量 (5 Invariants)

1. **WORM 绝不侵犯原则**:
   重放绝不修改原父记录。重放产生的新记录作为独立的衍生记录写入只追加账本，通过 `parent_cognition_id` 显式追溯父记录；
2. **四级确定性等级刚性分层 (Deterministic Level)**:
   摒弃“temperature=0 即等于绝对确定”的技术盲从，系统严格区分四级：
   - `BIT_EXACT`: 新响应与历史文本 SHA-256 二进制级 100% 吻合；
   - `SEMANTIC_EQUAL`: 文本微调，但提取出的结构化假说与断言 100% 等价；
   - `STOCHASTIC_DRIFT`: 相同配置下模型因 MoE 路由或随机性产生结论漂移；
   - `OFFLINE_FALLBACK`: 历史模型已下线，采用指定替代模型进行近似推演；
3. **无排行榜与严禁 Winner 评选**:
   彻底封杀 `winner_cognition_id`。差异对撞的本质是控制变量的科学对照实验，严禁粗暴评选胜负；
4. **控制变量事实保全**:
   重放执行器所摄入的 `ObservationSnapshot` 必须严格提取自原父记录，严禁重新实时拉取或篡改事实切片；
5. **Zero Trading / Zero DB Migration 刚性红线**:
   纯沙箱环境运行，严禁触碰交易接口、账户或订单系统，零新增数据库表结构迁移。

---

## 三、 Phase 2B 工序拆解与实施路线图

```text
Sub-Step 2B.1: 科学重放契约与确定性分级模型 (Replay Contracts)
  ├── 领域模型: ReplayConfig, DerivedCognitionRecord, DeterministicLevel
  └── 确定性判定算法: BitExact / SemanticEqual / StochasticDrift 判定逻辑

Sub-Step 2B.2: 参数化历史重放执行器 (Replay Runner)
  ├── 实现 ReplayRunner: 绑定历史 ObservationSnapshot 与升级 Prompt/ModelSpec
  ├── 确定性重放沙箱执行器与全血缘 parent_cognition_id 指针绑定
  └── 衍生假说与验证记录生成

Sub-Step 2B.3: 五维差异对撞引擎 (Cognition Diff Engine)
  ├── 模块 A: Observation Diff (事实覆盖面与质量警示差异)
  ├── 模块 B: Reasoning Diff (因果归因与命题倾向差异)
  ├── 模块 C: Hypothesis Diff (假说命题、断言阈值宽严对比)
  ├── 模块 D: Confidence Diff (模型主观置信度差异与过度自信识别)
  └── 模块 E: Outcome Comparison Matrix (证实/证伪/未决对照矩阵，无 winner)

Sub-Step 2B.4: 反事实实验编排与批量对撞流水线 (Experiment Orchestrator)
  ├── 批量处理历史交易日基线切片
  └── 生成结构化 CognitionDiffReport 报告与可视化卡片数据载荷

Sub-Step 2B.5: 全量端到端验收与 AST 架构静态扫描
  ├── 编制 test_cognition_phase2b_replay.py
  ├── 编制 test_cognition_phase2b_diff.py
  └── 扩充 test_cognition_static_architecture_scan.py (防线覆盖 replay/diff)
```

---

## 四、 核心数据模型规范

```python
class DeterministicLevel(str, Enum):
    BIT_EXACT = "BIT_EXACT"
    SEMANTIC_EQUAL = "SEMANTIC_EQUAL"
    STOCHASTIC_DRIFT = "STOCHASTIC_DRIFT"
    OFFLINE_FALLBACK = "OFFLINE_FALLBACK"

class ReplayType(str, Enum):
    EXACT_REPLAY = "EXACT_REPLAY"     # 历史同配置可复现检验
    DIFF_SHADOW = "DIFF_SHADOW"       # 控制变量反事实对照实验

class CognitionDiffReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    diff_id: str
    baseline_cognition_id: str
    experiment_cognition_id: str
    observation_diff: Dict[str, Any]
    reasoning_diff: Dict[str, Any]
    hypothesis_diff: Dict[str, Any]
    confidence_diff: Dict[str, Any]
    outcome_matrix: Dict[str, Any]
    has_winner_selection: bool = False  # 刚性恒为 False
    generated_at: str
```

---

## 五、 产物清单与交付计划

### 5.1 代码交付物清册
1. `backend/app/cognition/replay/__init__.py`: 重放包统一导出；
2. `backend/app/cognition/replay/contracts.py`: 确定性分级与重放配置模型；
3. `backend/app/cognition/replay/runner.py`: 历史切片参数化重放执行器；
4. `backend/app/cognition/diff/__init__.py`: 差异对撞包统一导出；
5. `backend/app/cognition/diff/contracts.py`: 五维差异对撞模型与报告规范；
6. `backend/app/cognition/diff/engine.py`: 五维差异计算引擎（绝对无排行榜）；
7. `backend/tests/test_cognition_phase2b_replay.py`: 重放确定性分级测试；
8. `backend/tests/test_cognition_phase2b_diff.py`: 五维对撞矩阵与反事实对比测试；
9. 更新 `backend/tests/test_cognition_static_architecture_scan.py`。

---

## 六、 提请董事会授权事项

工程团队特此提请董事会：
1. **审议并批准《PLAN-PHASE2B-20261001》作为 Cognition Phase 2B 的法定工程实施依据**；
2. **授权启动 Phase 2B Sub-Step 2B.1 与 2B.2 的代码实施与测试编写**；
3. **重申执行纯沙箱实现（Pure Sandbox），严禁 LLM Runtime 与 Trading 泄漏**。
