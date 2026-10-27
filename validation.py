"""Input validation for patient records.

validate_patient() takes the raw form values and returns (clean_data, errors).
`errors` maps a field name to a message, so the form can show each error next to its field.
"""

import re
from datetime import date

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z .'-]*$")
DATE_PATTERN = re.compile(r"^(\d{2})[/.-](\d{2})[/.-](\d{4})$")

# Plausible measurement limits. Values outside these are almost certainly typing errors
# (for example 1800 instead of 180), not real results.
BLOOD_LIMITS = {
    "glucose": ("Glucose", "mg/dL", 10, 1000),
    "haemoglobin": ("Haemoglobin", "g/dL", 1, 25),
    "cholesterol": ("Cholesterol", "mg/dL", 50, 1000),
}


def validate_name(value: str) -> tuple[str | None, str | None]:
    name = " ".join(value.split())  # trim and collapse repeated spaces
    if not name:
        return None, "Full name is required."
    if len(name) < 2 or not NAME_PATTERN.match(name):
        return None, "Use letters, spaces, apostrophes or hyphens only."
    return name, None


def validate_dob(value: str) -> tuple[str | None, str | None]:
    """Accepts dd/mm/yyyy (also dd.mm.yyyy or dd-mm-yyyy) and returns it as dd/mm/yyyy."""
    value = value.strip()
    match = DATE_PATTERN.match(value)
    if not match:
        return None, "Enter the date as dd/mm/yyyy."
    day, month, year = (int(part) for part in match.groups())
    try:
        dob = date(year, month, day)  # rejects impossible dates such as 31/11
    except ValueError:
        return None, f"{value} is not a real calendar date."
    today = date.today()
    if dob > today:
        return None, "Date of birth cannot be in the future."
    if today.year - dob.year > 130:
        return None, "Date of birth is more than 130 years ago."
    return dob.strftime("%d/%m/%Y"), None


def validate_email(value: str) -> tuple[str | None, str | None]:
    email = value.strip().lower()
    if not email:
        return None, "Email address is required."
    if not EMAIL_PATTERN.match(email):
        return None, "Enter a valid email address, e.g. name@example.com."
    return email, None


def validate_blood_value(field: str, value: str) -> tuple[float | None, str | None]:
    label, unit, low, high = BLOOD_LIMITS[field]
    value = value.strip()
    if not value:
        return None, f"{label} is required."
    try:
        number = float(value)
    except ValueError:
        return None, f"{label} must be a number."
    if not low <= number <= high:
        return None, f"{label} must be between {low} and {high} {unit}."
    return number, None


def validate_patient(form: dict) -> tuple[dict, dict]:
    clean, errors = {}, {}
    checks = {
        "full_name": validate_name,
        "dob": validate_dob,
        "email": validate_email,
    }
    for field, check in checks.items():
        clean[field], error = check(form.get(field, ""))
        if error:
            errors[field] = error
    for field in BLOOD_LIMITS:
        clean[field], error = validate_blood_value(field, form.get(field, ""))
        if error:
            errors[field] = error
    return clean, errors
