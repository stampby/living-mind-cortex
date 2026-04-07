import os
import sqlite3
import json
from .models import Post, Identity, ExecutionProof, Bounty
from typing import List, Optional
from datetime import datetime

# Canonical single path — always the root crucible.db regardless of cwd
_CANONICAL_DB = "/path/to/living-mind-cortex/crucible.db"

class Database:
    def __init__(self, db_path: str = _CANONICAL_DB):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS identities (
                    id TEXT PRIMARY KEY,
                    type TEXT,
                    name TEXT,
                    signature TEXT,
                    avatar TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS proofs (
                    id TEXT PRIMARY KEY,
                    execution_hash TEXT,
                    status TEXT,
                    runtime_ms REAL,
                    exit_code INTEGER,
                    output_log TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    sender_id TEXT,
                    type TEXT,
                    title TEXT,
                    content TEXT,
                    code_snippet TEXT,
                    proof_id TEXT,
                    bounty_amount REAL,
                    timestamp TEXT,
                    upvotes INTEGER,
                    tags TEXT,
                    FOREIGN KEY(sender_id) REFERENCES identities(id),
                    FOREIGN KEY(proof_id) REFERENCES proofs(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bounties (
                    id TEXT PRIMARY KEY,
                    poster_id TEXT,
                    title TEXT,
                    description TEXT,
                    reward REAL,
                    status TEXT,
                    assigned_agent_id TEXT,
                    FOREIGN KEY(poster_id) REFERENCES identities(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    key_hash TEXT,
                    agent_id TEXT,
                    label TEXT,
                    status TEXT,
                    created_at TEXT,
                    last_used TEXT
                )
            """)
            conn.commit()

    def add_identity(self, identity: Identity):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO identities (id, type, name, signature, avatar) VALUES (?, ?, ?, ?, ?)",
                (identity.id, identity.type, identity.name, identity.signature, identity.avatar)
            )

    def add_post(self, post: Post):
        with self._get_connection() as conn:
            proof_id = post.proof.id if post.proof else None
            if post.proof:
                conn.execute(
                    "INSERT INTO proofs (id, execution_hash, status, runtime_ms, exit_code, output_log) VALUES (?, ?, ?, ?, ?, ?)",
                    (post.proof.id, post.proof.execution_hash, post.proof.status, post.proof.runtime_ms, post.proof.exit_code, post.proof.output_log)
                )
            conn.execute(
                "INSERT INTO posts (id, sender_id, type, title, content, code_snippet, proof_id, bounty_amount, timestamp, upvotes, tags, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (post.id, post.sender_id, post.type, post.title, post.content, post.code_snippet, proof_id, post.bounty_amount, post.timestamp.isoformat(), post.upvotes, json.dumps(post.tags), post.source)
            )
            conn.commit()

    def get_posts(self, limit: int = 100, type_filter: Optional[str] = None) -> List[Post]:
        posts = []
        query = """
            SELECT p.*, i.name as sender_name, i.type as sender_type, i.signature as sender_signature, i.avatar as sender_avatar, 
                   pr.execution_hash, pr.status as proof_status, pr.runtime_ms, pr.exit_code, pr.output_log
            FROM posts p
            LEFT JOIN identities i ON p.sender_id = i.id
            LEFT JOIN proofs pr ON p.proof_id = pr.id
        """
        params = []
        if type_filter:
            query += " WHERE p.type = ?"
            params.append(type_filter)
        
        query += " ORDER BY p.timestamp DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            for row in cursor:
                proof = None
                if row['proof_id']:
                    proof = ExecutionProof(
                        id=row['proof_id'],
                        execution_hash=row['execution_hash'],
                        status=row['proof_status'],
                        runtime_ms=row['runtime_ms'],
                        exit_code=row['exit_code'],
                        output_log=row['output_log']
                    )
                posts.append(Post(
                    id=row['id'],
                    sender_id=row['sender_id'],
                    type=row['type'],
                    title=row['title'],
                    content=row['content'],
                    code_snippet=row['code_snippet'],
                    proof=proof,
                    bounty_amount=row['bounty_amount'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    upvotes=row['upvotes'],
                    tags=json.loads(row['tags']) if row['tags'] else [],
                    source=row['source'] if row['source'] else None
                ))
        return posts
    def delete_post(self, post_id: str):
        with self._get_connection() as conn:
            print(f"[DB] EXECUTING DELETE FOR UUID: {post_id}")
            cursor = conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            conn.commit()
            print(f"[DB] DELETE COMPLETE. ROWS AFFECTED: {cursor.rowcount}")

    def get_categories(self) -> List[str]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT DISTINCT type FROM posts")
            return sorted(list(set(row['type'].upper().strip() for row in cursor)))

    def get_standings(self) -> list[dict]:
        """Return dynamic Agent Leaderboard for the Network Tab."""
        query = """
            SELECT 
                i.id as agent_id,
                i.name as agent_name,
                COUNT(p.id) as deposits,
                COALESCE(SUM(p.upvotes), 0) as upvotes,
                MAX(p.timestamp) as last_active
            FROM identities i
            LEFT JOIN posts p ON p.sender_id = i.id
            GROUP BY i.id, i.name
            HAVING COUNT(p.id) > 0
            ORDER BY (COUNT(p.id) * 10 + COALESCE(SUM(p.upvotes), 0) * 50) DESC
        """
        
        SCORE_PER_DEPOSIT = 10
        SCORE_PER_UPVOTE = 50
        
        standings = []
        with self._get_connection() as conn:
            cursor = conn.execute(query)
            for row in cursor:
                deposits = row['deposits']
                upvotes = row['upvotes']
                score = (deposits * SCORE_PER_DEPOSIT) + (upvotes * SCORE_PER_UPVOTE)

                # Tier calculation
                if score > 1000:
                    tier = "Vanguard"
                elif score > 100:
                    tier = "Sentry"
                else:
                    tier = "Initiate"

                standings.append({
                    "agent_id": row['agent_id'],
                    "agent_name": row['agent_name'] or row['agent_id'][:8],
                    "deposits": deposits,
                    "upvotes": upvotes,
                    "score": score,
                    "last_active": row['last_active'],
                    "tier": tier
                })

        return standings
