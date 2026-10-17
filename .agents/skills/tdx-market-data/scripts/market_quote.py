#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
实时五档与盘口行情查询 CLI
用法：python market_quote.py --code 600519,000001
"""

import sys
import os
import argparse
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdx_client import TdxDirectClient

def main():
    parser = argparse.ArgumentParser(description="获取A股实时五档盘口与快照数据")
    parser.add_argument("--code", required=True, help="股票代码，多只股票用英文逗号分隔 (例: 600519,000001.SZ)")
    args = parser.parse_args()

    codes = [c.strip() for c in args.code.split(",") if c.strip()]
    if not codes:
        print(json.dumps({"status": "error", "message": "股票代码不能为空"}, ensure_ascii=False))
        sys.exit(1)

    client = TdxDirectClient()
    try:
        quotes = client.get_quotes(codes)
        output = {
            "status": "success",
            "count": len(quotes),
            "data": quotes
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    main()
