"""
Phase 2B.2: 隔离沙箱认知假说提议驱动器 (SandboxProposer)
上位依据：《开发文档/56-Phase-2B.2-受约束LLM认知假说提议器契约设计单.md》

核心职责：
1. 在沙箱环境中驱动 LLM 提议流程（支持可插拔生成器函数与测试 Mock）；
2. 串联：Observation 渲染 -> PromptSpec 生成 -> LLM 推演调用 -> ProposalValidator 契约审计 -> AST 编译；
3. 保证在无外部网络/无真实 API Key 状态下，实现 100% 确定性离线回归测试；
4. 真实 API Key 接入时仅作为生成器驱动函数插入，业务架构零修改。
"""

import json
from typing import Dict, Any, Callable, Optional, Tuple
from pydantic import BaseModel, ConfigDict

from .prompt_spec import PromptSpec
from .proposal_validator import ProposalValidator, ProposalValidationResult
from ...schemas.cognition import MarketHypothesisCreate


class ProposerExecutionRecord(BaseModel):
    """沙箱提议执行审计记录不可变值对象"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    market_date: str
    target_date: str
    prompt_spec_version: str
    prompt_hash: str
    rendered_prompt: str
    raw_llm_response: str
    is_valid: bool
    validation_error_code: Optional[str] = None
    validation_error_detail: Optional[str] = None
    compiled_hypothesis: Optional[MarketHypothesisCreate] = None


class SandboxProposer:
    """沙箱认知假说提议执行器"""

    def __init__(self, prompt_spec: Optional[PromptSpec] = None):
        self.prompt_spec = prompt_spec or PromptSpec.create_canonical()

    def propose(
        self,
        observation: Dict[str, Any],
        target_date: str,
        generator_fn: Callable[[str, str], str],
    ) -> ProposerExecutionRecord:
        """
        执行受约束的假说提议管道：
        1. 渲染 Prompt；
        2. 调用 generator_fn（可在测试中使用 Mock，生产中使用真实 LLM Client）；
        3. 经过 ProposalValidator 强校验；
        4. 返回包含完整审计痕迹的 ProposerExecutionRecord。
        """
        market_date = observation.get("market_date", "")
        rendered_prompt = self.prompt_spec.render_user_prompt(observation, target_date)

        # 调用提议生成器
        raw_response = generator_fn(self.prompt_spec.system_prompt, rendered_prompt)

        # 解析 JSON
        try:
            # 清理可能存在的代码块包装
            cleaned_resp = raw_response.strip()
            if cleaned_resp.startswith("```json"):
                cleaned_resp = cleaned_resp[7:]
            elif cleaned_resp.startswith("```"):
                cleaned_resp = cleaned_resp[3:]
            if cleaned_resp.endswith("```"):
                cleaned_resp = cleaned_resp[:-3]
            cleaned_resp = cleaned_resp.strip()

            parsed_proposal = json.loads(cleaned_resp)
        except Exception as e:
            return ProposerExecutionRecord(
                market_date=market_date,
                target_date=target_date,
                prompt_spec_version=self.prompt_spec.version,
                prompt_hash=self.prompt_spec.prompt_hash,
                rendered_prompt=rendered_prompt,
                raw_llm_response=raw_response,
                is_valid=False,
                validation_error_code="VR-01_JSON_PARSE_FAILED",
                validation_error_detail=f"输出无法解析为合法 JSON: {str(e)}",
                compiled_hypothesis=None,
            )

        # 提交 ProposalValidator 严格准入审计
        val_res: ProposalValidationResult = ProposalValidator.validate_and_compile(
            raw_proposal=parsed_proposal,
            market_date=market_date,
        )

        return ProposerExecutionRecord(
            market_date=market_date,
            target_date=target_date,
            prompt_spec_version=self.prompt_spec.version,
            prompt_hash=self.prompt_spec.prompt_hash,
            rendered_prompt=rendered_prompt,
            raw_llm_response=raw_response,
            is_valid=val_res.is_valid,
            validation_error_code=val_res.error_code,
            validation_error_detail=val_res.error_detail,
            compiled_hypothesis=val_res.compiled_hypothesis,
        )
