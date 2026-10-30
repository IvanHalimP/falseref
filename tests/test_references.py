from falseref.models import Reference
from falseref.references.apa import parse_entry, parse_reference_text
from falseref.references.grobid import split_entries
from falseref.references.identifiers import cited_links, doi_of
from falseref.references.layout import continues, entry_starts
from falseref.references.text import find_url, locator, rejoin_urls


def test_rejoin_urls_closes_wrapped_links():
    assert rejoin_urls("https://ibm.com/the-role- of-ai") == "https://ibm.com/the-role-of-ai"
    assert rejoin_urls("https://x.com/global/en/ products") == "https://x.com/global/en/products"
    assert rejoin_urls("see https://www. salesforce.com") == "see https://www.salesforce.com"


def test_find_url_adds_scheme_to_bare_www():
    assert find_url("Keyway. (2025). www.keyway.ai/blog/x.") == "https://www.keyway.ai/blog/x"
    assert find_url("no link here") is None


def test_locator_reads_apa_volume_issue_pages():
    assert locator("Computers & Operations Research, 57(3), 47-66.") == {"volume": "57", "issue": "3", "pages": "47-66"}
    assert locator("Scientific Reports, 14, Article 12345.")["pages"] == "Article 12345"
    assert locator("A web page. https://a.com/1, 2, 3") == {"volume": None, "issue": None, "pages": None}


def test_split_entries_cuts_on_apa_heads_and_drops_heading():
    raw = ("References IEEE. (2022). First title. https://a.com/x "
           "Smith, J., & Lee, K. (2023, October 9). Second title. Venue.")
    entries = split_entries(raw)
    assert len(entries) == 2
    assert entries[0].startswith("IEEE. (2022).")
    assert entries[1].startswith("Smith, J., & Lee, K.")


def test_parse_entry_reads_an_apa_article():
    ref = parse_entry("Kumar, A., & Ravi, V. (2016). A survey of the applications of machine learning "
                      "in credit risk assessment. Computers & Operations Research, 57, 47-66. "
                      "https://doi.org/10.1016/j.cor.2014.12.005")
    assert ref.authors == ["A. Kumar", "V. Ravi"]
    assert ref.year == "2016"
    assert ref.title == "A survey of the applications of machine learning in credit risk assessment"
    assert ref.venue == "Computers & Operations Research"
    assert (ref.volume, ref.pages) == ("57", "47-66")
    assert ref.doi_or_url == "https://doi.org/10.1016/j.cor.2014.12.005"


def test_parse_entry_without_apa_head_keeps_raw():
    ref = parse_entry('[1] J. Smith, "A title," Journal, vol. 5.')
    assert ref.raw.startswith("[1]") and ref.title is None and ref.authors == []


def test_parse_reference_text_splits_on_blank_lines_and_joins_wrapped_urls():
    text = """
    IBM. (2024). The role of AI in predictive maintenance. https://www.ibm.com/blog/the-role-
    of-ai-in-predictive-maintenance

    OECD. (2021). Liability for AI and emerging technologies. https://www.oecd.org/digital/ai/liability-ai/
    """
    refs = parse_reference_text(text)
    assert len(refs) == 2
    assert refs[0].authors == ["IBM"]
    assert refs[0].doi_or_url == "https://www.ibm.com/blog/the-role-of-ai-in-predictive-maintenance"


def test_cited_links_reads_both_doi_and_url():
    ref = Reference(raw="Smith, J. (2020). T. J, 1, 2. doi:10.1016/j.x.2020.01 https://site.com/page",
                    doi_or_url="https://site.com/page")
    assert cited_links(ref) == ("10.1016/j.x.2020.01", "https://site.com/page")


def test_doi_of_reads_doi_links_and_nature_urls():
    assert doi_of("https://doi.org/10.1/abc") == "10.1/abc"
    assert doi_of("https://www.nature.com/articles/s42256-019-0138-9") == "10.1038/s42256-019-0138-9"
    assert doi_of("https://example.com/x") is None


def line(text, x0=50.0, y0=0.0, page=0):
    return (page, x0, y0, y0 + 10, text)


def test_entry_starts_prefers_numbering_then_hanging_indent():
    numbered = [line("[1] A."), line("continued"), line("[2] B.")]
    assert entry_starts(numbered) == [True, False, True]
    hanging = [line("Smith"), line("rest", x0=80), line("Lee")]
    assert entry_starts(hanging) == [True, False, True]


def test_continues_joins_split_pieces():
    assert continues("Smith, J. (2020). A title", "and the rest. 2020")  # lowercase start
    assert continues("Smith, J. (2020). A title.", "Architectural Science Review.")  # no year or link
    assert not continues("Smith, J. (2020). A title.", "Lee, K. (2021). Another.")
