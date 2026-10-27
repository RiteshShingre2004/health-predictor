"""Health Predictor: Flask web app for patient blood test records with AI risk remarks.

Routes
  GET  /                      list all records (Read)
  GET  /patients/new          blank form
  POST /patients/new          validate, call AI, save (Create)
  GET  /patients/<id>/edit    pre-filled form
  POST /patients/<id>/edit    validate, re-run AI if results changed, save (Update)
  POST /patients/<id>/delete  remove the record (Delete)
"""

import os
from datetime import date, datetime

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for

import database as db
from ai_service import predict
from validation import validate_patient

load_dotenv()  # GROQ_API_KEY and FLASK_SECRET_KEY come from .env, never from code

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24)
db.init_db()

BLOOD_FIELDS = ("glucose", "haemoglobin", "cholesterol")


@app.template_filter("num")
def format_number(value):
    """Show 232.0 as 232 and 13.5 as 13.5; leave text (e.g. form input) unchanged."""
    if isinstance(value, float):
        return f"{value:g}"
    return value


def age_from_dob(dob: str) -> int:
    born = datetime.strptime(dob, "%d/%m/%Y").date()
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def run_prediction(data: dict) -> dict:
    return predict(age_from_dob(data["dob"]), data["glucose"], data["haemoglobin"], data["cholesterol"])


@app.route("/")
def index():
    with db.connect() as conn:
        patients = db.list_patients(conn)
    return render_template("index.html", patients=patients)


@app.route("/patients/new", methods=["GET", "POST"])
def create():
    if request.method == "GET":
        return render_template("form.html", form={}, errors={}, patient=None)

    data, errors = validate_patient(request.form)
    with db.connect() as conn:
        if not errors and (existing := db.find_duplicate(conn, data)):
            errors["duplicate"] = (f"This patient already exists as record #{existing['id']} "
                                   "(same name, date of birth and email).")
        if errors:
            return render_template("form.html", form=request.form, errors=errors, patient=None), 422

        data.update(run_prediction(data))
        new_id = db.create_patient(conn, data)
    flash(f"Record #{new_id} for {data['full_name']} saved. AI risk: {data['risk_level']}.", "success")
    return redirect(url_for("index"))


@app.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
def edit(patient_id: int):
    with db.connect() as conn:
        patient = db.get_patient(conn, patient_id) or abort(404)
        if request.method == "GET":
            return render_template("form.html", form=dict(patient), errors={}, patient=patient)

        data, errors = validate_patient(request.form)
        if not errors and (existing := db.find_duplicate(conn, data, exclude_id=patient_id)):
            errors["duplicate"] = f"These details match record #{existing['id']}."
        if errors:
            return render_template("form.html", form=request.form, errors=errors, patient=patient), 422

        # Only call the AI again if something it uses changed; an email fix keeps the old remarks.
        if data["dob"] != patient["dob"] or any(data[f] != patient[f] for f in BLOOD_FIELDS):
            data.update(run_prediction(data))
        else:
            data.update(risk_level=patient["risk_level"], remarks=patient["remarks"])
        db.update_patient(conn, patient_id, data)
    flash(f"Record #{patient_id} updated.", "success")
    return redirect(url_for("index"))


@app.route("/patients/<int:patient_id>/delete", methods=["POST"])
def delete(patient_id: int):
    with db.connect() as conn:
        patient = db.get_patient(conn, patient_id) or abort(404)
        db.delete_patient(conn, patient_id)
    flash(f"Record #{patient_id} ({patient['full_name']}) deleted.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5050)  # macOS AirPlay Receiver already uses port 5000
