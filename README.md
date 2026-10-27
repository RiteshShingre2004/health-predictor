# Health Predictor

A Flask web application for managing patient blood test records. When a valid record is saved, the app calls an AI model through the **Groq API** to predict possible health conditions and writes the result to the **Remarks** column.

**Stack:** Python 3 · Flask · SQLite · Jinja2 templates with HTML/CSS · Groq API (`openai/gpt-oss-120b`) · pytest

## Features

| Requirement | How it is met |
|---|---|
| **CRUD** | Create, list, edit and delete patient records (`app.py`) |
| **User interface** | One records table with colour-coded risk badges, and one form for creating and editing with errors shown next to each field |
| **Validation** | Name, date of birth, email and numeric blood values are checked on the server before anything is saved (`validation.py`) |
| **Persistent storage** | SQLite database `patients.db`, created automatically on first run (`database.py`) |
| **AI integration** | Valid records are sent to an LLM on the Groq API, which returns a risk level, possible conditions and a short remark (`ai_service.py`) |

## Run it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then add your GROQ_API_KEY (free at console.groq.com)
python app.py               # open http://127.0.0.1:5050
```

Run the tests with `pytest`. They use a temporary database and a stubbed AI call, so they need no API key.

## Project structure

```
app.py            Flask routes: list, create, edit, delete
validation.py     Input validation; returns (clean data, errors per field)
database.py       SQLite schema and CRUD queries (parameterised SQL)
ai_service.py     Reference-range checks + Groq API prediction, with offline fallback
templates/        base layout, records list, create/edit form
static/style.css  Styling
tests/            The 10 task records run through the real app, plus range checks
```

## Validation rules

| Field | Rule |
|---|---|
| Full name | Required; letters, spaces, apostrophes and hyphens |
| Date of birth | `dd/mm/yyyy`. Dots and dashes are also accepted, as the task data uses `28.01.1960`, and every date is stored as `dd/mm/yyyy`. It must be a real calendar date, not in the future, and less than 130 years ago |
| Email | Must look like `name@domain.tld`; stored in lower case |
| Glucose / Haemoglobin / Cholesterol | Must be numeric and within a plausible range (glucose 10–1000 mg/dL, haemoglobin 1–25 g/dL, cholesterol 50–1000 mg/dL) |
| Duplicates | A record with the same name, date of birth and email as an existing record is rejected |

## How the AI prediction works

1. **Reference ranges (plain Python).** `assess_ranges()` flags each value against standard adult ranges, for example glucose ≥126 mg/dL is in the diabetes range, haemoglobin <12 g/dL in the anaemia range, and cholesterol ≥240 mg/dL is high. These flags are deterministic and unit-tested.
2. **AI prediction (Groq API).** The patient's age, values and flags are sent to `openai/gpt-oss-120b` with a JSON schema. The model returns `risk_level` (Low / Moderate / High), `possible_conditions` and `remarks`, and the response is validated with Pydantic before it is saved.
3. **Fallback.** If the API is unreachable or returns invalid output, the record is still saved, with a remark built from the reference-range flags and marked "(AI service unavailable)".
4. **Efficient updates.** When a record is edited, the AI is called again only if the date of birth or a blood value changed. Changing just the email keeps the existing remarks.

The API key is read from `.env`, which is excluded from Git by `.gitignore`. No keys are stored in the code.

## Task data results

| # | Name | Result | Reason |
|---|---|---|---|
| 1 | Robyn Pears | Saved | Valid |
| 2 | John Hunter | **Rejected** | `hunter@gmail` has no domain ending (e.g. `.com`) |
| 3 | Darryl Tim | Saved | Valid |
| 4 | Peter Larry | **Rejected** | `31.11.2001` is not a real date: November has 30 days |
| 5 | Sam Kerr | Saved | Valid |
| 6 | Robyn Pears | **Rejected** | Duplicate of record #1 (same name, date of birth and email) |
| 7 | Madison XI | Saved | Valid |
| 8 | Kris Wu | **Rejected** | Date of birth `19.10.2030` is in the future, **and** `Kris.wu.gmail.com` has no `@` |
| 9 | Tenille Singh | Saved | Valid |
| 10 | Prem Kumar | Saved | Valid |

*AI remarks are decision support only and are not a medical diagnosis.*
