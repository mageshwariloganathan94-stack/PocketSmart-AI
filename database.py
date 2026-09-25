import sqlite3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

DB_NAME = "pocketsmart.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # History table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        planner_type TEXT NOT NULL,
        query_summary TEXT NOT NULL,
        budget REAL NOT NULL,
        total_cost REAL NOT NULL,
        input_details TEXT NOT NULL,
        results_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)
    
    conn.commit()
    conn.close()

def create_user(username: str, email: str, hashed_password: str) -> Optional[int]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, email, hashed_password) VALUES (?, ?, ?)",
            (username.strip().lower(), email.strip().lower(), hashed_password)
        )
        conn.commit()
        user_id = cursor.lastrowid
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def save_history(
    user_id: int,
    planner_type: str,
    query_summary: str,
    budget: float,
    total_cost: float,
    input_details: Dict[str, Any],
    results_json: List[Dict[str, Any]]
) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO history (user_id, planner_type, query_summary, budget, total_cost, input_details, results_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            planner_type,
            query_summary,
            float(budget),
            float(total_cost),
            json.dumps(input_details),
            json.dumps(results_json)
        )
    )
    conn.commit()
    history_id = cursor.lastrowid
    conn.close()
    return history_id

def get_user_history(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    history_list = []
    for r in rows:
        item = dict(r)
        try:
            item["input_details"] = json.loads(item["input_details"])
        except Exception:
            pass
        try:
            item["results_json"] = json.loads(item["results_json"])
        except Exception:
            pass
        history_list.append(item)
    return history_list

def get_history_item(history_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM history WHERE id = ? AND user_id = ?",
        (history_id, user_id)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        item = dict(row)
        try:
            item["input_details"] = json.loads(item["input_details"])
        except Exception:
            pass
        try:
            item["results_json"] = json.loads(item["results_json"])
        except Exception:
            pass
        return item
    return None

def delete_history_item(history_id: int, user_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history WHERE id = ? AND user_id = ?", (history_id, user_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0
