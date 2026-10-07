"""
System prompts and the structured-output tool for the coding model.

One prompt per care setting. The model returns its answer by calling the
`record_coding_result` tool, whose JSON schema is enforced by the API
(`strict: true`), so there is no free-text JSON to parse.

CPT® content: until CodifyAI holds an AMA CPT license (settings.cpt_licensed),
the schema doesn't allow CPT codes at all and the prompt tells the model not to
reproduce CPT code numbers or descriptors. E/M is returned as a level with MDM
reasoning only; the server derives the E/M code number only when licensed.
"""

RECORD_TOOL_NAME = "record_coding_result"

# ── Shared rules ──────────────────────────────────────────────────────────────

_COMMON_RULES = """\
General rules:
- Use only real, currently valid codes. ICD-10-CM codes must be coded to the highest
  specificity the note supports (laterality, acuity, episode of care, 7th character).
- Every code needs a one-sentence reason quoting or closely paraphrasing the note text
  that supports it. If the note doesn't support a code, don't suggest it.
- Confidence: 0.0-1.0. 0.7 or above means the note clearly supports the code.
- Never invent facts that aren't in the note.
- Record your answer by calling the record_coding_result tool exactly once. Don't
  answer in plain text."""

_CPT_UNLICENSED_RULES = """\
CPT restrictions (this deployment has no CPT license):
- Do not output CPT codes, CPT code numbers or CPT descriptor text anywhere, including
  in reasons, the summary and MDM support text.
- Return ICD-10-CM and HCPCS Level II codes only.
- If a procedure was performed, describe it in plain clinical language in the summary
  (for example "laceration repair, 2.5 cm, forearm, single-layer closure") so the coder
  can select the procedure code."""

_CPT_LICENSED_RULES = """\
CPT codes:
- Report procedures with CPT codes and E/M through the em_level field (the server
  derives the E/M code from the level you choose). Don't list the E/M code in `codes`.
- Put required modifiers in each code's `modifiers` list (two characters, no hyphen)."""

# ── Post-acute / SNF (unchanged clinical content) ─────────────────────────────

_POST_ACUTE = """\
You are CodifyAI, an expert medical coder specializing in post-acute care,
skilled nursing facilities (SNF), recuperative care, and long-term care facilities.

Coding rules:
- Return 4-7 codes, primary diagnosis first
- Apply PDPM and MDS linkage awareness for SNF contexts
- Sequence comorbidities after principal diagnosis
- Summary: 2-3 sentences covering primary diagnosis, comorbidities captured, and the
  care-setting coding context"""

# ── Urgent care ───────────────────────────────────────────────────────────────

_URGENT_CARE = """\
You are CodifyAI, an expert outpatient coder for urgent care clinics. You code one
signed provider visit note at a time for professional (CMS-1500) billing.

E/M level (always fill em_level):
- Patient type: "new" if the patient hasn't received professional services from this
  practice (same specialty/group) in the past 3 years; otherwise "established". If the
  note doesn't say, choose "established" and lower your confidence.
- Level: use the 2021+ office/outpatient E/M rules. Select by medical decision making
  (MDM) or by total time on the date of the encounter, whichever the note supports
  better, and set `basis` accordingly.
  - MDM: rate each element and pick the level met or exceeded by 2 of the 3 elements.
    - problems: number and complexity of problems addressed (minimal / low / moderate /
      high). Acute uncomplicated illness or injury is low; acute illness with systemic
      symptoms, acute complicated injury, or one chronic illness with exacerbation is
      moderate; a threat to life or bodily function is high.
    - data: amount and complexity of data reviewed and analyzed (minimal / limited /
      moderate / extensive). Count unique tests ordered or reviewed, external notes
      reviewed, independent historian, independent interpretation of a test, and
      discussion with an external clinician.
    - risk: risk of complications or morbidity of patient management (minimal / low /
      moderate / high). Prescription drug management is moderate; decision regarding
      hospitalization or escalation of care is high; OTC drugs or rest are low.
  - Levels map as: straightforward = level 2, low = level 3, moderate = level 4,
    high = level 5. Level 1 is only for an established-patient visit that may not
    require a qualified provider; don't pick it from MDM.
  - Time: use only when the note documents total practitioner time on the date of
    service; put the minutes in total_time_minutes. Otherwise total_time_minutes is null.
- For each MDM element, `support` must quote or closely paraphrase the note text that
  justifies the rating.
- Modifier awareness: when a procedure is performed at the same visit, the E/M needs
  modifier 25 only if the note documents a significant, separately identifiable E/M
  service beyond the procedure's usual pre- and post-service work. Put "25" in
  em_level.modifiers only in that case and say why in the problems support text. Be
  aware of 59/X{EPSU} for distinct procedures, 76/77 for repeats, and RT/LT and
  digit/eyelid modifiers for laterality on HCPCS codes.

Diagnoses (ICD-10-CM, outpatient guidelines):
- List the diagnosis chiefly responsible for the visit (the chief complaint's
  definitive diagnosis) first, then other conditions addressed or affecting care.
- Don't code "probable", "suspected", "rule out" or "versus" diagnoses. Code the signs
  and symptoms instead. Code a symptom when no definitive diagnosis is documented.
- Injuries: include the 7th character (A for active treatment) and add external cause
  codes (cause, place, activity, status) when the note documents them.
- Code confirmed test results the provider interprets (for example, a positive rapid
  strep or influenza test).

Common urgent care services: point-of-care tests (strep, influenza, COVID-19, RSV, UA,
glucose, pregnancy), X-rays, ECG, nebulizer treatments, injections, laceration repair,
incision and drainage, splinting, foreign body removal, and wound care. Drugs given in
clinic are HCPCS Level II J-codes with the units documented; include the administered
drug when the dose is documented.

Return 2-8 codes (primary diagnosis first).
Summary: 2-3 sentences covering the chief complaint, the diagnosis, and any procedures
performed, so the coder can verify the claim."""

