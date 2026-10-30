from falseref.matching.compare import author_issues, compare, locator_issues, title_issues
from falseref.matching.similarity import NAME_SIM, name_sim, venue_sim
from falseref.models import Reference


def record(**kw):
    rec = {"title": ["Deep learning for credit risk"], "author": [{"given": "Anna", "family": "Kumar"}],
           "issued": {"date-parts": [[2020]]}, "container-title": ["Expert Systems with Applications"]}
    rec.update(kw)
    return rec


def test_name_sim_thresholds_from_docstring():
    assert name_sim("Hassan", "Hasan") >= NAME_SIM
    assert name_sim("Muller", "Mueller") >= NAME_SIM
    assert name_sim("Zhang", "Zhong") < NAME_SIM
    assert name_sim("Müller", "Muller") == 1.0


def test_venue_sim_accepts_abbreviations_and_acronyms():
    assert venue_sim("IEEE Trans. Pattern Anal. Mach. Intell.",
                     "IEEE Transactions on Pattern Analysis and Machine Intelligence") == 1.0
    assert venue_sim("JAMA", "Journal of the American Medical Association") == 1.0
    assert venue_sim("Nature", "Science") < 0.8


def test_title_issues_grades_differences():
    found = "Deep learning for credit risk assessment"
    assert title_issues(found, found) == []
    assert title_issues("Deep learning for credit risk", found)[0][0] == "minor"  # truncated
    assert title_issues("Deep leanring for credit risk assessment", found)[0][0] == "minor"  # typo
    assert title_issues("Shallow learning for credit risk assessment", found)[0][0] == "major"  # changed word
    assert title_issues("Something else entirely", found)[0][0] == "major"


def test_author_issues():
    rec = {"author": [{"given": "Anna", "family": "Kumar"}, {"given": "Vadlamani", "family": "Ravi"}]}
    assert author_issues(["A. Kumar", "V. Ravi"], rec) == []
    assert author_issues(["A. Kumar", "V. Rao"], rec)[0] == ("major", "author not in record: V. Rao")
    assert ("minor", "authors missing from reference: Vadlamani Ravi") in author_issues(["A. Kumar"], rec)
    assert author_issues(["B. Kumar", "V. Ravi"], rec)[0][1].startswith("author initials")
    assert any(m.startswith("author order") for _, m in author_issues(["V. Ravi", "A. Kumar"], rec))


def test_author_issues_when_no_cited_author_is_in_the_record():
    rec = {"author": [{"given": "Ayşegül", "family": "Uçar"}, {"given": "Mehmet", "family": "Karaköse"}]}
    assert author_issues(["MDPI"], rec) == [
        ("major", "author mismatch: got 'MDPI', expected 'Ayşegül Uçar; Mehmet Karaköse'")]


def test_locator_issues():
    ref = Reference(raw="", volume="7", pages="1015")
    assert locator_issues(ref, record(volume="7", page="1015-1015")) == []  # IEEE single page
    assert locator_issues(ref, record(volume="8", page="1015")) == [("major", "volume: 7 vs 8")]


def test_compare_year_gap_and_checked_fields():
    ref = Reference(raw="", authors=["A. Kumar"], title="Deep learning for credit risk", year="2021",
                    venue="Expert Systems with Applications")
    issues, checked = compare(ref, record())
    assert [(i.field, i.severity) for i in issues] == [("year", "minor")]
    assert checked == {"title", "year", "authors", "venue"}
    ref.year = "2017"
    assert compare(ref, record())[0][0].severity == "major"
