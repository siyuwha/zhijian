#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
大盘核心指数查询 CLI (上证、深证、创业板、科创50)
用法：python index_quote.py
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdx_client import TdxDirectClient

def main():
    client = TdxDirectClient()
    try:
        indices = client.get_index_quotes()
        output = {
            "status": "success",
            "count": len(indices),
            "data": indices
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    main()
