"""SQLite storage for patient records (Create, Read, Update, Delete)."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "patients.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name    TEXT    NOT NULL,
    dob          TEXT    NOT NULL,          -- stored as dd/mm/yyyy
    email        TEXT    NOT NULL,
    glucose      REAL    NOT NULL,          -- mg/dL
    haemoglobin  REAL    NOT NULL,          -- g/dL
    cholesterol  REAL    NOT NULL,          -- mg/dL
    risk_level   TEXT,
    remarks      TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at   TEXT
)
"""


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection for one request and always close it afterwards."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dicts: row["full_name"]
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(SCHEMA)
        conn.commit()


def list_patients(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM patients ORDER BY id").fetchall()


def get_patient(conn: sqlite3.Connection, patient_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()


def find_duplicate(conn: sqlite3.Connection, data: dict, exclude_id: int | None = None) -> sqlite3.Row | None:
    """Same name, date of birth and email means the same person entered twice."""
    return conn.execute(
        """SELECT * FROM patients
           WHERE lower(full_name) = lower(?) AND dob = ? AND email = ? AND id IS NOT ?""",
        (data["full_name"], data["dob"], data["email"], exclude_id),
    ).fetchone()


def create_patient(conn: sqlite3.Connection, data: dict) -> int:
    cursor = conn.execute(
        """INSERT INTO patients (full_name, dob, email, glucose, haemoglobin, cholesterol, risk_level, remarks)
           VALUES (:full_name, :dob, :email, :glucose, :haemoglobin, :cholesterol, :risk_level, :remarks)""",
        data,
    )
    conn.commit()
    return cursor.lastrowid


def update_patient(conn: sqlite3.Connection, patient_id: int, data: dict) -> None:
    conn.execute(
        """UPDATE patients
           SET full_name = :full_name, dob = :dob, email = :email, glucose = :glucose,
               haemoglobin = :haemoglobin, cholesterol = :cholesterol, risk_level = :risk_level,
               remarks = :remarks, updated_at = datetime('now', 'localtime')
           WHERE id = :id""",
        {**data, "id": patient_id},
    )
    conn.commit()


def delete_patient(conn: sqlite3.Connection, patient_id: int) -> None:
    conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    conn.commit()
