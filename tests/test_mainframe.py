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
    extract_hlasm,
    extract_ims,
    extract_bms,
    extract_ddl,
    _cobol_regex_extract,
    _decolumn_cobol,
    _strip_cobol_for_grammar,
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
    deco = _decolumn_cobol(src)
    _, copybooks = _strip_cobol_for_grammar(deco)
    r = _cobol_regex_extract(FIXTURES / "sample.cbl", deco, copybooks)
    _assert_schema_ok(r)
    labels = _labels(r)
    assert "SAMPLEPGM" in labels
    assert "MAIN-PARA" in labels
    assert ("sample.cbl", "CUSTREC") in _edges(r, "includes")
    assert any(t == "SUBPGM01" for _, t in _edges(r, "calls"))
    # CALL/PERFORM should be attributed to the enclosing paragraph, not the program.
    assert ("MAIN-PARA", "SUBPGM01") in _edges(r, "calls")
    assert ("MAIN-PARA", "INIT-PARA") in _edges(r, "calls")


@pytest.mark.skipif(not _ANTLR_AVAILABLE, reason="antlr4-python3-runtime not installed")
def test_cobol_uses_antlr_when_available():
    # The ANTLR grammar attributes CALL edges to the enclosing paragraph, which
    # the (program-scoped) regex fallback cannot do.
    r = extract_cobol(FIXTURES / "sample.cbl")
    calls = _edges(r, "calls")
    assert ("MAIN-PARA", "SUBPGM01") in calls


# ── COBOL: real-world dialect features (AUTHOR entries, embedded SQL/CICS, GO TO) ─

def test_cobol_db2_no_error_despite_comment_entries():
    r = extract_cobol(FIXTURES / "sample_db2.cbl")
    assert "error" not in r
    _assert_schema_ok(r)


def test_cobol_db2_finds_all_paragraphs():
    # AUTHOR./INSTALLATION./REMARKS. free text must not derail paragraph extraction.
    r = extract_cobol(FIXTURES / "sample_db2.cbl")
    labels = _labels(r)
    for name in ("SAMPLE2", "0100-INIT", "0200-FETCH-CUST", "0300-POST", "0999-ERROR"):
        assert name in labels


def test_cobol_db2_embedded_sql_and_cics():
    r = extract_cobol(FIXTURES / "sample_db2.cbl")
    includes = _edges(r, "includes")
    assert any(t == "SQLCA" for _, t in includes)        # EXEC SQL INCLUDE
    assert any(t == "CUSTROW" for _, t in includes)
    uses = _edges(r, "uses")
    assert any(t == "ACMEDB.CUSTOMER_TBL" for _, t in uses)   # EXEC SQL ... FROM/UPDATE
    assert any(t == "ACMEDB.ACCOUNT_TBL" for _, t in uses)    # EXEC SQL ... JOIN
    assert any(t == "CONFMAP" for _, t in uses)               # EXEC CICS SEND MAP
    calls = _edges(r, "calls")
    assert any(t == "POSTPGM" for _, t in calls)              # EXEC CICS LINK PROGRAM
    assert any(t == "AUDITLOG" for _, t in calls)             # static CALL 'literal'
    # "DISPLAY 'PLEASE CALL SUPPORT ...'" must NOT produce a CALL edge.
    assert all(t != "SUPPORT" for _, t in calls)


def test_cobol_db2_go_to_edge():
    r = extract_cobol(FIXTURES / "sample_db2.cbl")
    assert ("0200-FETCH-CUST", "0999-ERROR") in _edges(r, "calls")


def test_cobol_db2_sql_scoped_to_paragraph():
    # Embedded-SQL "uses" edges should be attributed to the enclosing paragraph.
    r = extract_cobol(FIXTURES / "sample_db2.cbl")
    uses = _edges(r, "uses")
    assert ("0200-FETCH-CUST", "ACMEDB.CUSTOMER_TBL") in uses


# ── Cross-file linking through the full extract() pipeline ────────────────────

def test_cobol_cross_file_call_links_to_program():
    from graphify.extract import extract
    from graphify.build import build_from_json
    paths = [FIXTURES / "sample.cbl", FIXTURES / "sample_sub.cbl", FIXTURES / "sample_run.jcl"]
    ex = extract(paths, cache_root=FIXTURES, parallel=False)
    G = build_from_json(ex, directed=True)
    lab = {n: d.get("label") for n, d in G.nodes(data=True)}
    edges = {(lab.get(s), lab.get(t), d.get("relation")) for s, t, d in G.edges(data=True)}
    # sample.cbl: MAIN-PARA CALLs 'SUBPGM01'; sample_sub.cbl: PROGRAM-ID. SUBPGM01.
    assert ("MAIN-PARA", "SUBPGM01", "calls") in edges
    # sample_run.jcl: a step EXECs PGM=SUBPGM01 — links to the same program node.
    assert any(t == "SUBPGM01" and r_ == "executes" for _, t, r_ in edges)
    # SUBPGM01 must be a single node (CALL target, PGM= target and PROGRAM-ID merge).
    assert len([n for n, l in lab.items() if l == "SUBPGM01"]) == 1
    # The merged program node should have its own paragraph defined.
    assert ("SUBPGM01", "VALIDATE-PARA", "defines") in edges


