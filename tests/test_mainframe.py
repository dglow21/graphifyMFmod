"""Tests for the mainframe extractors: COBOL (ProLeap ANTLR4 grammar + regex
fallback), COBOL copybooks, JCL, PL/I and REXX."""
from __future__ import annotations
from pathlib import Path

import pytest

from graphify.extract import (
    extract_cobol,
    extract_copybook,
    extract_jcl,
    extract_pli,
    extract_rexx,
    _cobol_regex_extract,
    _normalize_cobol_source,
)
from graphify.validate import validate_extraction

FIXTURES = Path(__file__).parent / "fixtures"

_ANTLR_AVAILABLE = True
try:  # pragma: no cover - depends on optional extra
    import antlr4  # noqa: F401
except ImportError:  # pragma: no cover
    _ANTLR_AVAILABLE = False


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def _edges(r, relation):
    by_id = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (by_id.get(e["source"], e["source"]), by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == relation
    }


def _assert_schema_ok(r):
    real = [e for e in validate_extraction(r) if "does not match any node id" not in e]
    assert real == [], real


# ── COBOL (ANTLR4 path when available, else regex fallback) ───────────────────

def test_cobol_no_error():
    r = extract_cobol(FIXTURES / "sample.cbl")
    assert "error" not in r
    _assert_schema_ok(r)


def test_cobol_finds_program_id():
    r = extract_cobol(FIXTURES / "sample.cbl")
    assert "SAMPLEPGM" in _labels(r)


def test_cobol_finds_paragraphs_and_section():
    r = extract_cobol(FIXTURES / "sample.cbl")
    labels = _labels(r)
    for name in ("MAIN-SECTION", "MAIN-PARA", "INIT-PARA", "PROCESS-PARA"):
        assert name in labels
    defines = _edges(r, "defines")
    assert ("SAMPLEPGM", "MAIN-PARA") in defines


def test_cobol_perform_and_call_edges():
    r = extract_cobol(FIXTURES / "sample.cbl")
    calls = _edges(r, "calls")
    # PERFORM resolves to local paragraphs; CALL 'literal' resolves to programs.
    assert any(t == "INIT-PARA" for _, t in calls)
    assert any(t == "PROCESS-EXIT" for _, t in calls)  # PERFORM ... THRU PROCESS-EXIT
    assert any(t == "SUBPGM01" for _, t in calls)
    assert any(t == "SUBPGM02" for _, t in calls)


def test_cobol_copy_dependency():
    r = extract_cobol(FIXTURES / "sample.cbl")
    assert ("sample.cbl", "CUSTREC") in _edges(r, "includes")


def test_cobol_regex_fallback_matches_structure():
    src = (FIXTURES / "sample.cbl").read_text()
    normalized, copybooks = _normalize_cobol_source(src)
    r = _cobol_regex_extract(FIXTURES / "sample.cbl", src, normalized, copybooks)
    _assert_schema_ok(r)
    labels = _labels(r)
    assert "SAMPLEPGM" in labels
    assert "MAIN-PARA" in labels
    assert ("sample.cbl", "CUSTREC") in _edges(r, "includes")
    assert any(t == "SUBPGM01" for _, t in _edges(r, "calls"))


@pytest.mark.skipif(not _ANTLR_AVAILABLE, reason="antlr4-python3-runtime not installed")
def test_cobol_uses_antlr_when_available():
    # The ANTLR grammar attributes CALL edges to the enclosing paragraph, which
    # the (program-scoped) regex fallback cannot do.
    r = extract_cobol(FIXTURES / "sample.cbl")
    calls = _edges(r, "calls")
    assert ("MAIN-PARA", "SUBPGM01") in calls


def test_cobol_handles_free_format():
    src = (
        "IDENTIFICATION DIVISION.\n"
        "PROGRAM-ID. FREEPGM.\n"
        "PROCEDURE DIVISION.\n"
        "MAIN-PARA.\n"
        "    DISPLAY 'HI'.\n"
        "    CALL 'OTHERPGM'.\n"
        "    STOP RUN.\n"
    )
    norm, _ = _normalize_cobol_source(src)
    # Free-format detection must not strip columns 1-7 here.
    assert "IDENTIFICATION DIVISION." in norm


# ── COBOL copybook ────────────────────────────────────────────────────────────

def test_copybook_no_error():
    r = extract_copybook(FIXTURES / "sample.cpy")
    assert "error" not in r
    _assert_schema_ok(r)


