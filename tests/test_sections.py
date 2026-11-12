from leanweb.clean import clean_html
from leanweb.sections import clamp, cut, match, parse_sections


def labels(md):
    return [s.label for s in parse_sections(md)]


def test_outline_and_labels(article_html):
    md, *_ = clean_html(article_html)
    assert labels(md) == [
        "Widget Plugins Guide",
        "How to install widgets",
        "Best widget plugins",
        "1. Alpha",
        "1. Alpha > What it does",
        "1. Alpha > Install",
        "2. Beta",
        "2. Beta > What it does",
        "2. Beta > Install",
        "Comparison",
        "Wrap up",
    ]


def test_section_ranges(article_html):
    md, *_ = clean_html(article_html)
    secs = parse_sections(md)
    best = secs[2]
    assert best.title == "Best widget plugins"
    body = md[best.start:best.end]
    assert "Beta stops an agent" in body and "Comparison" not in body  # includes subsections only
    assert md[best.start:best.own_end].strip() == "## Best widget plugins"


def test_headings_inside_code_are_ignored():
    md = "# Real\n\n```\n# not a heading\n```\n\n## Also real\n"
    assert labels(md) == ["Real", "Also real"]


def test_parent_label_when_unique():
    md = "# Linux\n## History\n### Development\n## Design\n## Development\n"
    assert labels(md) == ["Linux", "History", "History > Development", "Design", "Linux > Development"]


def test_numbered_label_when_still_ambiguous():
    md = "## Wrap Up\n## More\n## More\n"
    assert labels(md) == ["Wrap Up", "Wrap Up > More", "Wrap Up > More [2]"]


def test_match_rules(article_html):
    md, *_ = clean_html(article_html)
    secs = parse_sections(md)

    def first(q):
        found = match(secs, q)
        return secs[found[0]].label if found else None

    assert first("install") == "1. Alpha > Install"  # exact title beats "How to install widgets"
    assert len(match(secs, "install")) == 3
    assert first("Beta > Install") == "2. Beta > Install"  # path lookup via anchor
    assert first("2. Beta > Install") == "2. Beta > Install"  # exact label
    assert first("## comparison") == "Comparison"  # case and leading #'s ignored
    assert first("2 beta") == "2. Beta"  # punctuation-insensitive
    assert first("pricing") is None


def test_cut_and_clamp():
    text = "line one\nline two\nline three"
    assert cut(text, 100) == text
    assert cut(text, 20) == "line one\nline two"
    assert clamp(10) == 200 and clamp(10**9) == 16000
