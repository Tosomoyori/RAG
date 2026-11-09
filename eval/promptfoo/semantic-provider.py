"""Generate from frozen contexts and grade outputs using a fixed JSON rubric."""
import json
from pathlib import Path

from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
CASES = {case["id"]: case for case in json.loads((DIRECTORY / "semantic-cases.json").read_text(encoding="utf-8"))}
PROMPTS = json.loads((ROOT / "prompts.json").read_text(encoding="utf-8"))
RUBRIC = (DIRECTORY / "semantic-rubric.txt").read_text(encoding="utf-8")
generator = ChatDeepSeek(model="deepseek-chat", temperature=0.7, timeout=90, max_retries=1)
grader = ChatDeepSeek(model="deepseek-chat", temperature=0, timeout=90, max_retries=1).bind(
    response_format={"type": "json_object"})


def validate_grade(grade):
    if not isinstance(grade, dict):
        raise ValueError("Grading must be a JSON object")
    for name in ("correctness", "grounding", "behavior", "language"):
        value = grade.get(name)
        if type(value) is not int or value not in (0, 1, 2):
            raise ValueError(f"Invalid {name} grade: {value}")
    if not isinstance(grade.get("reason"), str) or not grade["reason"].strip():
        raise ValueError("Grading reason is required")
    if not isinstance(grade.get("unsupported_claims"), list):
        raise ValueError("unsupported_claims must be a list")
    if any(not isinstance(claim, str) for claim in grade["unsupported_claims"]):
        raise ValueError("Unsupported claims must be strings")
    if grade["grounding"] == 2 and grade["unsupported_claims"]:
        raise ValueError("Full grounding is inconsistent with unsupported claims")


def call_api(prompt, options, context):
    case = CASES[context["vars"]["case_id"]]
    variant = context["vars"].get("variant", options.get("config", {}).get("variant", "saved"))
    generation_usage = {}
    if variant == "saved":
        answer = case["saved_answer"]
    else:
        message = PROMPTS[variant].format(question=case["question"], context=case["context"],
                                          answer_language="English" if case["lang"] == "en" else "简体中文")
        generated = generator.invoke(message)
        answer = generated.content
        generation_usage = generated.usage_metadata or {}
    grading_input = {
        "question": case["question"], "expected_language": case["lang"],
        "reference_answer": case["reference_answer"],
        "reference_kind": case["reference_kind"],
        "expected_behavior": case["expected_behavior"],
        "context": case["context"], "answer": answer,
    }
    messages = [("system", RUBRIC), ("human", json.dumps(grading_input, ensure_ascii=False))]
    attempts = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    for attempt in range(2):
        graded = grader.invoke(messages)
        current_usage = graded.usage_metadata or {}
        for key in usage:
            usage[key] += current_usage.get(key, 0)
        attempts.append(graded.content)
        try:
            grade = json.loads(graded.content)
            validate_grade(grade)
            break
        except (ValueError, TypeError) as error:
            if attempt == 1:
                raise
            messages.extend([("assistant", graded.content),
                             ("human", f"Repair the JSON schema only. Validation error: {error}. "
                              "Return all required fields, including unsupported_claims as an array of strings.")])
    input_tokens = usage.get("input_tokens", 0) + generation_usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0) + generation_usage.get("output_tokens", 0)
    return {
        "output": {"id": case["id"], "variant": variant, "answer": answer, "grade": grade,
                   "generation_usage": generation_usage, "grading_usage": usage,
                   "grading_attempts": attempts},
        "tokenUsage": {"prompt": input_tokens, "completion": output_tokens,
                       "total": input_tokens + output_tokens},
    }
