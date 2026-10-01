import sqlite3
import os

scratch_db = r"C:\Users\siyuw\.gemini\antigravity\brain\156b15a4-1597-433b-a5a1-dd284c44f3fa\scratch\verify_clean_migration.db"
if os.path.exists(scratch_db):
    os.remove(scratch_db)

conn = sqlite3.connect(scratch_db)
cur = conn.cursor()

import sys
sys.path.insert(0, r"D:\项目库\AI认知复盘交易系统\backend")

# 1. Simulate full clean schema DDL execution
from app.core.database import Base
import app.models # load all models
from app.models.cognition_v2 import DATABASE_WORM_TRIGGERS_SQL
from app.cognition.chain_state import DEFAULT_CHAIN_ID, GENESIS_PREVIOUS_HASH
import datetime

# Create all tables via metadata (as would be encoded in Alembic 0001 & 0002)
# Here we verify that sqlite handles all DDL + triggers + genesis in sequence
from sqlalchemy import create_engine
engine = create_engine(f"sqlite:///{scratch_db.replace(os.sep, '/')}")
Base.metadata.create_all(engine)

# Execute WORM triggers (as encoded in Alembic 0003)
with engine.begin() as c:
    for trigger_sql in DATABASE_WORM_TRIGGERS_SQL:
        c.exec_driver_sql(trigger_sql)
    # Insert genesis chain state
    c.exec_driver_sql(f"""
        INSERT INTO cognition_chain_state (
            chain_id, tail_sequence_id, tail_record_hash
        ) VALUES (
            '{DEFAULT_CHAIN_ID}', 0, '{GENESIS_PREVIOUS_HASH}'
        )
    """)

# Verify directly via raw sqlite3
conn = sqlite3.connect(scratch_db)
cur = conn.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
triggers = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()]
genesis_row = cur.execute("SELECT chain_id, tail_sequence_id, tail_record_hash FROM cognition_chain_state").fetchall()

print(f"Total tables: {len(tables)}")
print(f"Total triggers: {len(triggers)}, Triggers: {triggers}")
print(f"Genesis row: {genesis_row}")

# Direct SQL attack verification: try to UPDATE cognition_record
# First insert a test record with valid columns
cur.execute("""
    INSERT INTO cognition_record (
        id, date, stage, timestamp,
        market_event_time, observation_window,
        data_snapshot_time, verification_execute_time,
        observation_snapshot, market_state_snapshot,
        prompt_id, prompt_version, prompt_hash,
        model_provider, model_name, model_version, inference_config,
        effective_input_hash, rendered_system_prompt, rendered_user_prompt,
        raw_response, structured_cognition, hypothesis_set_hash,
        sequence_id, previous_record_hash, payload_hash, record_hash,
        replay_type
    ) VALUES (
        'rec_test_01', '2026-10-01', 'EOD', '2026-10-01 15:00:00',
        '15:00:00', '15:00:00-15:05:00',
        '2026-10-01 15:05:00', NULL,
        '{}', '{}',
        'p1', 'v1', 'hash_p',
        'mock', 'mock', 'v1', '{}',
        'hash_in', 'sys', 'usr',
        'raw_initial', '{}', 'hset_hash',
        1, '0000000000000000000000000000000000000000000000000000000000000000', 'payload_hash', 'rec_hash_01',
        'ORIGINAL'
    )
""")
conn.commit()

# Attack 1: try UPDATE on cognition_record
try:
    cur.execute("UPDATE cognition_record SET raw_response='hacked' WHERE id='rec_test_01'")
    conn.commit()
    print("FAILED: UPDATE succeeded! Trigger did not block!")
except (sqlite3.OperationalError, sqlite3.IntegrityError) as e:
    print(f"SUCCESS: Direct SQL UPDATE blocked by trigger: {e}")

# Attack 2: try DELETE on cognition_record
try:
    cur.execute("DELETE FROM cognition_record WHERE id='rec_test_01'")
    conn.commit()
    print("FAILED: DELETE succeeded! Trigger did not block!")
except (sqlite3.OperationalError, sqlite3.IntegrityError) as e:
    print(f"SUCCESS: Direct SQL DELETE blocked by trigger: {e}")

# Attack 3: try DELETE on cognition_chain_state
try:
    cur.execute("DELETE FROM cognition_chain_state WHERE chain_id='MAIN_LEDGER'")
    conn.commit()
    print("FAILED: DELETE on chain_state succeeded! Trigger did not block!")
except (sqlite3.OperationalError, sqlite3.IntegrityError) as e:
    print(f"SUCCESS: Direct SQL DELETE on chain_state blocked by trigger: {e}")

conn.close()
