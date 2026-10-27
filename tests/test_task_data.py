"""Runs the 10 records from the Task 2 brief through the real Flask app (AI call stubbed)
and checks that each is accepted or rejected for the right reason."""

import pytest

import ai_service
import app as health_app
import database as db

TASK_DATA = [
    # (test #, full name, DOB, email, glucose, haemoglobin, cholesterol)
    (1, "Robyn Pears", "28.01.1960", "robyn@gmail.com", "232", "13.5", "180"),
    (2, "John Hunter", "10.12.1990", "hunter@gmail", "94", "15", "200"),
    (3, "Darryl Tim", "12.11.1993", "timd@smh.com.au", "240", "18.6", "326"),
    (4, "Peter Larry", "31.11.2001", "Larry@hotmail.com", "88", "11.5", "165"),
    (5, "Sam Kerr", "09.12.2006", "sam@news.com.au", "198", "8.9", "192"),
    (6, "Robyn Pears", "28.01.1960", "robyn@gmail.com", "232", "13.5", "180"),
    (7, "Madison XI", "12.09.1998", "madison@hotmail.com", "85", "7.6", "163"),
    (8, "Kris Wu", "19.10.2030", "Kris.wu.gmail.com", "79", "16.5", "197"),
    (9, "Tenille Singh", "30.11.1991", "Tenille@yahoo.com", "101", "15", "310"),
    (10, "Prem Kumar", "28.04.1990", "prem@telstra.com", "155", "12.5", "265"),
]

# Expected rejections: test # -> text that must appear in the error page.
EXPECTED_ERRORS = {
    2: ["valid email address"],
    4: ["not a real calendar date"],
    6: ["already exists"],
    8: ["cannot be in the future", "valid email address"],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")  # never touch the real patients.db
    db.init_db()
    monkeypatch.setattr(health_app, "predict",
                        lambda age, g, h, c: {"risk_level": "Low", "remarks": "stub"})
    health_app.app.config["TESTING"] = True
    return health_app.app.test_client()


def submit(client, row):
    _, name, dob, email, glucose, hb, chol = row
    return client.post("/patients/new", data={
        "full_name": name, "dob": dob, "email": email,
        "glucose": glucose, "haemoglobin": hb, "cholesterol": chol,
    })


def test_task_records_accepted_or_rejected_for_the_right_reason(client):
    for row in TASK_DATA:
        response = submit(client, row)
        page = response.get_data(as_text=True)
        if row[0] in EXPECTED_ERRORS:
            assert response.status_code == 422, f"test #{row[0]} should be rejected"
            for text in EXPECTED_ERRORS[row[0]]:
                assert text in page, f"test #{row[0]} missing error: {text}"
        else:
            assert response.status_code == 302, f"test #{row[0]} should be saved:\n{page[:2000]}"

    with db.connect() as conn:
        saved = db.list_patients(conn)
    assert [p["full_name"] for p in saved] == [
        "Robyn Pears", "Darryl Tim", "Sam Kerr", "Madison XI", "Tenille Singh", "Prem Kumar"]
    assert saved[0]["dob"] == "28/01/1960"  # dots normalised to dd/mm/yyyy


def test_edit_email_keeps_remarks_and_delete_removes(client):
    submit(client, TASK_DATA[0])
    response = client.post("/patients/1/edit", data={
        "full_name": "Robyn Pears", "dob": "28/01/1960", "email": "gokul@infocare.com",
        "glucose": "232", "haemoglobin": "13.5", "cholesterol": "180",
    })
    assert response.status_code == 302
    with db.connect() as conn:
        assert db.get_patient(conn, 1)["email"] == "gokul@infocare.com"
    client.post("/patients/1/delete")
    with db.connect() as conn:
        assert db.get_patient(conn, 1) is None


@pytest.mark.parametrize("glucose,hb,chol,expected", [
    (232, 13.5, 180, {"glucose": "high (diabetes range)", "haemoglobin": "normal", "cholesterol": "normal"}),
    (85, 7.6, 163, {"glucose": "normal", "haemoglobin": "very low (severe anaemia range)", "cholesterol": "normal"}),
    (101, 15, 310, {"glucose": "elevated (prediabetes range)", "haemoglobin": "normal", "cholesterol": "high"}),
])
def test_reference_ranges(glucose, hb, chol, expected):
    assert ai_service.assess_ranges(glucose, hb, chol) == expected


def test_delete_renumbers_and_next_record_fills_the_gap(client):
    for row in (TASK_DATA[0], TASK_DATA[2], TASK_DATA[4], TASK_DATA[6]):
        submit(client, row)
    client.post("/patients/2/delete")  # Darryl Tim
    client.post("/patients/3/delete")  # Madison XI (was #4, now #3)
    with db.connect() as conn:
        assert [(p["id"], p["full_name"]) for p in db.list_patients(conn)] == [
            (1, "Robyn Pears"), (2, "Sam Kerr")]
    submit(client, TASK_DATA[8])
    with db.connect() as conn:
        assert db.list_patients(conn)[-1]["id"] == 3

    for _ in range(3):
        client.post("/patients/1/delete")
    submit(client, TASK_DATA[9])
    with db.connect() as conn:
        assert [p["id"] for p in db.list_patients(conn)] == [1]  # empty table starts again at 1


def test_double_submit_saves_only_one_copy(client, monkeypatch):
    """Two identical submits that both pass the duplicate check while the AI call runs."""
    import threading
    import time

    def slow_predict(age, g, h, c):
        time.sleep(0.5)
        return {"risk_level": "Low", "remarks": "stub"}

    monkeypatch.setattr(health_app, "predict", slow_predict)
    codes = []
    threads = [threading.Thread(target=lambda: codes.append(submit(health_app.app.test_client(), TASK_DATA[0]).status_code))
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [302, 422]
    with db.connect() as conn:
        assert len(db.list_patients(conn)) == 1