# ── JCL in-stream procedures ──────────────────────────────────────────────────

def test_jcl_instream_proc():
    r = extract_jcl(FIXTURES / "sample_proc.jcl")
    _assert_schema_ok(r)
    labels = _labels(r)
    assert "LOADPROC" in labels                                # in-stream PROC defined
    assert ("sample_proc.jcl", "LOADPROC") in _edges(r, "defines")
    assert ("LOADPROC", "PLOAD") in _edges(r, "defines")       # step belongs to the PROC
    assert ("RUNLOAD", "LOADPROC") in _edges(r, "calls")       # invoked via EXEC LOADPROC
    # DSN on a DD continuation line is still captured.
    assert any(t == "PROD.AUDIT.LOG" for _, t in _edges(r, "reads"))


# ── PL/I FETCH and REXX function-style calls (inline source) ──────────────────

def test_pli_fetch_edge(tmp_path):
    p = tmp_path / "x.pli"
    p.write_text(
        " MAINP: PROCEDURE OPTIONS(MAIN);\n"
        "   FETCH DYNMOD;\n"
        "   CALL DYNMOD;\n"
        " END MAINP;\n"
    )
    r = extract_pli(p)
    calls = {t for _, t in _edges(r, "calls")}
    assert "DYNMOD" in calls


def test_rexx_internal_function_call(tmp_path):
    p = tmp_path / "x.rexx"
    p.write_text(
        "/* REXX */\n"
        "say DOUBLE(21)\n"
        "exit\n"
        "DOUBLE: procedure\n"
        "  parse arg n\n"
        "  return n * 2\n"
    )
    r = extract_rexx(p)
    assert "DOUBLE" in _labels(r)
    assert any(t == "DOUBLE" for _, t in _edges(r, "calls"))


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
    deco = _decolumn_cobol(src)
    # Free-format detection must not strip columns 1-7 here.
    assert "IDENTIFICATION DIVISION." in deco
    r = _cobol_regex_extract(Path("free.cbl"), deco, [])
    assert "FREEPGM" in _labels(r)
    assert "MAIN-PARA" in _labels(r)
    assert ("MAIN-PARA", "OTHERPGM") in _edges(r, "calls")


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
    (".ddl", "extract_ddl"),
    (".asm", "extract_hlasm"),
    (".mlc", "extract_hlasm"),
    (".hlasm", "extract_hlasm"),
    (".dbd", "extract_ims"),
    (".psb", "extract_ims"),
    (".bms", "extract_bms"),
    (".mapset", "extract_bms"),
    (".proc", "extract_jcl"),
])
def test_dispatch_registered(suffix, expected):
    from graphify.extract import _DISPATCH
    assert suffix in _DISPATCH
    assert _DISPATCH[suffix].__name__ == expected


def test_extensions_in_detect():
    from graphify.detect import CODE_EXTENSIONS
    for ext in (".cob", ".cbl", ".cobol", ".cpy", ".copy", ".jcl", ".proc", ".pli", ".pl1",
                ".rexx", ".rex", ".ddl", ".asm", ".mlc", ".hlasm", ".dbd", ".psb", ".bms", ".mapset"):
        assert ext in CODE_EXTENSIONS


# ── HLASM (mainframe assembler) ───────────────────────────────────────────────

def test_hlasm_no_error():
    r = extract_hlasm(FIXTURES / "sample.asm")
    assert "error" not in r
    _assert_schema_ok(r)


def test_hlasm_control_sections_and_macros():
    r = extract_hlasm(FIXTURES / "sample.asm")
    labels = _labels(r)
    assert "MYPROG" in labels          # CSECT
    assert "WORKAREA" in labels        # DSECT
    assert "MYMAC" in labels           # MACRO definition
    # No bogus opcode/operand "definitions" leaked in.
    for junk in ("DC", "DS", "BR", "CL8", "END", "MACRO", "A"):
        assert junk not in labels


