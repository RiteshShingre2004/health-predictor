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

# Same name (any case), date of birth and email means the same person. Enforced by the database
# itself so two quick submits can't both slip past find_duplicate() while the AI call runs.
# Email is already lower-cased by validation.
UNIQUE_PERSON = """
CREATE UNIQUE INDEX IF NOT EXISTS patients_unique_person
ON patients (lower(full_name), dob, email)
"""

DuplicatePatient = sqlite3.IntegrityError


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
        # Remove copies saved before the unique index existed, keeping the earliest record.
        conn.execute("""DELETE FROM patients WHERE id NOT IN (
                            SELECT MIN(id) FROM patients GROUP BY lower(full_name), dob, email)""")
        conn.execute(UNIQUE_PERSON)
        renumber(conn)  # also repairs gaps left by deletes made before renumbering existed
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
    renumber(conn)
    conn.commit()


def renumber(conn: sqlite3.Connection) -> None:
    """Keep record numbers 1..N with no gaps, so the next new record is always N + 1.

    AUTOINCREMENT never reuses a number on its own: delete #4 and the next insert would be #5.
    """
    # Walk in ascending order: slots 1..new_id-1 are already filled and every unmoved id is
    # larger, so the target slot is always free.
    old_ids = [row["id"] for row in conn.execute("SELECT id FROM patients ORDER BY id")]
    for new_id, old_id in enumerate(old_ids, start=1):
        if new_id != old_id:
            conn.execute("UPDATE patients SET id = ? WHERE id = ?", (new_id, old_id))
    conn.execute("UPDATE sqlite_sequence SET seq = (SELECT COALESCE(MAX(id), 0) FROM patients) "
                 "WHERE name = 'patients'")
