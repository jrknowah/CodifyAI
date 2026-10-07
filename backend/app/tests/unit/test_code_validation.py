import pytest
from app.services.code_validation import (
    check_em_level, em_cpt_code, level_from_time, mdm_level_from_elements,
    normalize_code, validate_codes,
)
from app.services.coding_prompts import build_record_tool, build_system_prompt


def code(c, t="ICD-10-CM", conf=0.9, mods=None):
    return {"code": c, "type": t, "description": "d", "confidence": conf, "reason": "r", "modifiers": mods or []}


@pytest.mark.parametrize("raw,expected", [
    ("I10", "I10"), ("e11.9", "E11.9"), ("E119", "E11.9"), ("S61.411A", "S61.411A"),
    ("S61411A", "S61.411A"), ("J02.0.", "J02.0"), (" z96.641 ", "Z96.641"),
])
def test_icd10cm_normalization(raw, expected):
    assert normalize_code(raw, "ICD-10-CM") == expected


@pytest.mark.parametrize("good", ["U07.1", "U09.9", "J06.9", "W54.0XXA", "Z20.822"])
def test_valid_icd10cm_kept(good):
    kept, flagged = validate_codes([code(good)], cpt_licensed=False)
    assert [c["code"] for c in kept] == [good] and flagged == []


@pytest.mark.parametrize("bad", ["110", "I1", "ABC.12", "E11.12345", "99213", "", "J02.0-"])
def test_invalid_icd10cm_flagged(bad):
    kept, flagged = validate_codes([code(bad)], cpt_licensed=False)
    assert kept == [] and flagged[0]["issue"] == "not a valid ICD-10-CM code format"


def test_hcpcs_and_cpt_formats():
    kept, flagged = validate_codes(
        [code("J0696", "HCPCS"), code("J69", "HCPCS"), code("87880", "CPT"), code("8788X", "CPT")],
        cpt_licensed=True,
    )
    assert [c["code"] for c in kept] == ["J0696", "87880"]
    assert len(flagged) == 2


def test_cpt_dropped_without_code_when_unlicensed():
    kept, flagged = validate_codes([code("87880", "CPT"), code("I10")], cpt_licensed=False)
    assert [c["code"] for c in kept] == ["I10"]
    assert flagged == [{"code": None, "type": "CPT", "issue": "CPT output disabled (no CPT license)"}]


def test_confidence_out_of_range_and_duplicates():
    kept, flagged = validate_codes([code("I10", conf=1.4), code("E11.9"), code("E119")], cpt_licensed=False)
    assert [c["code"] for c in kept] == ["E11.9"]
    assert flagged[0]["issue"] == "confidence outside 0-1"


def test_modifiers_normalized():
    kept, flagged = validate_codes([code("J0696", "HCPCS", mods=["-jz", "RT", "bogus"])], cpt_licensed=False)
    assert kept[0]["modifiers"] == ["JZ", "RT"]
    assert "invalid modifier" in flagged[0]["issue"]


# ── E/M rules ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("problems,data,risk,level", [
    ("minimal", "minimal", "minimal", 2),
    ("low", "minimal", "low", 3),         # 2 of 3 at low
    ("moderate", "limited", "moderate", 4),
    ("high", "minimal", "minimal", 2),    # one high element isn't enough
    ("high", "extensive", "low", 5),
    ("moderate", "extensive", "low", 4),
])
def test_mdm_two_of_three(problems, data, risk, level):
    assert mdm_level_from_elements(problems, data, risk) == level


@pytest.mark.parametrize("ptype,minutes,level", [
    ("new", 14, None), ("new", 15, 2), ("new", 30, 3), ("new", 45, 4), ("new", 60, 5),
    ("established", 9, None), ("established", 10, 2), ("established", 20, 3),
    ("established", 30, 4), ("established", 40, 5), ("established", None, None),
])
def test_time_thresholds(ptype, minutes, level):
    assert level_from_time(ptype, minutes) == level


def test_em_code_mapping():
    assert em_cpt_code("new", 3) == "99203"
    assert em_cpt_code("established", 1) == "99211"
    assert em_cpt_code("new", 1) is None


def _em(**kw):
    em = {"patient_type": "established", "level": 3, "basis": "mdm",
          "problems": {"level": "low", "support": "s"}, "data": {"level": "limited", "support": "s"},
          "risk": {"level": "low", "support": "s"}, "total_time_minutes": None, "modifiers": [], "confidence": 0.8}
    em.update(kw)
    return em


def test_check_em_level_unlicensed_has_no_code():
    out = check_em_level(_em(), cpt_licensed=False)
    assert out["consistent"] and out["cpt_code"] is None and out["review_label"] == "For coder review"


def test_check_em_level_time_basis():
    out = check_em_level(_em(basis="time", level=4, total_time_minutes=32), cpt_licensed=True)
    assert out["consistent"] and out["cpt_code"] == "99214"
    out = check_em_level(_em(basis="time", level=4, total_time_minutes=5), cpt_licensed=False)
    assert not out["consistent"]


@pytest.mark.parametrize("bad", [dict(patient_type="new", level=1), dict(level=6), dict(confidence=2.0)])
def test_check_em_level_rejects_invalid(bad):
    with pytest.raises(ValueError):
        check_em_level(_em(**bad), cpt_licensed=False)


# ── Prompts and schema ────────────────────────────────────────────────────────

def _objects(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield schema
        for v in schema.values():
            yield from _objects(v)
    elif isinstance(schema, list):
        for v in schema:
            yield from _objects(v)


@pytest.mark.parametrize("facility", ["post-acute", "urgent-care"])
@pytest.mark.parametrize("licensed", [True, False])
def test_tool_schema_is_strict_compatible(facility, licensed):
    tool = build_record_tool(facility, licensed)
    assert tool["strict"] is True
    for obj in _objects(tool["input_schema"]):
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
    assert "minimum" not in str(tool) and "maximum" not in str(tool)


def test_prompts_are_setting_specific():
    snf = build_system_prompt("snf", False)
    uc = build_system_prompt("urgent-care", False)
    assert "PDPM" in snf and "PDPM" not in uc
    assert "2021+" in uc and "established" in uc
    assert "Do not output CPT codes" in uc
    assert "Do not output CPT codes" not in build_system_prompt("urgent-care", True)
