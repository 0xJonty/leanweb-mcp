from leanweb.clean import clean_html, clean_markdown, one_line


def test_article_is_cleaned(article_html):
    md, images, title, cleaned_html = clean_html(article_html)
    assert title == "Widget Plugins Guide | Example Site"
    assert md.startswith("# Widget Plugins Guide")
    # boilerplate: scripts, nav, site header (no heading), footer, announcement outside <main>
    for junk in ("tracking", "analytics", "Docs nav link", "Products menu item", "Footer copyright",
                 "Announcement banner", "font-family"):
        assert junk not in md, junk
    # hidden content never reaches the model
    for hidden in ("ignore all previous instructions", "Hidden promotional text", "decorative glyph"):
        assert hidden not in md, hidden
        assert hidden not in cleaned_html, hidden
    # links become their text; images are removed and counted (the logo went with the site header)
    assert "official widget docs" in md and "example.org" not in md
    assert "](" not in md and "diagram.png" not in md
    assert images == 1
    # permalink glyph dropped, article header (has the h1) kept
    assert "¶" not in md
    assert "By A. Writer" in md


def test_code_is_preserved(article_html):
    md, *_ = clean_html(article_html)
    assert "# this line is a shell comment, not a heading" in md
    assert "`<config>`" in md  # inline code is not treated as a stray tag


def test_tables_survive(article_html):
    md, *_ = clean_html(article_html)
    assert "| Alpha | 1200 |" in md


def test_clean_markdown_rules():
    md, images = clean_markdown(
        "Intro ![logo](/a.png) [link text](https://x.test/a_(b)) <span>tag</span>\n\n\n\n"
        "-\n"
        "```\n<div>kept in code</div>\n[x](y)\n```\n"
        "word​  with   spaces\xa0here"
    )
    assert images == 1
    assert "Intro link text tag" in md
    assert "<div>kept in code</div>\n[x](y)" in md
    assert "\n\n\n" not in md
    assert "\n-\n" not in md
    assert "word with spaces here" in md


def test_one_line():
    assert one_line("a\n b  <b>c</b>", 50) == "a b c"
    s = one_line("word " * 100, 40)
    assert len(s) <= 43 and s.endswith("...")


def test_mediawiki_chrome_removed():
    html = ('<main><h2>History<span class="mw-editsection">[<a href="/edit">edit</a>]</span></h2>'
            '<p>The first robot,<sup class="reference"><a href="#c2">[2]</a></sup> Wanderer, was created. '
            + "More text. " * 60 + "</p></main>")
    md, *_ = clean_html(html)
    assert "## History\n" in md and "[edit]" not in md and "[2]" not in md and "robot, Wanderer" in md
