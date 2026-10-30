import zipfile

from falseref.inputs import documents, to_pdf
from falseref.models import CheckResult, DocumentReport, Issue, Reference
from falseref.report import report_rows, summary, to_frame


def test_documents_unpacks_supported_files_from_a_zip(tmp_path):
    upload = tmp_path / "upload.zip"
    with zipfile.ZipFile(upload, "w") as z:
        for name in ("b.docx", "a.pdf", "notes.txt", "sub/c.PDF", "old.doc"):
            z.writestr(name, b"x")
    found = documents(upload, tmp_path / "work")
    assert [p.name for p in found] == ["a.pdf", "b.docx", "old.doc", "c.PDF"]


def test_documents_passes_a_single_file_through(tmp_path):
    assert documents(tmp_path / "essay.pdf", tmp_path) == [tmp_path / "essay.pdf"]


def test_to_pdf_leaves_pdfs_alone(tmp_path):
    assert to_pdf(tmp_path / "essay.PDF", tmp_path / "out") == tmp_path / "essay.PDF"


REF = Reference(raw="Kumar, A. (2020). Deep learning. Expert Systems, 7, 1-10.", authors=["A. Kumar"],
                title="Deep learning", year="2020", venue="Expert Systems", volume="7", pages="1-10")
RESULT = CheckResult(
    tier="partial", doi=None, url=None, notes=["the work's DOI is 10.1/x"], citation=[],
    sources=[{"name": "DOI", "state": "not given"}, {"name": "URL", "state": "not given"},
             {"name": "title", "state": "confirmed"}],
    rec={"title": ["Deep learning"], "author": [{"given": "Anna", "family": "Kumar"}],
         "issued": {"date-parts": [[2020]]}, "container-title": ["Expert Systems"],
         "DOI": "10.1/x", "volume": "9", "page": "1-10"},
    issues=[Issue("locator", "major", "volume: 7 vs 9")],
)


def test_report_rows_gives_a_status_per_field():
    row = report_rows([REF], [RESULT])[0]
    assert row["tier"] == "⚠️  Exists, citation errors"
    assert row["sources"] == "DOI: not given | URL: not given | title: confirmed"
    assert (row["check_title"], row["check_volume"], row["check_pages"]) == ("ok", "major", "ok")
    assert (row["cited_volume"], row["found_volume"]) == ("7", "9")
    assert row["found_doi"] == "10.1/x" and row["check_doi"] == "no data"
    assert row["issues"] == "volume: 7 vs 9 [major]"
    assert row["sim_title"] == 1.0 and row["year_gap"] == 0


def test_to_frame_and_summary():
    doc = DocumentReport("essay.pdf", "layout+grobid", [REF], [RESULT])
    table = to_frame([doc])
    assert list(table[["file", "n"]].iloc[0]) == ["essay.pdf", 1]
    assert summary([doc]).split() == ["essay.pdf", "1", "refs", "✅0", "⚠️1", "🚩0", "❓0", "🤖0"]
