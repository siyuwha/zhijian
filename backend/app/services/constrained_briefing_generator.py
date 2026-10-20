"""
Phase 2D.3-C: Constrained Briefing Generator Service
===================================================
上位依据：
1. 最高董事会 2026-10-09 裁决令：《Phase 2D.3-C 授权与受约束 LLM 战报规范》
2. 《DOC-80 · Phase 2D.3 受约束 LLM 实战战报生成器技术设计单》

核心职责：
- 严格基于 NarrativeContextContract 构建具有发言边界刚性约束的系统与用户 Prompt；
- 贯彻【大势定调】、【主线与梯队】、【风险与负反馈】、【明日推演与防守红线】四段式操盘内参范式；
- 全流程受 BriefingSafetyGuard 审查；审查不通过或生成异常无感触发 DeterministicBriefingFallbackEngine；
- 支持自适应处理不同微观市场周期 (如 10-08 高位剧烈分化期 vs 10-01 主升共振期)。
"""

from typing import Optional, Dict, Any, List, Callable
from datetime import datetime

from backend.app.schemas.narrative_context import NarrativeContextContract
from backend.app.schemas.tactical_briefing import TacticalBriefingReport, SafetyAuditResult
from backend.app.services.briefing_safety_guard import BriefingSafetyGuard
from backend.app.services.briefing_fallback_engine import DeterministicBriefingFallbackEngine
from backend.app.services.tactical_briefing_service import TacticalBriefingService
from backend.app.schemas.canonical_market import MarketStateEnum


class BriefingPromptBuilder:
    """
    受约束 Prompt 构建器 (Prompt Speech Boundary Builder)
    """

    @staticmethod
    def build_system_prompt(contract: NarrativeContextContract) -> str:
        """
        构建包含显式发言边界与红线约束的 System Prompt
        """
        allowed = "\n  - ".join(contract.speech_boundary.allowed_claim_types)
        forbidden = "\n  - ".join(contract.speech_boundary.forbidden_claim_types)
        anchors = "\n  - ".join(contract.speech_boundary.required_evidence_anchors)

        return f"""你是一位拥有20年实战经验的顶级游资操盘手与头部券商特邀宏观策略内参首席顾问。
你的任务是根据系统提供的只读量化事实与认知假说，撰写一份冷峻、精炼、穿透力强、直击资金本质的【操盘内参实战战报】。

【刚性红线与发言边界】：
1. 允许声明类型：
  - {allowed}
2. 绝对禁止声明类型 (违者立即触发物理拦截并追责)：
  - {forbidden}
3. 严格 L5 隔离与客观陈述边界：
  - 严禁出现任何“买入”、“卖出”、“建仓”、“加仓”、“满仓”、“抄底”、“割肉”、“目标价”等交易指令或操作劝诱！
  - 绝对禁止包含向交易员发出行为命令的字眼，如“杜绝逆势博弈”、“严守...红线/纪律”、“控制仓位”、“保持克制/观望”等！
  - 必须且只能将风险描述为客观观测条件与假说证伪边界（例如：“市场处于高位分化加速段，逆势博弈面临显著亏损风险”；“次日竞价核心标杆若失守承接位，将触发结构性走弱与逻辑证伪”），绝对禁止向交易员发出行为命令！
4. 严格实体单射：所有股票名称必须与提供的规范名称绝对一致（002242 必须为九阳股份，绝对严禁出现毅昌科技）！
5. 严格数字保真：严禁篡改或捏造成交额、炸板率、天梯高度或跌停家数！两市成交额已含创业板，严禁重复累加！
6. 必须体现的证据锚点：
  - {anchors}

【结构与字数规范】：
- 严格分为四大模块：
  1. 【大势定调】：量能真实口径与微观状态标定；
  2. 【主线与梯队】：核心做多战场代表标杆与空间最高板；
  3. 【风险与负反馈】：真实炸板率、跌停大面与商业数据商异动规则撮合压力；
  4. 【明日推演与防守红线】：次日竞价核心观察哨与证伪触发条件。
- 总字数必须严格控制在 250 至 350 字之间，杜绝废话与泛泛而谈的宏观空话。"""

    @staticmethod
    def build_user_prompt(contract: NarrativeContextContract) -> str:
        """
        构建结构化用户提示词 (结构化注入 FACT, DERIVED, COGNITION)
        """
        fact = contract.fact_layer
        derived = contract.derived_layer
        cog = contract.cognition_layer

        ml_lines = []
        for ml in cog.candidate_mainlines[:3]:
            falsify_str = ml.falsification_condition.invalidation_rules[0] if ml.falsification_condition.invalidation_rules else "核心龙头竞价承接不足"
            ml_lines.append(
                f"- 第{ml.rank}主线【{ml.sector_name}】：龙头【{ml.leader_identity.canonical_name}】{ml.leader_height}B，"
                f"涨停 {ml.limit_up_count} 家。核心证伪条件：{falsify_str}"
            )
        mainline_summary = "\n".join(ml_lines)

        return f"""【业务日期】：{contract.trade_date}

【L0/L1 事实层 (FACT)】：
- 沪深真实总成交额：{fact.turnover.total_turnover_yi:.2f} 亿元（沪市 {fact.turnover.sh_amount_yi:.2f} 亿，深市含创业板 {fact.turnover.sz_total_amount_yi:.2f} 亿）
- 空间最高连板高度：{fact.ladder.max_height}B（空间标杆：【{fact.ladder.space_leader.canonical_name}】）
- 涨跌停微观统计：真实有效涨停 {fact.sentiment_counts.limit_up_count} 家，收盘跌停 {fact.sentiment_counts.limit_down_count} 家
- 商业数据商异动规则撮合标的：{fact.regulatory.total_anomaly_count} 家

【L2 衍生结构层 (DERIVED)】：
- 真实炸板率：{derived.broken_limit_ratio * 100:.2f}%
- 极值亏损率：{derived.extreme_loss_ratio * 100:.2f}%

【L3 顶层认知假说层 (COGNITION)】：
- 市场微观状态标定：【{cog.market_state.state_display_name}】（置信度 {int(cog.market_state.state_confidence * 100)}%）
- 状态驱动事实：{'; '.join(cog.market_state.driving_factors)}
- 主线候选与梯队纵深：
{mainline_summary}

请严格遵守发言边界，输出操盘内参战报正文。"""


