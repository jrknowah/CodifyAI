"""
Checks on what the model returns, before anything reaches the coder.

These are *format* checks: they catch malformed or hallucinated-looking codes and
codes of a type this deployment may not show (CPT without a license). They don't
prove a code exists in the current code set — that needs the CMS ICD-10-CM / HCPCS
files loaded as reference data.
"""
import re

# Any letter first: ICD-10-CM uses U codes (U07.1 COVID-19, U09.9 post-COVID)
ICD10CM_RE = re.compile(r"^[A-Z][0-9][0-9A-Z](\.[0-9A-Z]{1,4})?$")
HCPCS_RE = re.compile(r"^[A-V][0-9]{4}$")
CPT_RE = re.compile(r"^[0-9]{4}[0-9FTU]$")
MODIFIER_RE = re.compile(r"^[0-9A-Z]{2}$")

FORMAT_BY_TYPE = {"ICD-10-CM": ICD10CM_RE, "HCPCS": HCPCS_RE, "CPT": CPT_RE}


def normalize_code(code: str, code_type: str) -> str:
    code = code.strip().upper().replace(" ", "")
    if code_type == "ICD-10-CM":
        code = code.rstrip(".")
        # ICD-10-CM codes longer than 3 characters carry a dot after the category
        if "." not in code and len(code) > 3:
            code = f"{code[:3]}.{code[3:]}"
    return code


def normalize_modifiers(modifiers: list[str]) -> tuple[list[str], list[str]]:
    """Returns (valid, invalid). Accepts "-25" / "25" style input."""
    valid, invalid = [], []
    for m in modifiers:
        m = m.strip().upper().lstrip("-")
        (valid if MODIFIER_RE.match(m) else invalid).append(m)
    return valid, invalid


def validate_codes(codes: list[dict], cpt_licensed: bool) -> tuple[list[dict], list[dict]]:
    """
    Split model output into (kept, flagged). Each flagged entry says why it was
    dropped. CPT is dropped silently when unlicensed (it must never be shown) and
    recorded with only the type — no code number or descriptor.
    """
    kept, flagged, seen = [], [], set()
    for c in codes:
        code_type = c["type"]
        if code_type == "CPT" and not cpt_licensed:
            flagged.append({"code": None, "type": "CPT", "issue": "CPT output disabled (no CPT license)"})
            continue
        code = normalize_code(c["code"], code_type)
        pattern = FORMAT_BY_TYPE.get(code_type)
        if pattern is None or not pattern.match(code):
            flagged.append({"code": code[:20], "type": code_type, "issue": f"not a valid {code_type} code format"})
            continue
        if not 0.0 <= float(c["confidence"]) <= 1.0:
            flagged.append({"code": code, "type": code_type, "issue": "confidence outside 0-1"})
            continue
        if (code, code_type) in seen:
            continue  # duplicate suggestion
        seen.add((code, code_type))
        modifiers, bad = normalize_modifiers(c.get("modifiers", []))
        if bad:
            flagged.append({"code": code, "type": code_type, "issue": f"invalid modifier(s) dropped: {', '.join(bad)[:40]}"})
        kept.append({**c, "code": code, "modifiers": modifiers})
    return kept, flagged


# ── E/M (2021+ office/outpatient) ─────────────────────────────────────────────

_ELEMENT_RANK = {
    "problems": {"minimal": 1, "low": 2, "moderate": 3, "high": 4},
    "data": {"minimal": 1, "limited": 2, "moderate": 3, "extensive": 4},
    "risk": {"minimal": 1, "low": 2, "moderate": 3, "high": 4},
}
MDM_NAMES = {1: "straightforward", 2: "low", 3: "moderate", 4: "high"}

# Total time on the date of the encounter (2021 office/outpatient thresholds), minutes
_TIME_THRESHOLDS = {
    "new": [(60, 5), (45, 4), (30, 3), (15, 2)],
    "established": [(40, 5), (30, 4), (20, 3), (10, 2)],
}


def mdm_level_from_elements(problems: str, data: str, risk: str) -> int:
    """MDM level is the highest level met by at least 2 of the 3 elements.
    Returns the E/M level (2-5)."""
    ranks = sorted([
        _ELEMENT_RANK["problems"][problems],
        _ELEMENT_RANK["data"][data],
        _ELEMENT_RANK["risk"][risk],
    ], reverse=True)
    return ranks[1] + 1  # second-highest rank, mapped straightforward(1) -> level 2


def level_from_time(patient_type: str, minutes: int | None) -> int | None:
    if minutes is None:
        return None
    for floor, level in _TIME_THRESHOLDS[patient_type]:
        if minutes >= floor:
            return level
    return None


def em_cpt_code(patient_type: str, level: int) -> str | None:
    """Office/outpatient E/M code number for a level. Only used when CPT-licensed."""
    if patient_type == "new" and 2 <= level <= 5:
        return f"9920{level}"
    if patient_type == "established" and 1 <= level <= 5:
        return f"9921{level}"
    return None


def check_em_level(em: dict, cpt_licensed: bool) -> dict:
    """Validate the model's E/M suggestion and add the server's own computation.
    Returns the enriched dict; raises ValueError if it's unusable."""
    patient_type, level = em["patient_type"], int(em["level"])
    if not (2 if patient_type == "new" else 1) <= level <= 5:
        raise ValueError(f"E/M level {level} is invalid for a {patient_type} patient")
    if not 0.0 <= float(em["confidence"]) <= 1.0:
        raise ValueError("E/M confidence outside 0-1")

    mdm_level = mdm_level_from_elements(em["problems"]["level"], em["data"]["level"], em["risk"]["level"])
    time_level = level_from_time(patient_type, em.get("total_time_minutes"))
    expected = time_level if em["basis"] == "time" and time_level else mdm_level
    modifiers, _ = normalize_modifiers(em.get("modifiers", []))

    notes = []
    if level != expected:
        source = "documented time" if em["basis"] == "time" and time_level else "MDM elements (2 of 3)"
        notes.append(f"Suggested level {level} doesn't match level {expected} computed from the {source}.")
    if em["basis"] == "time" and time_level is None:
        notes.append("Time basis selected but the documented time doesn't meet a level threshold.")

    return {
        **em,
        "level": level,
        "modifiers": modifiers,
        "mdm_level": MDM_NAMES[mdm_level - 1],
        "computed_level": expected,
        "consistent": not notes,
        "consistency_notes": notes,
        "cpt_code": em_cpt_code(patient_type, level) if cpt_licensed else None,
        "review_label": "For coder review",
    }
