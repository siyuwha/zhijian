"""
Phase 3B.1: Tamper-Evident Hash-Chained Alert Audit Logger
==========================================================
上位依据：
1. 最高董事会裁决令：《VERDICT-PHASE3A-CLOSE-PHASE3B1-GATE-20261009》
2. 治理红线：不得将普通 JSONL 追加文件直接等同于 WORM 存储，必须具备密码学防篡改链条。

核心设计：
- 级联哈希链 (Merkle Hash-Chain Append-Only Log)；
- 每行载荷包含: line_index, recorded_at, event_payload, prev_line_hash, line_hash；
- 首行绑定全零创世哈希 ("0"*64)；
- 具备物理全量链条完整性校验器 (verify_audit_log_integrity)，任何字符篡改雪崩式识别。
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from threading import Lock

from backend.app.cognition.jcs import hash_jcs
from backend.app.schemas.canonical_alert_event import CanonicalDriftAlertEvent

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64


class AlertAuditLogger:
    """
    密码学级联防篡改审计日志器 (WORM-Equivalent Hash Chained Logger)
    """
    def __init__(self, log_dir: str = "logs/alert_bus"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self._lock = Lock()
        self.last_line_hash = GENESIS_HASH
        self.current_line_index = 0

    def _get_log_path(self, trade_date: str) -> str:
        return os.path.join(self.log_dir, f"alert_audit_{trade_date}.jsonl")

    def append_event(self, event: CanonicalDriftAlertEvent) -> str:
        """
        向指定交易日日志追加一条级联签名的审计条目，返回当前行哈希
        """
        with self._lock:
            log_path = self._get_log_path(event.trade_date)
            
            # 若日志文件已存在，先读取末行哈希初始化状态
            if self.current_line_index == 0 and os.path.exists(log_path):
                self._sync_state_from_existing_file(log_path)

            self.current_line_index += 1
            now_iso = datetime.now(timezone(timedelta(hours=8))).isoformat()

            entry_to_hash = {
                "line_index": self.current_line_index,
                "recorded_at": now_iso,
                "event": event.model_dump(),
                "prev_line_hash": self.last_line_hash,
            }

            current_line_hash = hash_jcs(entry_to_hash)
            full_record = dict(entry_to_hash)
            full_record["line_hash"] = current_line_hash

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(full_record, ensure_ascii=False) + "\n")

            self.last_line_hash = current_line_hash
            return current_line_hash

    def _sync_state_from_existing_file(self, log_path: str) -> None:
        """从已存在的日志文件同步行号与末行哈希"""
        if not os.path.exists(log_path):
            return
        last_line = None
        count = 0
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line.strip()
                    count += 1
        if last_line:
            try:
                data = json.loads(last_line)
                self.current_line_index = count
                self.last_line_hash = data.get("line_hash", GENESIS_HASH)
            except Exception as e:
                logger.error(f"[AUDIT LOG SYNC ERROR] Failed to parse last line: {e}")

    @staticmethod
    def verify_audit_log_integrity(
        log_path: str,
        expected_closing_hash: Optional[str] = None,
        expected_line_count: Optional[int] = None,
    ) -> Tuple[bool, int, Optional[str]]:
        """
        全量静态校验指定日志文件的哈希链完整性：
        - 支持外部可信锚点校验 (expected_closing_hash, expected_line_count)
        - 返回 (is_valid, verified_line_count, error_detail)
        - 任何单字符篡改、删行、尾部截断、插行或重排将立即报告失败
        """
        if not os.path.exists(log_path):
            return False, 0, f"File not found: {log_path}"

        expected_prev_hash = GENESIS_HASH
        line_idx = 0

        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                line_idx += 1
                try:
                    record = json.loads(line_str)
                except Exception as e:
                    return False, line_idx, f"Line {line_idx} invalid JSON: {e}"

                if record.get("line_index") != line_idx:
                    return False, line_idx, f"Line {line_idx} index mismatch: expected {line_idx}, got {record.get('line_index')}"

                actual_prev_hash = record.get("prev_line_hash")
                if actual_prev_hash != expected_prev_hash:
                    return False, line_idx, f"Line {line_idx} prev_line_hash mismatch! Tampering detected."

                actual_line_hash = record.get("line_hash")
                to_verify = {
                    "line_index": record["line_index"],
                    "recorded_at": record["recorded_at"],
                    "event": record["event"],
                    "prev_line_hash": record["prev_line_hash"],
                }
                computed_hash = hash_jcs(to_verify)
                if actual_line_hash != computed_hash:
                    return False, line_idx, f"Line {line_idx} line_hash mismatch! Content has been altered."

                expected_prev_hash = actual_line_hash

        # 校验外部可信锚点 (抗尾部截断与全量重写攻击)
        if expected_line_count is not None and line_idx != expected_line_count:
            return False, line_idx, f"Log truncation detected: expected {expected_line_count} lines, found {line_idx}"

        if expected_closing_hash is not None and expected_prev_hash != expected_closing_hash:
            return False, line_idx, f"Closing hash mismatch! External anchor {expected_closing_hash} != {expected_prev_hash}. Truncation or forgery detected."

        return True, line_idx, None

