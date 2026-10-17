#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多周期历史 K 线数据查询 CLI
用法：python kline_history.py --code 600519 --period 1d --count 50
"""

import sys
import os
import argparse
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdx_client import TdxDirectClient

def main():
    parser = argparse.ArgumentParser(description="获取个股多周期历史 K 线数据")
    parser.add_argument("--code", required=True, help="股票代码 (例: 600519)")
    parser.add_argument("--period", default="1d", choices=["1d", "5m", "1m", "15m", "30m", "60m", "1w", "1mon"], help="K线周期")
    parser.add_argument("--count", type=int, default=100, help="获取K线根数 (默认: 100)")
    args = parser.parse_args()

    client = TdxDirectClient()
    try:
        bars = client.get_kline(args.code, period=args.period, count=args.count)
        output = {
            "status": "success",
            "code": args.code,
            "period": args.period,
            "count": len(bars),
            "data": bars
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    main()
