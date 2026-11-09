"""Shared JSON grading validation for calibration and development evaluations."""
import json


def validate_grade(grade):
    if not isinstance(grade, dict):
        raise ValueError("Grade must be a JSON object")
    for key in ("correctness", "grounding", "behavior", "language"):
        if type(grade.get(key)) is not int or grade[key] not in (0, 1, 2):
            raise ValueError(f"Invalid grader score: {key}")
    if not isinstance(grade.get("reason"), str) or not grade["reason"].strip():
        raise ValueError("Missing grading reason")
    claims = grade.get("unsupported_claims")
    if not isinstance(claims, list) or any(not isinstance(c, str) for c in claims):
        raise ValueError("Invalid unsupported claims")
    if grade["grounding"] == 2 and claims:
        raise ValueError("Full grounding conflicts with unsupported claims")
    if "source_errors" in grade:
        errors = grade["source_errors"]
        if not isinstance(errors, list) or any(not isinstance(error, str) for error in errors):
            raise ValueError("Invalid source errors")
        if grade["grounding"] == 2 and errors:
            raise ValueError("Full grounding conflicts with source errors")
    return grade


def grade_answer(grader, rubric, payload):
    message = grader.invoke([("system", rubric), ("human", json.dumps(payload, ensure_ascii=False))])
    grade = validate_grade(json.loads(message.content))
    if "source_metadata" in payload and "source_errors" not in grade:
        raise ValueError("Source-aware grading requires source_errors")
    return {"grade": grade,
            "grading_usage": message.usage_metadata or {}, "grading_raw": message.content}
