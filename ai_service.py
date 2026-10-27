"""Health risk prediction.

Two layers:
1. assess_ranges() compares each blood value with standard adult reference ranges. This is
   plain Python, so the core flags are deterministic and testable.
2. predict() sends the values and those flags to an LLM on the Groq API, which returns a
   risk level, possible conditions and a short remark. If the API is unavailable, the
   remark is built from the flags alone, so saving a record never fails because of the AI.
"""

import json
import os
from typing import Literal

from groq import Groq, GroqError
from pydantic import BaseModel, ValidationError

MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# Adult reference ranges. Glucose and cholesterol are in mg/dL, haemoglobin in g/dL.
# Sex is not collected, so haemoglobin uses the general adult range (12-17.5 g/dL).
def glucose_status(value: float) -> str:
    if value < 70:
        return "low (hypoglycaemia range)"
    if value < 100:
        return "normal"
    if value < 126:
        return "elevated (prediabetes range)"
    return "high (diabetes range)"


def haemoglobin_status(value: float) -> str:
    if value < 8:
        return "very low (severe anaemia range)"
    if value < 12:
        return "low (anaemia range)"
    if value <= 17.5:
        return "normal"
    return "high (polycythaemia range)"


def cholesterol_status(value: float) -> str:
    if value < 200:
        return "normal"
    if value < 240:
        return "borderline high"
    return "high"


def assess_ranges(glucose: float, haemoglobin: float, cholesterol: float) -> dict:
    return {
        "glucose": glucose_status(glucose),
        "haemoglobin": haemoglobin_status(haemoglobin),
        "cholesterol": cholesterol_status(cholesterol),
    }


class Prediction(BaseModel):
    risk_level: Literal["Low", "Moderate", "High"]
    possible_conditions: list[str]
    remarks: str


SYSTEM_PROMPT = """You are a clinical decision-support assistant. You receive one patient's
age and three blood test results, plus a reference-range flag for each value.

Return JSON with:
- risk_level: "Low", "Moderate" or "High" overall health risk based on these results.
- possible_conditions: the conditions these results may indicate, e.g. "Type 2 diabetes",
  "Hypercholesterolaemia", "Anaemia". Empty list if all values are normal.
- remarks: at most 45 words, plain English, for the patient record. Name each abnormal value
  and what it may indicate, then one practical next step (e.g. "Recommend HbA1c test and GP
  review"). If everything is normal, say so.

Base everything only on the values given. Do not diagnose; use words like "may indicate"."""


def _fallback(flags: dict) -> dict:
    abnormal = [f"{test} {status}" for test, status in flags.items() if status != "normal"]
    if not abnormal:
        return {"risk_level": "Low", "remarks": "All results are within normal ranges. (AI service unavailable)"}
    level = "High" if any("high (" in a or "very low" in a for a in abnormal) else "Moderate"
    return {"risk_level": level,
            "remarks": "Abnormal: " + "; ".join(abnormal) + ". Recommend GP review. (AI service unavailable)"}


def predict(age: int, glucose: float, haemoglobin: float, cholesterol: float) -> dict:
    """Return {"risk_level": ..., "remarks": ...} for one patient."""
    flags = assess_ranges(glucose, haemoglobin, cholesterol)
    patient = {
        "age": age,
        "glucose_mg_dl": glucose, "glucose_flag": flags["glucose"],
        "haemoglobin_g_dl": haemoglobin, "haemoglobin_flag": flags["haemoglobin"],
        "cholesterol_mg_dl": cholesterol, "cholesterol_flag": flags["cholesterol"],
    }
    try:
        client = Groq(timeout=30, max_retries=2)  # reads GROQ_API_KEY from the environment
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": json.dumps(patient)}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "Prediction", "schema": Prediction.model_json_schema()}},
            reasoning_effort="low",
        )
        result = Prediction.model_validate_json(response.choices[0].message.content)
    except (GroqError, ValidationError, TypeError) as error:
        print(f"AI prediction failed, using reference-range fallback: {error}")
        return _fallback(flags)

    remarks = " ".join(result.remarks.split())  # also normalises the model's narrow no-break spaces
    if result.possible_conditions:
        remarks = f"Possible: {', '.join(result.possible_conditions)}. {remarks}"
    return {"risk_level": result.risk_level, "remarks": remarks}
