"""db.py — Cortiq Postgres persistence layer
All history, artifacts, portfolio, drafts and watchlist stored on VPS Postgres.
Connection string via DATABASE_URL env var.
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras


def _conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL não configurada")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── History ───────────────────────────────────────────────

def history_load() -> List[Dict]:
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT mode, key, verdict, confidence, verdict_color,
                           thesis, mandate, report, sources, evaluation,
                           queries, market_data, critic_notes, created_at
                    FROM analyses
                    ORDER BY created_at DESC
                    LIMIT 2000
                """)
                rows = cur.fetchall()
                return [
                    {
                        "mode": r["mode"],
                        "key": r["key"],
                        "verdict": r["verdict"] or "",
                        "confidence": r["confidence"] or "",
                        "verdictColor": r["verdict_color"] or "",
                        "thesis": r["thesis"] or "",
                        "mandate": r["mandate"] or "",
                        "report": r["report"] or "",
                        "sources": r["sources"] or [],
                        "evaluation": r["evaluation"] or {},
                        "queries": r["queries"] or [],
                        "market_data": r["market_data"] or {},
                        "critic_notes": r["critic_notes"] or "",
                        "date": r["created_at"].isoformat() if r["created_at"] else "",
                    }
                    for r in rows
                ]
    except Exception as e:
        print(f"[db] history_load error: {e}")
        return []


def history_save(entry: Dict) -> None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO analyses
                        (mode, key, verdict, confidence, verdict_color,
                         thesis, mandate, report, sources, evaluation,
                         queries, market_data, critic_notes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    entry.get("mode", ""),
                    entry.get("key", ""),
                    entry.get("verdict", ""),
                    entry.get("confidence", ""),
                    entry.get("verdictColor", ""),
                    entry.get("thesis", ""),
                    entry.get("mandate", ""),
                    entry.get("report", ""),
                    json.dumps(entry.get("sources", []), ensure_ascii=False),
                    json.dumps(entry.get("evaluation", {}), ensure_ascii=False),
                    json.dumps(entry.get("queries", []), ensure_ascii=False),
                    json.dumps(entry.get("market_data", {}), ensure_ascii=False),
                    entry.get("critic_notes", ""),
                ))
            conn.commit()
    except Exception as e:
        print(f"[db] history_save error: {e}")


def history_for_key(mode: str, key: str) -> List[Dict]:
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT mode, key, verdict, confidence, verdict_color,
                           thesis, mandate, report, sources, evaluation,
                           queries, market_data, critic_notes, created_at
                    FROM analyses
                    WHERE mode=%s AND lower(key)=lower(%s)
                    ORDER BY created_at DESC
                    LIMIT 100
                """, (mode, key))
                rows = cur.fetchall()
                return [
                    {
                        "mode": r["mode"],
                        "key": r["key"],
                        "verdict": r["verdict"] or "",
                        "confidence": r["confidence"] or "",
                        "verdictColor": r["verdict_color"] or "",
                        "date": r["created_at"].isoformat() if r["created_at"] else "",
                        "evaluation": r["evaluation"] or {},
                        "sources": r["sources"] or [],
                    }
                    for r in rows
                ]
    except Exception as e:
        print(f"[db] history_for_key error: {e}")
        return []


def history_delete_key(mode: str, key: str) -> None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM analyses WHERE mode=%s AND lower(key)=lower(%s)",
                    (mode, key)
                )
            conn.commit()
    except Exception as e:
        print(f"[db] history_delete_key error: {e}")


def history_clear() -> None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM analyses")
            conn.commit()
    except Exception as e:
        print(f"[db] history_clear error: {e}")


# ── Artifacts ─────────────────────────────────────────────

def artifact_save(mode: str, key: str, payload: Dict) -> None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO artifacts (mode, key, payload)
                    VALUES (%s, %s, %s)
                """, (mode, key.upper() if mode == "equity" else key,
                      json.dumps(payload, ensure_ascii=False)))
            conn.commit()
    except Exception as e:
        print(f"[db] artifact_save error: {e}")


def artifact_load_latest(mode: str, key: str) -> Optional[Dict]:
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT payload FROM artifacts
                    WHERE mode=%s AND lower(key)=lower(%s)
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (mode, key))
                row = cur.fetchone()
                return row["payload"] if row else None
    except Exception as e:
        print(f"[db] artifact_load error: {e}")
        return None


# ── KV Store (watchlist, portfolio, etc.) ─────────────────

def kv_get(key: str, default: Any = None) -> Any:
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT value FROM kv_store WHERE key=%s", (key,))
                row = cur.fetchone()
                return row["value"] if row else default
    except Exception as e:
        print(f"[db] kv_get({key}) error: {e}")
        return default


def kv_set(key: str, value: Any) -> None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO kv_store (key, value, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (key) DO UPDATE
                    SET value=EXCLUDED.value, updated_at=NOW()
                """, (key, json.dumps(value, ensure_ascii=False)))
            conn.commit()
    except Exception as e:
        print(f"[db] kv_set({key}) error: {e}")


# ── Drafts ────────────────────────────────────────────────

def draft_save(draft: Dict) -> None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO drafts (id, payload, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (id) DO UPDATE
                    SET payload=EXCLUDED.payload, updated_at=NOW()
                """, (draft["id"], json.dumps(draft, ensure_ascii=False)))
            conn.commit()
    except Exception as e:
        print(f"[db] draft_save error: {e}")


def draft_load(draft_id: str) -> Optional[Dict]:
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT payload FROM drafts WHERE id=%s", (draft_id,))
                row = cur.fetchone()
                return row["payload"] if row else None
    except Exception as e:
        print(f"[db] draft_load error: {e}")
        return None


def drafts_load_all() -> List[Dict]:
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT payload FROM drafts ORDER BY updated_at DESC LIMIT 200")
                return [r["payload"] for r in cur.fetchall()]
    except Exception as e:
        print(f"[db] drafts_load_all error: {e}")
        return []
