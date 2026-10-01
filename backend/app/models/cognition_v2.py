"""
Cognition Phase 2A 核心不可变认知账本与控制状态模型
依据：《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》(v1.2.1-FINAL-CLOSURE)
     《开发文档/29-Cognition-Phase2A架构与数据契约冻结决议与实施约束单.md》

核心表结构：
1. cognition_record: 核心不可变认知账本表 (Aggregate Root, JCS RFC 8785 覆盖, Hash Chain 串接)
2. cognition_chain_state: 账本链全局控制表 (Gapless Monotonic Sequence, 防 Genesis 竞态)
3. cognition_prompt_spec: 不可变 Prompt 规格表 (WORM 范式)
4. cognition_diff_report: 对撞报告持久化表 (预留结构)
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    Float,
    String,
    Text,
    DateTime,
    Index,
    func,
    event,
)
from ..core.database import Base


class CognitionRecord(Base):
    """
    核心不可变认知账本表 (Phase 2A 聚合根)
    WORM 存储原则：记录一旦写入，禁止任何 UPDATE 或 DELETE 操作。
    """
    __tablename__ = "cognition_record"

    # 主键与业务时点
    id = Column(String(64), primary_key=True)                      # cog_YYYYMMDD_HHMMSS_xxxx
    date = Column(String(10), nullable=False, index=True)          # YYYY-MM-DD
    stage = Column(String(20), nullable=False)                     # PRE_MARKET / INTRADAY / POST_CLOSE
    timestamp = Column(DateTime, nullable=False)

    # 四维时间解耦物理列
    market_event_time = Column(String(20), nullable=False)         # 物理事件时点 (如 15:00:00)
    observation_window = Column(String(50), nullable=False)        # 观测窗口 (如 09:15:00-09:25:00)
    data_snapshot_time = Column(DateTime, nullable=False)          # 事实快照落库时点 (如 15:05:22)
    verification_execute_time = Column(DateTime, nullable=True)     # 验证执行触发时点 (如 15:30:00，未执行前为 NULL)

    # 只读快照投影 (JCS Canonical JSON)
    observation_snapshot = Column(Text, nullable=False)
    market_state_snapshot = Column(Text, nullable=False)

    # 不可变工件引用 (Self-contained Auditability)
    prompt_id = Column(String(50), nullable=False)
    prompt_version = Column(String(20), nullable=False)
    prompt_hash = Column(String(64), nullable=False)               # SHA-256
    model_provider = Column(String(30), nullable=False)
    model_name = Column(String(50), nullable=False)
    model_version = Column(String(50), nullable=False)
    inference_config = Column(Text, nullable=False)                 # JSON

    # 生效推理输入保全
    effective_input_hash = Column(String(64), nullable=False)      # SHA-256
    rendered_system_prompt = Column(Text, nullable=False)
    rendered_user_prompt = Column(Text, nullable=False)

    # 输出与结构化认知
    raw_response = Column(Text, nullable=False)
    response_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    structured_cognition = Column(Text, nullable=False)             # JSON: {thesis, rationale, self_assessed_conf, ...}

    # 假说集合哈希
    hypothesis_set_hash = Column(String(64), nullable=False)       # SHA-256 (全量派生假说定义投影集合哈希)

    # 真正的链式审计与血缘
    sequence_id = Column(BigInteger, nullable=False, unique=True, index=True) # 严格自增单调连续序号 (防漏防删)
    previous_record_hash = Column(String(64), nullable=False)      # 前驱哈希 (创世记录为 64个0)
    payload_hash = Column(String(64), nullable=False)              # 本记录全要素 Canonical Payload 哈希
    record_hash = Column(String(64), nullable=False, unique=True)  # SHA256(JCS({"payload_hash": ..., "previous_record_hash": ...}))

    parent_cognition_id = Column(String(64), nullable=True)        # 重放来源
    replay_type = Column(String(20), default="ORIGINAL", nullable=False)     # ORIGINAL / EXACT_REPLAY / DIFF_SHADOW
    deterministic_level = Column(String(30), nullable=True)        # BIT_EXACT / SEMANTIC_EQUAL / STOCHASTIC_DRIFT

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_cog_date_stage", "date", "stage"),
        Index("idx_cog_seq", "sequence_id"),
    )


class CognitionChainState(Base):
    """
    账本链全局控制表 (C-04 核心新增: 杜绝 Genesis Race 与并发空洞)
    单行控制表：通过单行行锁实现入账排他串行化。
    """
    __tablename__ = "cognition_chain_state"

    chain_id = Column(String(32), primary_key=True)                # 默认 'MAIN_LEDGER'
    tail_sequence_id = Column(BigInteger, nullable=False, default=0) # 当前链尾序号 (创世初始化为 0)
    tail_record_hash = Column(String(64), nullable=False, default="0"*64) # 当前链尾哈希 (创世初始化为 64个0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class CognitionPromptSpec(Base):
    """
    不可变 Prompt 规格表 (WORM 范式)
    模板一旦落库，禁止原地修改。变更模板必须生成新版本与新 Hash。
    """
    __tablename__ = "cognition_prompt_spec"

    id = Column(String(64), primary_key=True)                      # prompt_id + "@" + version
    prompt_id = Column(String(50), nullable=False)
    version = Column(String(20), nullable=False)
    prompt_hash = Column(String(64), nullable=False, unique=True)  # SHA-256
    system_template = Column(Text, nullable=False)
    user_template = Column(Text, nullable=False)
    input_schema = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class CognitionDiffReport(Base):
    """
    认知对撞差异报告持久化表 (Phase 2B 预留存储模型)
    """
    __tablename__ = "cognition_diff_report"

    id = Column(String(64), primary_key=True)
    base_cognition_id = Column(String(64), nullable=False)
    target_cognition_id = Column(String(64), nullable=False)
    diff_matrix = Column(Text, nullable=False)                     # JSON: 五维差异对比与结果对照矩阵
    summary_analysis = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# =========================================================================
# WORM 第一道物理防线：数据库引擎原生 DDL 触发器 (Database-Level WORM Triggers)
# 任何绕过 SQLAlchemy ORM 的原生 SQL UPDATE/DELETE 均会被 SQLite 引擎直接抛错中止
# =========================================================================

from sqlalchemy import text

DATABASE_WORM_TRIGGERS_SQL = [
    # 1. 物理阻断对 cognition_record 的任何 UPDATE
    """
    CREATE TRIGGER IF NOT EXISTS trg_cognition_record_no_update
    BEFORE UPDATE ON cognition_record
    BEGIN
        SELECT RAISE(ABORT, 'DATABASE WORM VIOLATION: cognition_record is immutable. Direct SQL UPDATE operations are strictly prohibited at database engine level.');
    END;
    """,
    # 2. 物理阻断对 cognition_record 的任何 DELETE
    """
    CREATE TRIGGER IF NOT EXISTS trg_cognition_record_no_delete
    BEFORE DELETE ON cognition_record
    BEGIN
        SELECT RAISE(ABORT, 'DATABASE WORM VIOLATION: cognition_record is immutable. Direct SQL DELETE operations are strictly prohibited at database engine level.');
    END;
    """,
    # 3. 物理阻断对 cognition_prompt_spec 的任何 UPDATE
    """
    CREATE TRIGGER IF NOT EXISTS trg_cognition_prompt_spec_no_update
    BEFORE UPDATE ON cognition_prompt_spec
    BEGIN
        SELECT RAISE(ABORT, 'DATABASE WORM VIOLATION: cognition_prompt_spec is immutable. Direct SQL UPDATE operations are strictly prohibited at database engine level.');
    END;
    """,
    # 4. 物理阻断对 cognition_prompt_spec 的任何 DELETE
    """
    CREATE TRIGGER IF NOT EXISTS trg_cognition_prompt_spec_no_delete
    BEFORE DELETE ON cognition_prompt_spec
    BEGIN
        SELECT RAISE(ABORT, 'DATABASE WORM VIOLATION: cognition_prompt_spec is immutable. Direct SQL DELETE operations are strictly prohibited at database engine level.');
    END;
    """,
    # 5. 物理阻断对 cognition_chain_state 控制行的任何 DELETE
    """
    CREATE TRIGGER IF NOT EXISTS trg_cognition_chain_state_no_delete
    BEFORE DELETE ON cognition_chain_state
    BEGIN
        SELECT RAISE(ABORT, 'DATABASE WORM VIOLATION: cognition_chain_state is permanent ledger anchor. Direct SQL DELETE operations are strictly prohibited at database engine level.');
    END;
    """
]

def install_database_worm_triggers_sync(conn):
    """在同步连接上安装原生数据库触发器"""
    for trigger_sql in DATABASE_WORM_TRIGGERS_SQL:
        conn.execute(text(trigger_sql))

async def install_database_worm_triggers_async(async_conn):
    """在异步连接上安装原生数据库触发器"""
    for trigger_sql in DATABASE_WORM_TRIGGERS_SQL:
        await async_conn.execute(text(trigger_sql))

# 自动绑定表创建事件：只要 Base.metadata.create_all 执行，自动在 DB 引擎层面安装触发器
@event.listens_for(CognitionRecord.__table__, "after_create")
def _on_cognition_record_create(target, connection, **kw):
    connection.execute(text(DATABASE_WORM_TRIGGERS_SQL[0]))
    connection.execute(text(DATABASE_WORM_TRIGGERS_SQL[1]))

@event.listens_for(CognitionPromptSpec.__table__, "after_create")
def _on_cognition_prompt_spec_create(target, connection, **kw):
    connection.execute(text(DATABASE_WORM_TRIGGERS_SQL[2]))
    connection.execute(text(DATABASE_WORM_TRIGGERS_SQL[3]))

@event.listens_for(CognitionChainState.__table__, "after_create")
def _on_cognition_chain_state_create(target, connection, **kw):
    connection.execute(text(DATABASE_WORM_TRIGGERS_SQL[4]))

# =========================================================================
# WORM 第二道逻辑防线：SQLAlchemy ORM 级事件监听拦截 (Defense-in-Depth)
# =========================================================================

@event.listens_for(CognitionRecord, "before_update")
def _guard_cognition_record_update(mapper, connection, target):
    raise RuntimeError("WORM Violation: CognitionRecord is immutable. UPDATE operations are strictly prohibited.")

@event.listens_for(CognitionRecord, "before_delete")
def _guard_cognition_record_delete(mapper, connection, target):
    raise RuntimeError("WORM Violation: CognitionRecord is immutable. DELETE operations are strictly prohibited.")

@event.listens_for(CognitionPromptSpec, "before_update")
def _guard_cognition_prompt_spec_update(mapper, connection, target):
    raise RuntimeError("WORM Violation: CognitionPromptSpec is immutable. UPDATE operations are strictly prohibited.")

@event.listens_for(CognitionPromptSpec, "before_delete")
def _guard_cognition_prompt_spec_delete(mapper, connection, target):
    raise RuntimeError("WORM Violation: CognitionPromptSpec is immutable. DELETE operations are strictly prohibited.")

@event.listens_for(CognitionChainState, "before_delete")
def _guard_cognition_chain_state_delete(mapper, connection, target):
    raise RuntimeError("WORM Violation: CognitionChainState is permanent ledger anchor. DELETE operations are strictly prohibited.")