def test_copybook_finds_records():
    r = extract_copybook(FIXTURES / "sample.cpy")
    labels = _labels(r)
    assert "CUSTOMER-RECORD" in labels
    assert "CUSTOMER-FLAGS" in labels
    # Subordinate 05-level items are not emitted (only 01-level records).
    assert "CUST-ID" not in labels


def test_copybook_file_node_keyed_on_member():
    # COPY edges from programs reference the bare member name, so the copybook
    # file node must be keyed on it for cross-file linking.
    from graphify.extract import _make_id
    r = extract_copybook(FIXTURES / "sample.cpy")
    file_node = r["nodes"][0]
    assert file_node["id"] == _make_id("sample")


# ── JCL ───────────────────────────────────────────────────────────────────────

def test_jcl_no_error():
    r = extract_jcl(FIXTURES / "sample.jcl")
    assert "error" not in r
    _assert_schema_ok(r)


def test_jcl_finds_job_and_steps():
    r = extract_jcl(FIXTURES / "sample.jcl")
    labels = _labels(r)
    assert "PAYROLL" in labels
    for step in ("STEP010", "STEP020", "STEP030"):
        assert step in labels
    assert ("PAYROLL", "STEP010") in _edges(r, "defines")


def test_jcl_program_and_proc_edges():
    r = extract_jcl(FIXTURES / "sample.jcl")
    assert any(t == "CUSTLOAD" for _, t in _edges(r, "executes"))
    assert any(t == "IEFBR14" for _, t in _edges(r, "executes"))
    assert any(t == "BILLPROC" for _, t in _edges(r, "calls"))
    assert ("sample.jcl", "CLEANUP") in _edges(r, "includes")


def test_jcl_dataset_edges():
    r = extract_jcl(FIXTURES / "sample.jcl")
    assert any(t == "PROD.CUSTOMER.MASTER" for _, t in _edges(r, "reads"))
    assert any(t == "PROD.CUSTOMER.EXTRACT" for _, t in _edges(r, "writes"))


# ── PL/I ──────────────────────────────────────────────────────────────────────

def test_pli_no_error():
    r = extract_pli(FIXTURES / "sample.pli")
    assert "error" not in r
    _assert_schema_ok(r)


def test_pli_finds_procedures_and_includes():
    r = extract_pli(FIXTURES / "sample.pli")
    labels = _labels(r)
    assert "SAMPLEPLI" in labels
    assert "INIT_DATA" in labels
    assert "PROCESS_RECORD" in labels
    assert ("sample.pli", "CUSTREC") in _edges(r, "includes")
    assert ("sample.pli", "SHARED") in _edges(r, "includes")


def test_pli_call_edges():
    r = extract_pli(FIXTURES / "sample.pli")
    calls = _edges(r, "calls")
    assert ("SAMPLEPLI", "INIT_DATA") in calls
    assert ("SAMPLEPLI", "PROCESS_RECORD") in calls
    # External routine call is dropped (no matching definition in this unit).
    assert all(t != "EXTERNAL_RTN" for _, t in calls)


# ── REXX ──────────────────────────────────────────────────────────────────────

def test_rexx_no_error():
    r = extract_rexx(FIXTURES / "sample.rexx")
    assert "error" not in r
    _assert_schema_ok(r)


def test_rexx_finds_routines_and_calls():
    r = extract_rexx(FIXTURES / "sample.rexx")
    labels = _labels(r)
    assert "INIT_VARS" in labels
    assert "PROCESS_DATA" in labels
    calls = _edges(r, "calls")
    assert ("sample.rexx", "INIT_VARS") in calls
    assert ("sample.rexx", "PROCESS_DATA") in calls


# ── Dispatch wiring ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("suffix,expected", [
    (".cob", "extract_cobol"),
    (".cbl", "extract_cobol"),
    (".cobol", "extract_cobol"),
    (".cpy", "extract_copybook"),
    (".copy", "extract_copybook"),
    (".jcl", "extract_jcl"),
    (".pli", "extract_pli"),
    (".pl1", "extract_pli"),
    (".rexx", "extract_rexx"),
    (".rex", "extract_rexx"),
    (".ddl", "extract_sql"),
])
def test_dispatch_registered(suffix, expected):
    from graphify.extract import _DISPATCH
    assert suffix in _DISPATCH
    assert _DISPATCH[suffix].__name__ == expected


def test_extensions_in_detect():
    from graphify.detect import CODE_EXTENSIONS
    for ext in (".cob", ".cbl", ".cobol", ".cpy", ".copy", ".jcl", ".pli", ".pl1", ".rexx", ".rex", ".ddl"):
        assert ext in CODE_EXTENSIONS