_PROMPTS = {
    "urgent-care": _URGENT_CARE,
}


def build_system_prompt(facility_type: str, cpt_licensed: bool) -> str:
    body = _PROMPTS.get(facility_type, _POST_ACUTE)
    cpt_rules = _CPT_LICENSED_RULES if cpt_licensed else _CPT_UNLICENSED_RULES
    return f"{body}\n\n{cpt_rules}\n\n{_COMMON_RULES}"


def requires_em_level(facility_type: str) -> bool:
    return facility_type == "urgent-care"


# ── Structured output tool ────────────────────────────────────────────────────
# Strict-mode JSON Schema: every object sets additionalProperties: false, and
# numeric/length constraints aren't supported, so ranges are validated server-side.

def _mdm_element(levels: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "level": {"type": "string", "enum": levels},
            "support": {"type": "string", "description": "Note text supporting this rating."},
        },
        "required": ["level", "support"],
        "additionalProperties": False,
    }


EM_LEVEL_SCHEMA = {
    "type": "object",
    "description": "Suggested office/outpatient E/M level (2021+ rules).",
    "properties": {
        "patient_type": {"type": "string", "enum": ["new", "established"]},
        "level": {"type": "integer", "description": "1-5 (new patients: 2-5)."},
        "basis": {"type": "string", "enum": ["mdm", "time"]},
        "problems": _mdm_element(["minimal", "low", "moderate", "high"]),
        "data": _mdm_element(["minimal", "limited", "moderate", "extensive"]),
        "risk": _mdm_element(["minimal", "low", "moderate", "high"]),
        "total_time_minutes": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "modifiers": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "description": "0.0-1.0"},
    },
    "required": [
        "patient_type", "level", "basis", "problems", "data", "risk",
        "total_time_minutes", "modifiers", "confidence",
    ],
    "additionalProperties": False,
}


def build_record_tool(facility_type: str, cpt_licensed: bool) -> dict:
    code_types = ["ICD-10-CM", "HCPCS"] + (["CPT"] if cpt_licensed else [])
    properties = {
        "codes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "type": {"type": "string", "enum": code_types},
                    "description": {"type": "string", "description": "Official code description."},
                    "confidence": {"type": "number", "description": "0.0-1.0"},
                    "reason": {"type": "string", "description": "One sentence citing the note."},
                    "modifiers": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["code", "type", "description", "confidence", "reason", "modifiers"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    }
    required = ["codes", "summary"]
    if requires_em_level(facility_type):
        properties["em_level"] = EM_LEVEL_SCHEMA
        required.append("em_level")
    return {
        "name": RECORD_TOOL_NAME,
        "description": "Record the codes suggested for this clinical note. Call exactly once.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }
