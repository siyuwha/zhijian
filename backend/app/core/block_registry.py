"""
Block Registry and Taxonomy
===========================
Wave 1 概念板块注册表与三维正交分类隔离器
功能：
1. 过滤机械统计噪音（如 昨日连板、百元股、富时罗素、MSCI等）
2. 正交打标：
   - INDUSTRY: 申万/东财行业标准树（核心主线，参与假说求值）
   - CONCEPT: 催化题材主题（参与微观情绪共振）
   - REGION: 注册地（默认隔离，不作为主线投资逻辑求值）
"""

from typing import Dict, List, Optional, Set, Any, Tuple


class BlockRegistry:
    # 统计型噪音黑名单（机械标签，无产业或政策投资催化因果）
    NOISE_BLACKLIST: Set[str] = {
        "昨日连板", "昨日涨停", "昨日触板", "百元股", "破净股", "低价股",
        "微盘股", "融资融券", "转融券标的", "深股通", "沪股通",
        "富时罗素", "标准普尔", "MSCI中国", "预盈预增", "股权激励",
        "高股息精选", "中证500成份", "沪深300成份", "上证50成份",
        "深证100成份", "机构重仓", "基金重仓", "QFII重仓", "社保重仓",
        "证金持股", "汇金持股", "国企改革", "央企改革",
    }

    # 中国省级行政区与直辖市名单（地域判定）
    REGIONAL_PREFIXES: Tuple[str, ...] = (
        "北京", "天津", "上海", "重庆", "河北", "山西", "辽宁", "吉林",
        "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
        "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西",
        "甘肃", "青海", "台湾", "内蒙古", "广西", "西藏", "宁夏", "新疆",
        "香港", "澳门"
    )

    # 常见标准行业关键字
    KNOWN_INDUSTRIES: Set[str] = {
        "食品饮料", "白酒", "医药商业", "中药", "化学制药", "生物制品", "医疗器械", "医疗服务",
        "电力设备", "光伏设备", "风电设备", "电池", "电网设备", "电机",
        "半导体", "消费电子", "光学光电子", "电子元件", "元件", "其他电子",
        "计算机设备", "软件开发", "IT服务", "互联网服务", "通信设备", "通信服务",
        "银行", "证券", "保险", "多元金融", "房地产开发", "房地产服务",
        "汽车整车", "汽车零部件", "汽车服务", "交运设备",
        "有色金属", "钢铁", "煤炭行业", "石油行业", "化学原料", "化学制品", "农药兽药", "化肥行业",
        "农牧饲渔", "建筑装饰", "建筑材料", "通用设备", "专用设备", "仪器仪表",
        "商业百货", "旅游酒店", "航空机场", "航运港口", "物流行业", "铁路公路",
        "公用事业", "电力行业", "燃气", "环保行业", "美容护理", "纺织服装", "造纸印刷",
    }

    @classmethod
    def is_noise(cls, block_name: str) -> bool:
        """判定是否为机械统计噪音"""
        name = block_name.strip()
        if name in cls.NOISE_BLACKLIST:
            return True
        if name.startswith(("昨日", "MSCI", "标普", "标准普尔", "富时", "中证", "上证50", "沪深300")):
            return True
        return False

    @classmethod
    def categorize(cls, block_name: str, block_code: str = "") -> str:
        """
        三维正交分类判定
        返回: "INDUSTRY" | "CONCEPT" | "REGION" | "FILTERED_NOISE"
        """
        name = block_name.strip()
        if cls.is_noise(name):
            return "FILTERED_NOISE"

        # 1. 地域维度判定（以“板块”结尾且包含省份简称）
        if name.endswith("板块"):
            for region in cls.REGIONAL_PREFIXES:
                if region in name:
                    return "REGION"

        # 2. 行业维度判定（包含罗马数字或精确匹配申万/东财已知标准行业）
        if any(roman in name for roman in ("Ⅰ", "Ⅱ", "Ⅲ", "I", "II", "III")):
            return "INDUSTRY"

        if name in cls.KNOWN_INDUSTRIES or (name.endswith("行业") and name[:-2] in cls.KNOWN_INDUSTRIES):
            return "INDUSTRY"

        # 3. 默认属于概念题材主题
        return "CONCEPT"

    @classmethod
    def clean_and_tag_blocks(cls, raw_boards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        全量清洗与打标
        过滤噪音，打上 category，并分离三维结构
        """
        cleaned = []
        for b in raw_boards:
            name = b.get("name") or b.get("f14") or ""
            code = b.get("code") or b.get("f12") or ""
            cat = cls.categorize(name, code)
            if cat == "FILTERED_NOISE":
                continue

            cleaned.append({
                "block_code": code,
                "block_name": name,
                "category": cat,
                "change_pct": b.get("change_pct") or b.get("f3"),
                "leader_name": b.get("leader_name") or b.get("f128"),
                "leader_symbol": b.get("leader_symbol") or b.get("f140"),
            })
        return cleaned
