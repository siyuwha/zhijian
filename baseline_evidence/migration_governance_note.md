# Alembic 迁移体系治理声明（Migration Governance Note）

> **归档位置**：`baseline_evidence/migration_governance_note.md`  
> **生效阶段**：CONTROL-RESET-01 工程基线治理  
> **关联版本**：`d440da877b6a` (p2_track_a_and_cognition_phase2a_baseline)  
> **归档时间**：2026-10-01 23:35:00 CST  

---

## 一、治理背景与现状说明

在执行 CONTROL-RESET-01 状态重建与治理期间，发现迁移文件 `backend/migrations/versions/d440da877b6a_p2_track_a_and_cognition_phase2a_.py` 存在以下工程现实：
1. **历史遗留多源状态**：工作区中存在带数据的早期物理库（已有部分历史表），同时也存在全新空库部署需求；
2. **空库验证障碍**：若直接运行原始自动生成的 `d440da877b6a`，其针对历史表的 `batch_alter_table` 在空库上会抛出 `NoSuchTableError`，导致空库迁移不可用，且原先必须依赖应用启动时的 `Base.metadata.create_all()` 兜底；
3. **约束限制**：依据人工批准的《CONTROL-RESET-01 治理行动》**约束 2**（“Alembic 不允许大改造，本轮只允许修复验证障碍，不重新设计迁移体系”），本轮严禁将单迁移重写为 `0001`~`0003` 多版本修订链。

---

## 二、当前版本（d440da877b6a）的技术处理界定

为了在不破坏约束 2 的前提下扫清验证障碍，我们在 `d440da877b6a` 中采取了**最小验证修复（Minimal Validation Fix）**方案：
- 在 `upgrade()` 起始位置通过 `inspector.get_table_names()` 探测物理表；
- 针对空库，自动通过 `Base.metadata.sorted_tables` 补齐基础表定义；
- 针对历史表 `alter` 逻辑，增加表存在性前置断言保护；
- 在迁移末尾以幂等方式部署 5 项 WORM 物理触发器及 `cognition_chain_state` 创世记录（Genesis Record）。

---

## 三、架构边界与永久性规范声明（Architecture Boundary Declaration）

本治理声明正式确立以下工程原则，防止未来开发者或智能体误读迁移职责：

### 1. 过渡性声明（Transitional Nature）
> **`d440da877b6a` 是 Phase 2A 历史状态向可复核工程基线收口的【过渡兼容迁移】，绝不代表系统未来的标准迁移范式！**

### 2. 三大禁止红线（Migration Prohibitions）
- ❌ **严禁在未来迁移中复制此模式**：后续任何业务迭代，严禁在新的 migration 中调用 `Base.metadata.create_all` 隐式建表；
- ❌ **严禁继续向 `d440da877b6a` 堆叠逻辑**：本文件已作为工程基线资产冻结，除紧急修复语法错误外，不得再追加新的表或触发器；
- ❌ **严禁绕过 Alembic 产生隐式 DDL**：生产与测试环境的表结构演进，必须完全基于显式的 `op.create_table`、`op.add_column` 等原子操作。

### 3. 未来重构路线（Future Milestone Plan）
在通过人工架构审核并正式进入生产架构重整阶段后，本过渡迁移应当按照标准规范被重构为清晰线性的多版本迁移链：
- `0001_legacy_core_schema.py`：基础业务与历史交易表；
- `0002_track_a_market_resilience.py`：市场快照与结算缓存表；
- `0003_cognition_phase2a_worm.py`：不可变认知账本、WORM 触发器与创世锚点。

---

> **结论**：当前 `d440da877b6a` 仅用于确保本地测试沙箱与空库环境能够以零外部依赖通过 `alembic upgrade head` 形成一致的物理验证态。
