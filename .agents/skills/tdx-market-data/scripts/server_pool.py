#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
通达信主站池连通性与延迟诊断工具
用法：python server_pool.py
"""

import sys
import os
import time
import json
from pytdx.hq import TdxHq_API

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdx_client import DEFAULT_HQ_SERVERS

def main():
    api = TdxHq_API(auto_retry=False)
    results = []

    for srv in DEFAULT_HQ_SERVERS:
        t0 = time.time()
        try:
            ok = api.connect(srv["ip"], srv["port"], time_out=2.5)
            lat = round((time.time() - t0) * 1000, 1)
            if ok:
                api.disconnect()
                results.append({"name": srv["name"], "ip": srv["ip"], "port": srv["port"], "status": "ONLINE", "latency_ms": lat})
            else:
                results.append({"name": srv["name"], "ip": srv["ip"], "port": srv["port"], "status": "TIMEOUT", "latency_ms": lat})
        except Exception as e:
            lat = round((time.time() - t0) * 1000, 1)
            results.append({"name": srv["name"], "ip": srv["ip"], "port": srv["port"], "status": "ERROR", "error": str(e), "latency_ms": lat})

    # 按延迟排序
    online_servers = [s for s in results if s["status"] == "ONLINE"]
    online_servers.sort(key=lambda x: x["latency_ms"])

    output = {
        "status": "success",
        "total_servers": len(results),
        "online_servers_count": len(online_servers),
        "fastest_server": online_servers[0] if online_servers else None,
        "servers": results
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
