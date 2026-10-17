#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全天 241 分钟分时走势查询 CLI
用法：python minute_trend.py --code 600519
"""

import sys
import os
import argparse
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdx_client import TdxDirectClient

def main():
    parser = argparse.ArgumentParser(description="获取个股全天241点连续分时走势")
    parser.add_argument("--code", required=True, help="股票代码 (例: 600519)")
    args = parser.parse_args()

    client = TdxDirectClient()
    try:
        points = client.get_minute_trend(args.code)
        output = {
            "status": "success",
            "code": args.code,
            "points_count": len(points),
            "data": points
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    main()
