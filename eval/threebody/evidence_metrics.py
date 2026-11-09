"""Annotated evidence coverage with explicit non-applicability for abstention cases."""


def evidence_metrics(case, indexes):
    if case["behavior"] == "abstain":
        return {"evidence_groups_hit": [], "evidence_coverage": None,
                "all_evidence_found": None, "evidence_applicable": False}
    groups = case.get("evidence", [])
    if not groups:
        raise ValueError("Answerable case has no evidence annotation")
    indexes = set(indexes)
    hits = [bool(indexes.intersection(e["acceptable_indexes"])) for e in groups]
    return {"evidence_groups_hit": hits, "evidence_coverage": sum(hits) / len(hits),
            "all_evidence_found": all(hits), "evidence_applicable": True}
