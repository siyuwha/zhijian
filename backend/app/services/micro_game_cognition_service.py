import asyncio
from datetime import datetime
import json
import logging
import time
from typing import Any, Dict, List, Optional
import httpx

from .llm_config_service import LLMConfigService

logger = logging.getLogger(__name__)

# 内存单日认知缓存字典
_COGNITION_CACHE: Dict[str, Dict[str, Any]] = {}
# 内存单日认知触发历史轨迹：trade_date -> List[Dict[str, Any]]
_COGNITION_HISTORY: Dict[str, List[Dict[str, Any]]] = {}


class MicroGameCognitionService:
    """
    核心微观博弈与题材轮动 LLM 深度认知生成服务
    上位依据：
    1. 彻底淘汰前端写死的静态死板模板字符串；
    2. 基于清洗完毕的高纯度事实卡片（换手率、真实流通市值、连板高度、封单、资金剪刀差），
       调用大语言模型 (LLM) 生成富有机构博弈深度与穿透力的即时盘面洞察；
    3. 支持带超时的优雅降级（量化专家启发式规则引擎）。
    """

    SYSTEM_PROMPT = """你是一个在A股顶级私募与游资交易室拥有15年一线操盘经验的首席认知复盘专家。
你的职责是：基于系统提供的客观微观量化事实，摒弃千篇一律的废话和公文套话，以极具刀锋感、因果逻辑严密、直击本质的语言，提炼出微观博弈与题材轮动的3段核心洞察。

必须输出严格合法的 JSON 对象，格式如下：
{
  "track1": "昨日核心在今日的表现剖析（重点点名核心个股、换手率与承接/核按钮本质）",
  "track2": "今日最强涨停与昨日核心的动态博弈（分析存量资金吸血剪刀差、高低切还是共振助攻）",
  "sector_rotation": "题材战场资金轮动本质（必须以一线操盘手视角指名道姓：1.今日资金真正的主攻战场是谁？是真金白银放量共振还是缩量弱脉冲？点名先锋标杆与容量中军大票；2.资金在与谁玩跷跷板抽血？谁在持续失血为谁买单？3.梯队助攻质量与独苗/炸板风险。直击痛点，拒绝空洞套话）"
}
约束：
1. 必须使用中文，严禁输出任何 markdown 格式代码块标记（如不要加 ```json ），仅输出纯 JSON 字符串；
2. 语言风格：专业、精炼、充满金融博弈穿透力，杜绝“表现良好”、“值得关注”、“轮动态势”等公文废话；
3. sector_rotation 必须结合提供的成交额、中军龙头与梯队涨停数，写出清晰的盘面定调，60~110 字。"""

    @classmethod
    def get_cognition_history(cls, trade_date: str) -> List[Dict[str, Any]]:
        """
        获取指定交易日的 AI 题材轮动推演触发历史记录
        """
        return _COGNITION_HISTORY.get(trade_date, [])

    @classmethod
    def _record_history(
        cls,
        trade_date: str,
        result_data: Dict[str, Any],
        sectors: List[Dict[str, Any]],
        force_refresh: bool = False,
    ) -> None:
        """
        将单次推演结果记录入当日事件驱动时间轴中
        """
        if trade_date not in _COGNITION_HISTORY:
            _COGNITION_HISTORY[trade_date] = []

        now_time = datetime.now().strftime("%H:%M:%S")
        lead_sec = sectors[0] if sectors else {}
        lead_name = lead_sec.get("name", "主流题材")
        lead_net = float(lead_sec.get("net", 0) or 0)

        tail_sec = sectors[-1] if sectors else {}
        tail_name = tail_sec.get("name", "对立题材")
        tail_net = float(tail_sec.get("net", 0) or 0)

        history_list = _COGNITION_HISTORY[trade_date]

        # 触发时机与盘面事件智能判定
        if not history_list:
            event_type = "开盘首次定调"
        else:
            prev = history_list[-1]
            # 若与上一条内容、主线题材均完全一致且未强制刷新，则避免冗余写入
            if (
                not force_refresh
                and prev.get("sector_rotation") == result_data.get("sector_rotation")
                and prev.get("lead_sector") == lead_name
            ):
                return

            if prev.get("lead_sector") != lead_name:
                event_type = f"主线更替·{lead_name}接棒"
            elif abs(lead_net - float(prev.get("lead_net", 0))) >= 5.0 or (lead_net > 0 and float(prev.get("lead_net", 0)) <= 0):
                event_type = "主力资金剪刀差突变"
            elif now_time >= "15:00:00" and prev.get("time", "") < "15:00:00":
                event_type = "尾盘收盘沉淀定型"
            elif now_time >= "11:30:00" and prev.get("time", "") < "11:30:00":
                event_type = "午盘多空格局定型"
            else:
                event_type = "题材轮动动态追踪"

        item = {
            "id": f"{trade_date}_{int(time.time() * 1000)}_{len(history_list) + 1}",
            "time": now_time,
            "event_type": event_type,
            "event_desc": f"主攻【{lead_name}】({lead_net:+.1f}亿) / 失血【{tail_name}】({tail_net:+.1f}亿)",
            "lead_sector": lead_name,
            "lead_net": lead_net,
            "tail_sector": tail_name,
            "tail_net": tail_net,
            "sector_rotation": result_data.get("sector_rotation", ""),
            "track1": result_data.get("track1", ""),
            "track2": result_data.get("track2", ""),
            "source": result_data.get("source", "QUANT_EXPERT_ENGINE"),
            "model": result_data.get("model", ""),
            "created_at": datetime.now().isoformat(),
        }

        history_list.append(item)
        if len(history_list) > 50:
            _COGNITION_HISTORY[trade_date] = history_list[-50:]

    @classmethod
    async def generate_game_cognition(
        cls,
        trade_date: str,
        stocks: List[Dict[str, Any]],
        strongest_stock: Optional[Dict[str, Any]],
        sectors: List[Dict[str, Any]],
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        生成或获取微观个股博弈与题材轮动的 LLM 洞察结论
        """
        cache_key = f"{trade_date}_{len(stocks)}_{strongest_stock.get('code', '') if strongest_stock else ''}"
        if not force_refresh and cache_key in _COGNITION_CACHE:
            cached_res = _COGNITION_CACHE[cache_key]
            if trade_date not in _COGNITION_HISTORY or not _COGNITION_HISTORY[trade_date]:
                cls._record_history(trade_date, cached_res, sectors, force_refresh=False)
            return {
                **cached_res,
                "history": cls.get_cognition_history(trade_date),
            }

        # 1. 组装输入客观事实简报
        stock_facts = []
        for s in stocks:
            stock_facts.append({
                "code": s.get("code"),
                "name": s.get("name"),
                "pct": f"{s.get('changePct', 0):+.2f}%",
                "role": s.get("role"),
                "turnover": f"{s.get('turnoverRate', '--')}%",
                "float_mcap": f"{s.get('floatMcapYi', '--')}亿",
                "amount": f"{s.get('totalAmountYi', '--')}亿",
                "roles": s.get("roles", []),
            })

        sector_facts = []
        for sec in sectors[:5]:
            flagship_name = "--"
            if isinstance(sec.get("flagship"), dict):
                flagship_name = sec["flagship"].get("name", "--")
            elif sec.get("flagshipName"):
                flagship_name = sec.get("flagshipName", "--")

            sector_facts.append({
                "name": sec.get("name"),
                "turnover_amount": f"{sec.get('amount_yi', sec.get('amount', '--'))}亿",
                "net_inflow": f"{sec.get('net', 0):+.1f}亿",
                "pct": f"{sec.get('pct', 0):+.2f}%",
                "leader_pioneer": f"{sec.get('leader', '--')}({sec.get('leaderPct', 0):+.1f}%)",
                "flagship_core": flagship_name,
                "echelon_summary": sec.get("echelon_summary") or f"{sec.get('limit_up_count', 0)}只涨停",
                "max_height": f"{sec.get('max_height', 1)}B",
                "is_solitary": sec.get("isSolitaryMonopoly", False),
                "rear_negative": f"{round((sec.get('rearNegativeRatio', 0) or 0) * 100)}%",
                "seesaw_role": sec.get("seesaw_role", "NORMAL"),
            })

        payload_context = {
            "trade_date": trade_date,
            "core_sample_stocks": stock_facts,
            "today_strongest_stock": strongest_stock or {},
            "top_5_sectors": sector_facts,
        }

        user_prompt = f"以下是 {trade_date} 盘中最新清洗的微观结构与资金量化事实：\n{json.dumps(payload_context, ensure_ascii=False, indent=2)}\n\n请立即输出针对这三项的专业复盘洞察 JSON。"

        # 2. 尝试调用系统配置的 LLM (若未配置则优雅降级为启发式专家推演)
        creds = LLMConfigService.get_runtime_credentials()
        api_key = creds.get("api_key")
        base_url = (creds.get("base_url") or "").strip()
        model = (creds.get("model") or "").strip()

        result_data = None
        if api_key and base_url and model:
            try:
                clean_base_url = base_url.rstrip("/")
                endpoint = f"{clean_base_url}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                body = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": cls.SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 800,
                }
                async with httpx.AsyncClient(timeout=12.0, trust_env=False) as client:
                    resp = await client.post(endpoint, headers=headers, json=body)
                    if resp.status_code == 200:
                        raw_json = resp.json()
                        content = raw_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        if content:
                            if content.startswith("```"):
                                content = content.split("```")[1]
                                if content.startswith("json"):
                                    content = content[4:].strip()
                            parsed = json.loads(content)
                            if "track1" in parsed and "track2" in parsed and "sector_rotation" in parsed:
                                result_data = {
                                    "status": "ok",
                                    "source": "LLM_INFERRED",
                                    "model": model,
                                    "track1": parsed["track1"],
                                    "track2": parsed["track2"],
                                    "sector_rotation": parsed["sector_rotation"],
                                }
            except Exception as e:
                logger.warning(f"LLM call failed for micro game cognition, falling back to quantitative expert engine: {e}")

        # 3. 兜底回退：量化专家启发式规则引擎 (比旧版死模板丰富得多的量化博弈推演)
        if not result_data:
            result_data = cls._generate_heuristic_cognition(stocks, strongest_stock, sectors)

        _COGNITION_CACHE[cache_key] = result_data
        cls._record_history(trade_date, result_data, sectors, force_refresh=force_refresh)
        return {
            **result_data,
            "history": cls.get_cognition_history(trade_date),
        }

    @classmethod
    def _generate_heuristic_cognition(
        cls,
        stocks: List[Dict[str, Any]],
        strongest_stock: Optional[Dict[str, Any]],
        sectors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        当未配置 LLM API 或超时断网时的量化专家启发式推理引擎
        """
        # 1. 分析昨日核心表现
        h_stocks = [s for s in stocks if s.get("tagType") == "yesterday_highest"]
        s_stocks = [s for s in stocks if s.get("tagType") == "yesterday_second"]
        all_s = stocks or []

        broken_stocks = [s for s in all_s if "炸板" in str(s.get("roles", [])) or s.get("changePct", 0) < 0]
        strong_stocks = [s for s in all_s if s.get("changePct", 0) > 8.5]
        floor_stocks = [s for s in all_s if s.get("changePct", 0) <= -9.0]

        if floor_stocks:
            f_names = "、".join([s.get("name", "") for s in floor_stocks])
            track1 = f"昨日连板高标出现剧烈分化冰点，【{f_names}】开盘遭遇无情核按钮封死跌停，资金高位接力意愿大幅受挫；"
            if strong_stocks:
                s_names = "、".join([s.get("name", "") for s in strong_stocks])
                track1 += f"但【{s_names}】凭借独立逻辑强势封死涨停，呈现极端的多空冰火两重天格局。"
            else:
                track1 += "高位容错率骤降，存量筹码恐慌踩踏效应显著。"
        elif strong_stocks and not broken_stocks:
            s_names = "、".join([s.get("name", "") for s in strong_stocks])
            track1 = f"昨日高标溢价全面兑现，【{s_names}】开盘加速晋级，换手洗盘充分，多头抱团结构极其坚挺，市场情绪处于良性接力上升期。"
        else:
            names = "、".join([f"{s.get('name')}({s.get('changePct', 0):+.1f}%)" for s in all_s[:3]])
            track1 = f"昨日核心标的【{names}】日内呈现高位震荡洗盘态势，资金分歧加剧，筹码在关键支撑位激烈博弈，整体以维稳震荡为主。"

        # 2. 分析今日最强 vs 昨日核心
        st_name = strongest_stock.get("name") if strongest_stock else "日内新首板"
        st_sector = strongest_stock.get("sector") if strongest_stock else "独立题材"
        st_pct = strongest_stock.get("zdp", 10.0) if strongest_stock else 10.0

        if floor_stocks:
            track2 = f"盘中实时最强先锋【{st_name}】({st_sector}，+{st_pct}%)与老高标形成鲜明的「抽血剪刀差」，资金坚决执行高低切换避险策略，抛弃昨日退潮龙头，涌入低位确定性防线。"
        elif strong_stocks:
            track2 = f"日内领跑先锋【{st_name}】与昨日高位中军形成合力共振，增量资金在主线与细分领域多点开花，做多动能由单点突破扩散为全面梯队助攻。"
        else:
            track2 = f"盘中新题材龙头【{st_name}】尝试突破吸附存量流动性，但受制于大盘量能收缩，未能带动昨日核心跟风，呈现孤军深入的局部博弈态势。"

        # 3. 分析题材轮动特征 (专家规则引擎结合梯队中军与跷跷板全面升级)
        if sectors:
            lead_sec = sectors[0]
            lead_name = lead_sec.get("name", "主线")
            lead_net = float(lead_sec.get("net", 0) or 0)
            lead_pioneer = lead_sec.get("leader", "--")
            lead_flagship = lead_sec.get("flagship", {}).get("name") if isinstance(lead_sec.get("flagship"), dict) else lead_sec.get("flagshipName")
            lead_height = lead_sec.get("max_height", 1)
            lead_count = lead_sec.get("limit_up_count", 1)
            lead_echelon = lead_sec.get("echelon_summary") or ""
            is_solitary = lead_sec.get("isSolitaryMonopoly", False)

            tail_sec = sectors[-1]
            tail_name = tail_sec.get("name", "弱势题材")
            tail_net = float(tail_sec.get("net", 0) or 0)

            flagship_part = f"，容量中军【{lead_flagship}】承接大资金" if (lead_flagship and lead_flagship != lead_pioneer) else ""
            echelon_part = f"，梯队聚拢{lead_count}只涨停形成集团作战" if lead_count > 1 else ("，但呈独苗弱抱团特征" if is_solitary else "")

            if lead_net > 0 and tail_net < 0:
                sector_rot = (
                    f"盘面呈现典型的存量跷跷板博弈：【{lead_name}】以主力净流入 {lead_net:+.1f}亿 成为绝对主攻阵地，"
                    f"先锋【{lead_pioneer}】({lead_height}B){flagship_part}{echelon_part}；"
                    f"而对立题材【{tail_name}】以 {tail_net:+.1f}亿 持续失血成为主要抽血源，资金弃弱聚强，警惕非主线跟风标的流动性挤出风险。"
                )
            elif lead_net > 0 and tail_net >= 0:
                sector_rot = (
                    f"全天多头资金情绪亢奋，【{lead_name}】净流入 {lead_net:+.1f}亿 领跑全场，"
                    f"先锋【{lead_pioneer}】带队展开攻坚{flagship_part}{echelon_part}，各主流题材呈增量普涨共振态势，市场进攻动能通畅。"
                )
            else:
                sector_rot = (
                    f"盘面存量博弈特征显著，【{lead_name}】虽有脉冲但主力净流入仅 {lead_net:+.1f}亿，缺乏大体量中军协同承接，"
                    f"各热点轮动过快且多带长上影，操作上需警惕尾盘佯攻诱多与冲高回落大面风险。"
                )
        else:
            sector_rot = "全天题材轮动节奏加快，存量资金在各个细分热点间快速脉冲反抽，缺乏持续性领涨大题材，以防守防御为主。"

        return {
            "status": "ok",
            "source": "QUANT_EXPERT_ENGINE",
            "model": "rule_heuristic",
            "track1": track1,
            "track2": track2,
            "sector_rotation": sector_rot,
        }
