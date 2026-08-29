import hashlib
import json
import time
import sqlite3
import os

DB_PATH = "output/ibvap.db"

def calculate_file_sha256(file_path):
    """Generates SHA-256 hash of an evidence image or file to guarantee authenticity."""
    if not os.path.exists(file_path):
        return None
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def calculate_block_hash(index, previous_hash, timestamp, event_data, evidence_hash, nonce=0):
    """Calculates SHA-256 hash of a blockchain block payload."""
    block_string = f"{index}{previous_hash}{timestamp}{json.dumps(event_data, sort_keys=True)}{evidence_hash}{nonce}"
    return hashlib.sha256(block_string.encode()).hexdigest()

def initialize_blockchain():
    """Initializes the SQLite blockchain_ledger table and creates Genesis block if needed."""
    os.makedirs("output", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blockchain_ledger (
            block_index INTEGER PRIMARY KEY,
            event_id TEXT UNIQUE,
            previous_hash TEXT,
            block_hash TEXT,
            evidence_hash TEXT,
            timestamp TEXT,
            nonce INTEGER,
            data_json TEXT
        )
    """)
    conn.commit()

    # Check if genesis block exists
    cursor.execute("SELECT COUNT(*) FROM blockchain_ledger")
    count = cursor.fetchone()[0]

    if count == 0:
        genesis_timestamp = "2026-01-01 00:00:00"
        genesis_data = {"message": "IBVAP Genesis Block - Immutable Security Ledger Initialized"}
        evidence_hash = hashlib.sha256(b"GENESIS_EVIDENCE").hexdigest()
        genesis_hash = calculate_block_hash(0, "0" * 64, genesis_timestamp, genesis_data, evidence_hash, 0)

        cursor.execute("""
            INSERT INTO blockchain_ledger (block_index, event_id, previous_hash, block_hash, evidence_hash, timestamp, nonce, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (0, "EVT-GENESIS", "0" * 64, genesis_hash, evidence_hash, genesis_timestamp, 0, json.dumps(genesis_data)))
        conn.commit()

    conn.close()

def add_event_to_blockchain(event_id, event_data, evidence_path):
    """Mines and appends a new cryptographic block to the ledger for a security event."""
    initialize_blockchain()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get latest block
    cursor.execute("SELECT block_index, block_hash FROM blockchain_ledger ORDER BY block_index DESC LIMIT 1")
    last_block = cursor.fetchone()
    prev_index, prev_hash = last_block

    new_index = prev_index + 1
    timestamp = str(event_data.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S")))
    evidence_hash = calculate_file_sha256(evidence_path) or hashlib.sha256(f"NO_FILE_{event_id}".encode()).hexdigest()

    # Lightweight Proof-of-Work (nonce calculation)
    nonce = 0
    block_hash = calculate_block_hash(new_index, prev_hash, timestamp, event_data, evidence_hash, nonce)
    
    # Simple difficulty target for high performance: hash starts with '0'
    while not block_hash.startswith("0"):
        nonce += 1
        block_hash = calculate_block_hash(new_index, prev_hash, timestamp, event_data, evidence_hash, nonce)

    cursor.execute("""
        INSERT INTO blockchain_ledger (block_index, event_id, previous_hash, block_hash, evidence_hash, timestamp, nonce, data_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (new_index, event_id, prev_hash, block_hash, evidence_hash, timestamp, nonce, json.dumps(event_data)))

    conn.commit()
    conn.close()
    return block_hash, evidence_hash

def verify_blockchain_integrity():
    """Validates the complete blockchain ledger for tampering."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT block_index, event_id, previous_hash, block_hash, evidence_hash, timestamp, nonce, data_json FROM blockchain_ledger ORDER BY block_index ASC")
    blocks = cursor.fetchall()
    conn.close()

    if not blocks:
        return True, "Blockchain is empty."

    for i in range(len(blocks)):
        index, event_id, prev_hash, block_hash, evidence_hash, timestamp, nonce, data_json = blocks[i]
        event_data = json.loads(data_json)

        # Verify Genesis Block
        if index == 0:
            recalculated_hash = calculate_block_hash(0, "0" * 64, timestamp, event_data, evidence_hash, nonce)
            if recalculated_hash != block_hash:
                return False, f"Genesis Block (Index 0) is corrupted!"
            continue

        # Check chain linkage with previous block
        expected_prev_hash = blocks[i-1][3]
        if prev_hash != expected_prev_hash:
            return False, f"Chain linkage broken at Block #{index} (Event {event_id})!"

        # Recalculate block hash
        recalculated_hash = calculate_block_hash(index, prev_hash, timestamp, event_data, evidence_hash, nonce)
        if recalculated_hash != block_hash:
            return False, f"Block hash mismatch at Block #{index} (Event {event_id})! Data may be tampered."

    return True, f"All {len(blocks)} blocks verified successfully. Ledger integrity 100% authentic."

if __name__ == "__main__":
    print("Initializing Blockchain Audit Ledger...")
    initialize_blockchain()
    valid, msg = verify_blockchain_integrity()
    print("Verification Result:", msg)
