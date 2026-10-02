"""
Phase 2B.2: 假说提议提示词规范与 WORM 模板管理器 (PromptSpec)
上位依据：《开发文档/56-Phase-2B.2-受约束LLM认知假说提议器契约设计单.md》

核心职责：
1. 提供不可变版本化的 PromptSpec 实体；
2. 明确指示 LLM 遵守输出 JSON Schema、宏观白名单指标与波普尔证伪原则；
3. 计算并绑定 Prompt SHA-256 哈希，供 CognitionRecord 溯源链锚定。
"""

import json
import hashlib
from typing import Dict, Any
from pydantic import BaseModel, ConfigDict, Field


SYSTEM_ROLE_PROMPT = """你是一个专业的 A 股宏观市场认知与情绪周期推演引擎（Cognitive Hypothesis Proposer）。
你的职责是在收盘复盘事实（M1/M2）的基础上，提出对下一个交易日市场宏观演绎的科学假说。

【必须严格遵守的铁律】：
1. 你只负责提出假说，绝无裁判权，严禁使用模糊不可度量的词汇；
2. 绝对禁止给出个股推荐、买卖指令、加减仓建议或目标价（严防交易预测）；
3. 标的仅限全A宏观聚合('ALL_A')或主要宽基指数('sh000001', 'sz399001', 'sz399006', 'sh000688')；
4. 指标必须来自白名单：limit_up_count, limit_down_count, pct_change, open_pct_change, turnover_ratio, board_height, up_count, down_count；
5. 操作符仅限：GT, GTE, LT, LTE, EQ, BETWEEN；
6. 必须至少提供一条刚性证伪红线断言(invalidation_assertions)——触碰红线即代表假说被客观证伪！
7. 必须仅输出符合指定 JSON Schema 的纯 JSON 对象，严禁包裹任何 Markdown 标记或多余解释文字。

【输出规范：必须严格遵守以下 JSON 键名与嵌套结构（所有键名必须完全一致）】：
{
  "target_date": "YYYY-MM-DD",
  "hypothesis_type": "SENTIMENT_CYCLE 或 INDEX_TREND 或 MARKET_STATE 或 BREADTH_TREND",
  "target_asset": "推演标的宏观对象描述 (如: 全市场短线投机生态 或 上证指数)",
  "expected_scenario": "预期演绎形态 (如: REBOUND 或 DIVERGENCE 等)",
  "premise_logic": "前置支撑逻辑说明（字符串）",
  "expected_phenomenon": "预期盘面宏观现象说明（字符串）",
  "expected_assertions": [
    {
      "assertion_id": "exp_1",
      "metric_type": "limit_up_count 等白名单指标",
      "target_code": "ALL_A 或主要宽基代码",
      "operator": "GT 或 GTE 或 LT 或 LTE 或 EQ",
      "threshold": 40.0,
      "description": "断言可读说明"
    }
  ],
  "invalidation_condition": "失效条件自然语言总结（字符串）",
  "invalidation_assertions": [
    {
      "assertion_id": "inv_1",
      "metric_type": "limit_down_count 等白名单指标",
      "target_code": "ALL_A 或主要宽基代码",
      "operator": "GT 或 GTE 或 LT 或 LTE 或 EQ",
      "threshold": 50.0,
      "description": "断言可读说明"
    }
  ],
  "explanation": "推理补充说明（字符串）"
}
"""

USER_OBSERVATION_TEMPLATE = """请基于以下 {market_date} 的真实收盘事实切片，推演下一个交易日 ({target_date}) 的宏观市场假说：

【今日收盘核心事实】：
- 主要宽基指数表现: {indices_summary}
- 短线情绪与涨跌停: 涨停 {limit_up_count} 家, 跌停 {limit_down_count} 家, 连板高度 {max_board_height} 板, 炸板率 {broken_ratio}
- 全市场涨跌广度: 上涨 {up_count} 家, 下跌 {down_count} 家
- 市场物理状态定性: {state_label}

请严格输出纯 JSON 对象，target_date 请填入 "{target_date}"，严格使用上述规范中的键名。"""


class PromptSpec(BaseModel):
    """不可变提示词规范定义"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_id: str = "PROMPT_COGNITION_HYPOTHESIS_V1"
    version: str = "1.1.0"
    system_prompt: str = Field(default=SYSTEM_ROLE_PROMPT)
    user_template: str = Field(default=USER_OBSERVATION_TEMPLATE)
    prompt_hash: str = ""

    @classmethod
    def create_canonical(cls) -> "PromptSpec":
        """创建带有标准化 SHA-256 指纹的规范实例"""
        content_for_hash = f"{cls.model_fields['prompt_id'].default}_{cls.model_fields['version'].default}_{SYSTEM_ROLE_PROMPT}_{USER_OBSERVATION_TEMPLATE}"
        p_hash = hashlib.sha256(content_for_hash.encode("utf-8")).hexdigest()
        return cls(prompt_hash=p_hash)

    def render_user_prompt(self, obs: Dict[str, Any], target_date: str) -> str:
        """根据真实客观事实切片安全渲染用户提示词"""
        indices_list = obs.get("indices", [])
        idx_strs = [f"{i.get('name', i.get('code'))}: {i.get('pct_change')}%" for i in indices_list]
        idx_summary = ", ".join(idx_strs) if idx_strs else "暂无"

        lu_info = obs.get("limit_up_summary", {})
        breadth_info = obs.get("breadth", {})
        ms_info = obs.get("market_state", {})

        return self.user_template.format(
            market_date=obs.get("market_date", "T日"),
            target_date=target_date,
            indices_summary=idx_summary,
            limit_up_count=lu_info.get("total_limit_up", 0),
            limit_down_count=lu_info.get("limit_down_count", 0),
            max_board_height=lu_info.get("max_board_height", 0),
            broken_ratio=f"{float(lu_info.get('broken_ratio', 0) or 0)*100:.1f}%",
            up_count=breadth_info.get("up_count", 0),
            down_count=breadth_info.get("down_count", 0),
            state_label=ms_info.get("state_label", "平稳中性"),
        )
