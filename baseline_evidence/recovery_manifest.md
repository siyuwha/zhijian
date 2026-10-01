# 物理恢复点凭证清单（Recovery Point Manifest）

> **归档位置**：`baseline_evidence/recovery_manifest.md`  
> **建立阶段**：CONTROL-RESET-01 治理行动（EG-00 步骤，约束 1 先行执行）  
> **生成时间**：2026-10-01 22:33:57 CST  
> **状态**：物理封存，外部存档（不在 Git 版本控制中跟踪二进制包）  

---

## 一、恢复点元数据

为防止 Git 仓库历史体积膨胀（避免每次治理/快照污染仓库历史），物理压缩包置于本地及外部存储，Git 仓库仅追踪本元数据凭证清单与校验哈希。

| 字段 | 属性值 | 说明 |
| :--- | :--- | :--- |
| **快照文件名** | `level1_recovery_point_20261001_223357.zip` | 治理前全工作区未提交状态完整打包 |
| **物理存储路径** | `baseline_evidence/recovery_points/level1_recovery_point_20261001_223357.zip` | 本地文件系统 / NAS 外部归档备份 |
| **文件大小** | 1,783,817 字节 (约 1.70 MB) | 包含 268 个文件 |
| **创建时间** | 2026-10-01 22:34:01 CST | 代码修改前第一优先级执行 |
| **SHA-256 哈希** | `4506A70E2F0D67E31C65E6E760F292BC74FBF5D680884053B82A63CAB0F70DDF` | 物理防篡改校验哈希 |

---

## 二、快照所包含的核心资产范围

该恢复点冻结了 CONTROL-RESET-01 开始前工作区的完整原始状态，包括：
1. **未跟踪认知引擎核心代码**：`backend/app/cognition/` 下全部实现与 DSL 约束（JCS、Hash Chain、Hypothesis、Diff、Replay）；
2. **Phase 2A 契约与红队测试套件**：`backend/tests/` 下 `test_cognition_*.py` 等 13 个测试文件；
3. **架构审计与设计文档**：根目录下 `00`~`09` 系列审计与整改文档、`开发文档/28`~`49` 架构设计单；
4. **盘股资产证据卡**：`knowledge_cards/` 目录下全部知识资产提取卡。

---

## 三、快速回滚操作指南（Rollback Procedure）

若未来任何时候需要无损回滚至 CONTROL-RESET-01 治理前状态，仅需执行以下操作：

```powershell
# 1. 校验恢复包完整性
Get-FileHash "baseline_evidence\recovery_points\level1_recovery_point_20261001_223357.zip"
# 必须匹配: 4506A70E2F0D67E31C65E6E760F292BC74FBF5D680884053B82A63CAB0F70DDF

# 2. 清理当前工作区未跟踪文件（慎用）
# git clean -fd
# git checkout .

# 3. 将恢复包解压覆盖至项目根目录
Expand-Archive -Path "baseline_evidence\recovery_points\level1_recovery_point_20261001_223357.zip" -DestinationPath "." -Force
```