def test_hlasm_call_and_extern_edges():
    r = extract_hlasm(FIXTURES / "sample.asm")
    calls = {t for _, t in _edges(r, "calls")}
    assert "SUBRTN1" in calls          # CALL macro (positional)
    assert "SUBRTN2" in calls          # LINK EP=...
    assert "EXTSUB3" in calls          # =V(...) address constant
    assert any(t == "MYMACROS" for _, t in _edges(r, "includes"))   # COPY include


# ── IMS DBD / PSB ─────────────────────────────────────────────────────────────

def test_ims_dbd_segment_hierarchy():
    r = extract_ims(FIXTURES / "sample.dbd")
    assert "error" not in r
    _assert_schema_ok(r)
    labels = _labels(r)
    assert "CUSTDB" in labels
    for seg in ("CUSTOMER", "ORDER", "ORDLINE"):
        assert seg in labels
    contains = _edges(r, "contains")
    assert ("CUSTDB", "CUSTOMER") in contains
    assert ("CUSTOMER", "ORDER") in contains
    assert ("ORDER", "ORDLINE") in contains


def test_ims_psb_uses_databases():
    r = extract_ims(FIXTURES / "sample.psb")
    assert "error" not in r
    _assert_schema_ok(r)
    uses = {t for _, t in _edges(r, "uses")}
    assert "CUSTDB" in uses
    assert "ITEMDB" in uses
    assert "CUSTPSB" in _labels(r)     # PSBGEN PSBNAME=


def test_ims_dbd_psb_segment_ids_match():
    # A PSB's SENSEG and the owning DBD's SEGM produce the same node id,
    # so a PSB and its DBDs link up when both are in the corpus.
    from graphify.extract import extract
    from graphify.build import build_from_json
    ex = extract([FIXTURES / "sample.dbd", FIXTURES / "sample.psb"], cache_root=FIXTURES, parallel=False)
    G = build_from_json(ex, directed=True)
    lab = {n: d.get("label") for n, d in G.nodes(data=True)}
    # CUSTOMER segment appears once, referenced by both the DBD (contains) and the PSB (uses).
    cust_ids = [n for n, l in lab.items() if l == "CUSTOMER"]
    assert len(cust_ids) == 1
    deg = G.in_degree(cust_ids[0]) + G.out_degree(cust_ids[0])
    assert deg >= 2


# ── CICS BMS ──────────────────────────────────────────────────────────────────

def test_bms_mapset_and_maps():
    r = extract_bms(FIXTURES / "sample.bms")
    assert "error" not in r
    _assert_schema_ok(r)
    labels = _labels(r)
    assert "CONFSET" in labels
    assert "CONFMAP" in labels
    assert "ERRMAP" in labels
    assert ("CONFSET", "CONFMAP") in _edges(r, "defines")


def test_bms_map_id_matches_cobol_send_map():
    from graphify.extract import _make_id
    r = extract_bms(FIXTURES / "sample.bms")
    confmap = next(n for n in r["nodes"] if n["label"] == "CONFMAP")
    # COBOL `EXEC CICS SEND MAP('CONFMAP')` emits a node with this same id.
    assert confmap["id"] == _make_id("map", "CONFMAP")


# ── DB2 / SQL DDL ─────────────────────────────────────────────────────────────

def test_ddl_extracts_tables():
    r = extract_ddl(FIXTURES / "sample.ddl")
    assert "error" not in r
    labels = " ".join(_labels(r))
    assert "CUSTOMER" in labels
    assert "ORDERS" in labels


def test_ddl_regex_fallback(tmp_path):
    # Exercise the dependency-free fallback directly (independent of tree-sitter-sql).
    from graphify.extract import extract_sql
    p = tmp_path / "db2.ddl"
    p.write_text(
        "CREATE TABLESPACE TS1 IN MYDB;\n"
        "CREATE TABLE APP.CUSTOMER (CUST_ID INT NOT NULL PRIMARY KEY);\n"
        "CREATE TABLE APP.ORDERS (ORDER_ID INT, CUST_ID INT,\n"
        "  FOREIGN KEY (CUST_ID) REFERENCES APP.CUSTOMER (CUST_ID));\n"
        "CREATE UNIQUE INDEX APP.CUSTIX ON APP.CUSTOMER (CUST_ID);\n"
    )
    sql_r = extract_sql(p)
    if "error" not in sql_r:
        pytest.skip("tree-sitter-sql is installed; the regex fallback isn't exercised here")
    r = extract_ddl(p)
    _assert_schema_ok(r)
    labels = " ".join(_labels(r))
    assert "APP.CUSTOMER" in labels and "APP.ORDERS" in labels and "TS1" in labels
    refs = _edges(r, "references")
    assert any(s == "APP.ORDERS" and t == "APP.CUSTOMER" for s, t in refs)
