#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
逐笔成交明细 (Ticks) 查询 CLI
用法：python tick_detail.py --code 600519 --count 30
"""

import sys
import os
import argparse
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdx_client import TdxDirectClient

def main():
    parser = argparse.ArgumentParser(description="获取盘中逐笔分笔成交明细")
    parser.add_argument("--code", required=True, help="股票代码 (例: 600519)")
    parser.add_argument("--count", type=int, default=30, help="获取成交笔数 (默认: 30)")
    args = parser.parse_args()

    client = TdxDirectClient()
    try:
        ticks = client.get_ticks(args.code, count=args.count)
        output = {
            "status": "success",
            "code": args.code,
            "count": len(ticks),
            "data": ticks
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    main()