class DeepSeekBriefingLLMClient:
    """
    生产级真实 DeepSeek LLM 客户端 (P0-1 真实大模型调用穿透支持)
    可精确测量 TTFT (Time To First Token)、总推理延迟与 Token 吞吐，并记录脱敏报文。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
    ):
        from backend.app.config import settings
        try:
            from .llm_config_service import LLMConfigService
            creds = LLMConfigService.get_runtime_credentials()
        except Exception:
            creds = {}

        self.api_key = api_key or creds.get("api_key") or settings.DEEPSEEK_API_KEY or settings.LLM_API_KEY
        raw_base_url = base_url or creds.get("base_url") or settings.LLM_BASE_URL or "https://api.deepseek.com/v1"
        self.base_url = str(raw_base_url).rstrip("/")
        self.model = model or creds.get("model") or settings.LLM_MODEL or "deepseek-chat"
        self.timeout = timeout if timeout != 30.0 else creds.get("timeout_seconds", 30.0)

    def call_stream_with_metrics(
        self,
        sys_prompt: str,
        usr_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 400,
    ) -> Dict[str, Any]:
        """
        以流式方式调用真实 LLM，精确测量 TTFT 与总耗时，捕获脱敏报文。
        """
        import time
        import httpx
        import json

        desensitized_key = (
            f"{self.api_key[:8]}***{self.api_key[-6:]}"
            if len(self.api_key) > 14
            else "***"
        )
        desensitized_payload = {
            "endpoint": f"{self.base_url}/chat/completions",
            "model": self.model,
            "api_key_masked": desensitized_key,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "sys_prompt_preview": sys_prompt[:120] + "...",
            "usr_prompt_preview": usr_prompt[:120] + "...",
        }

        if not self.api_key:
            raise ValueError("No valid LLM_API_KEY / DEEPSEEK_API_KEY configured for real LLM call.")

        client = httpx.Client(timeout=self.timeout, trust_env=False)
        t0 = time.time()
        ttft = None
        full_text = ""
        first_chunk = False

        with client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": usr_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            },
        ) as resp:
            if resp.status_code != 200:
                raw_body = resp.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"DeepSeek API HTTP {resp.status_code}: {raw_body}")

            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if delta and not first_chunk:
                        ttft = (time.time() - t0) * 1000
                        first_chunk = True
                    full_text += delta
                except Exception:
                    continue

        t_total = (time.time() - t0) * 1000
        if ttft is None:
            ttft = t_total

        return {
            "ttft_ms": round(ttft, 2),
            "total_ms": round(t_total, 2),
            "text": full_text.strip(),
            "char_count": len(full_text.strip()),
            "model": self.model,
            "desensitized_payload": desensitized_payload,
        }

    def __call__(self, sys_prompt: str, usr_prompt: str) -> str:
        metrics = self.call_stream_with_metrics(sys_prompt, usr_prompt)
        return metrics["text"]


class ConstrainedBriefingGenerator:
    """
    受约束 LLM 操盘战报生成器 (Constrained Briefing Generator)
    """

    def __init__(
        self,
        safety_guard: Optional[BriefingSafetyGuard] = None,
        fallback_engine: Optional[DeterministicBriefingFallbackEngine] = None,
        llm_client: Optional[Callable[[str, str], str]] = None,
        use_real_llm: bool = False,
    ):
        self.safety_guard = safety_guard or BriefingSafetyGuard()
        self.fallback_engine = fallback_engine or DeterministicBriefingFallbackEngine(
            safety_guard=self.safety_guard
        )
        self.briefing_service = TacticalBriefingService(
            safety_guard=self.safety_guard,
            fallback_engine=self.fallback_engine,
        )
        if use_real_llm and llm_client is None:
            self.llm_client = DeepSeekBriefingLLMClient()
        else:
            self.llm_client = llm_client

    def generate_briefing(
        self,
        contract: NarrativeContextContract,
        generated_at: str = "2026-10-09T03:00:00Z",
        trace_id: Optional[str] = None,
        source_snapshot_hash: Optional[str] = None,
    ) -> TacticalBriefingReport:
        """
        全流程生成战报：
        1. 构建受约束 Prompt；
        2. 调用 LLM 或自适应模拟推理；
        3. 经 BriefingSafetyGuard 拦截审查；
        4. 通过则发布正式战报，失败则无感降级。
        """
        active_trace_id = trace_id or f"TRACE-{contract.trade_date}-CANONICAL-DEFAULT"
        active_snapshot_hash = source_snapshot_hash or "926200c87eb19e07547d3e6ce5f780c44b2943313a499f69a68560880a49cc52"

        sys_prompt = BriefingPromptBuilder.build_system_prompt(contract)
        usr_prompt = BriefingPromptBuilder.build_user_prompt(contract)

        candidate_text: Optional[str] = None
        llm_metrics: Optional[dict] = None
        if self.llm_client:
            try:
                if hasattr(self.llm_client, "call_stream_with_metrics"):
                    res = self.llm_client.call_stream_with_metrics(sys_prompt, usr_prompt)
                    candidate_text = res.get("text")
                    llm_metrics = {
                        "model": res.get("model"),
                        "ttft_ms": res.get("ttft_ms"),
                        "total_ms": res.get("total_ms"),
                        "char_count": res.get("char_count"),
                        "desensitized_payload": res.get("desensitized_payload"),
                    }
                else:
                    candidate_text = self.llm_client(sys_prompt, usr_prompt)
            except Exception as e:
                # LLM 故障/异常，直接无感保底
                return self.fallback_engine.generate_fallback_briefing(
                    context=contract,
                    fallback_reason=f"LLM Client Exception ({type(e).__name__}): {str(e)}",
                    generated_at=generated_at,
                    trace_id=active_trace_id,
                    source_snapshot_hash=active_snapshot_hash,
                )
        else:
            # 默认高保真受约束自适应生成器 (根据 MarketState 自适应生成高质量操盘内参文本)
            candidate_text = self._adaptive_stylized_generation(contract)

        return self.briefing_service.produce_briefing(
            context=contract,
            candidate_text=candidate_text,
            generated_at=generated_at,
            trace_id=active_trace_id,
            source_snapshot_hash=active_snapshot_hash,
            llm_metrics=llm_metrics,
        )

    def _adaptive_stylized_generation(self, contract: NarrativeContextContract) -> str:
        """
        自适应操盘手文风生成器：针对不同市场状态呈现差异化战术文风，
        且严格遵守发言边界与数字事实。
        """
        fact = contract.fact_layer
        derived = contract.derived_layer
        cog = contract.cognition_layer

        total_to = fact.turnover.total_turnover_yi
        sh_to = fact.turnover.sh_amount_yi
        sz_to = fact.turnover.sz_total_amount_yi
        state_label = cog.market_state.state_display_name
        confidence_pct = int(cog.market_state.state_confidence * 100)
        max_h = fact.ladder.max_height
        space_leader = fact.ladder.space_leader.canonical_name
        broken_pct = derived.broken_limit_ratio * 100
        limit_down = fact.sentiment_counts.limit_down_count
        anomaly_count = fact.regulatory.total_anomaly_count

        top_ml = cog.candidate_mainlines[0] if cog.candidate_mainlines else None
        second_ml = cog.candidate_mainlines[1] if len(cog.candidate_mainlines) > 1 else None

        top_leader = top_ml.leader_identity.canonical_name if top_ml else space_leader
        top_h = top_ml.leader_height if top_ml else max_h
        falsification = (
            top_ml.falsification_condition.invalidation_rules[0]
            if top_ml and top_ml.falsification_condition.invalidation_rules
            else "核心龙头竞价承接力不足"
        )

        if cog.market_state.primary_state == MarketStateEnum.HIGH_DIVERGENCE_TOPPING:
            # 高位剧烈分化期文风：强调高位兑现、炸板与防守
            p1 = (
                f"【大势定调】两市总成交额达 {total_to:.2f} 亿元（沪市 {sh_to:.2f} 亿，深市含创业板 {sz_to:.2f} 亿）。"
                f"盘面处于典型的【{state_label}】（置信度 {confidence_pct}%），资金高位兑现加剧。"
            )
            p2 = (
                f"【主线与梯队】核心战场由【{top_ml.sector_name if top_ml else '主线'}】（龙头【{top_leader}】{top_h}B）"
                f"与【{second_ml.sector_name if second_ml else '分支'}】勉力维系，市场最高板标杆为 {max_h}B【{space_leader}】。"
            )
            p3 = (
                f"【风险与负反馈】微观亏钱效应急剧放大：日内真实炸板率高达 {broken_pct:.2f}%，收盘跌停 {limit_down} 家；"
                f"商业数据商异动规则撮合达 {anomaly_count} 家，高位核按钮频发使得情绪大幅承压。"
            )
            p4 = (
                f"【明日推演与防守红线】明日竞价重点盯紧【{space_leader}】溢价表现与【{top_leader}】承接力度。"
                f"核心防守证伪红线：{falsification}。"
            )
        elif cog.market_state.primary_state == MarketStateEnum.EXPANSION_ACCELERATION:
            # 主升共振期文风：强调赚钱效应、梯队完整与流动性充足
            p1 = (
                f"【大势定调】两市总成交额达 {total_to:.2f} 亿元（沪市 {sh_to:.2f} 亿，深市含创业板 {sz_to:.2f} 亿）。"
                f"盘面处于强劲的【{state_label}】（置信度 {confidence_pct}%），多头动能全面迸发。"
            )
            p2 = (
                f"【主线与梯队】核心主线【{top_ml.sector_name if top_ml else '主线'}】梯队纵深完整，"
                f"龙头【{top_leader}】强势挺进 {top_h}B，全市场空间高度打开至 {max_h}B【{space_leader}】。"
            )
            p3 = (
                f"【风险与负反馈】盘面良性运行：真实炸板率仅为 {broken_pct:.2f}%，收盘跌停 {limit_down} 家；"
                f"商业数据商异动规则撮合标的仅 {anomaly_count} 家，做多情绪处于良性通道。"
            )
            p4 = (
                f"【明日推演与防守红线】明日竞价重点观察空间标杆【{space_leader}】的接力意愿与后排首板晋级率。"
                f"核心证伪红线：{falsification}。"
            )
        else:
            # 其他状态下的标准稳健文风
            p1 = (
                f"【大势定调】沪深两市真实总成交额为 {total_to:.2f} 亿元（沪市 {sh_to:.2f} 亿，深市含创业板 {sz_to:.2f} 亿）。"
                f"市场当前状态标定为【{state_label}】（判定置信度 {confidence_pct}%）。"
            )
            p2 = (
                f"【主线与梯队】核心做多战场为【{top_ml.sector_name if top_ml else '主线'}】（龙头【{top_leader}】{top_h}B），"
                f"最高空间板为 {max_h}B【{space_leader}】。"
            )
            p3 = (
                f"【风险与负反馈】真实炸板率达 {broken_pct:.2f}%，收盘跌停 {limit_down} 家，"
                f"商业数据商异动规则撮合标的 {anomaly_count} 家。"
            )
            p4 = (
                f"【明日推演与防守红线】次日重点跟踪【{space_leader}】竞价承接。核心证伪红线：{falsification}。"
            )

        return f"{p1}{p2}{p3}{p4}"
