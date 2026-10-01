"""
RFC 8785 JSON Canonicalization Scheme (JCS) 纯 Python 实现
上位依据：《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》(Section 8.2)
标准规范：IETF RFC 8785 (https://www.rfc-editor.org/rfc/rfc8785)

核心特征：
1. 字典键排序：严格按照 UTF-16 字节序递增排序 (Lexicographical ordering of UTF-16 code units)
2. 空白字符消除：属性间与数组元素间仅用单个逗号分隔，键与值间仅用单个冒号分隔，零空白符
3. 浮点数规范化：遵从 IEEE 754 规则，不输出多余尾零，整型浮点数序列化为纯整型，0.0 输出为 0
4. 字符串转义：UTF-8 字符直接输出（不转义中文字符），仅对必需字符（"、\\ 与 U+0000~U+001F）转义，不转义正斜杠 (/)
5. 确定性哈希：通过 SHA-256 输出 64 位小写十六进制摘要
"""

import hashlib
import json
import math
from typing import Any, Union, Dict, List


def _utf16_sort_key(s: str) -> bytes:
    """返回字符串对应的 UTF-16BE 字节序，用于 RFC 8785 键排序"""
    return s.encode("utf-16-be")


def canonicalize(val: Any) -> str:
    """
    将任意 JSON 兼容对象序列化为 RFC 8785 JCS 确定性字符串
    """
    if val is None:
        return "null"
    elif isinstance(val, bool):
        return "true" if val else "false"
    elif isinstance(val, int):
        return str(val)
    elif isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"RFC 8785 prohibits NaN and Infinity, got {val}")
        if val == 0.0:
            return "0"
        if val.is_integer():
            return str(int(val))
        # 标准 Python 浮点输出，若包含科学计数法确保格式紧凑
        s = repr(val)
        return s
    elif isinstance(val, str):
        # 严格遵守 RFC 8785 字符串转义规则
        escaped_parts = []
        for ch in val:
            cp = ord(ch)
            if ch == '"':
                escaped_parts.append('\\"')
            elif ch == "\\":
                escaped_parts.append("\\\\")
            elif cp < 0x20:
                if ch == "\b":
                    escaped_parts.append("\\b")
                elif ch == "\f":
                    escaped_parts.append("\\f")
                elif ch == "\n":
                    escaped_parts.append("\\n")
                elif ch == "\r":
                    escaped_parts.append("\\r")
                elif ch == "\t":
                    escaped_parts.append("\\t")
                else:
                    escaped_parts.append(f"\\u{cp:04x}")
            else:
                escaped_parts.append(ch)
        return '"' + "".join(escaped_parts) + '"'
    elif isinstance(val, (list, tuple)):
        return "[" + ",".join(canonicalize(item) for item in val) + "]"
    elif isinstance(val, dict):
        # 键排序：必须是字符串且按 UTF-16 字节序排列
        sorted_keys = sorted(val.keys(), key=_utf16_sort_key)
        parts = []
        for k in sorted_keys:
            if not isinstance(k, str):
                raise TypeError(f"RFC 8785 object keys must be strings, got {type(k)}")
            parts.append(canonicalize(k) + ":" + canonicalize(val[k]))
        return "{" + ",".join(parts) + "}"
    else:
        raise TypeError(f"Type {type(val)} is not JSON-serializable in RFC 8785 JCS")


def canonicalize_bytes(val: Any) -> bytes:
    """序列化为 UTF-8 编码字节流"""
    return canonicalize(val).encode("utf-8")


def hash_jcs(val: Any) -> str:
    """计算 RFC 8785 JCS 规范化内容的 SHA-256 十六进制哈希（64 位小写）"""
    return hashlib.sha256(canonicalize_bytes(val)).hexdigest()
