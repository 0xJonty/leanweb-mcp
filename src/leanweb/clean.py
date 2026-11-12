"""HTML -> compact markdown: drop boilerplate and hidden content, strip images/links/tags, collapse blanks."""

import re

from lxml import etree
from lxml import html as lxml_html
from markdownify import markdownify

from . import config

NOISE_TAGS = (
    "script", "style", "noscript", "svg", "iframe", "template", "nav", "footer", "button",
    "select", "textarea", "input", "canvas", "object", "embed", "dialog", "link", "meta", "head",
)
# Hidden content is invisible to people but often carries junk or text aimed at AI agents.
HIDDEN_XPATH = (
    "//*[@hidden] | //*[@aria-hidden='true'] "
    "| //*[contains(translate(@style,' ',''),'display:none')] "
    "| //*[contains(translate(@style,' ',''),'visibility:hidden')]"
)
ROLE_XPATH = "//*[@role='navigation' or @role='contentinfo' or @role='dialog']"
# heading permalink glyphs (Sphinx/MkDocs "¶", GitHub-style "#")
PERMALINK_XPATH = ("//a[normalize-space(.)='¶' or normalize-space(.)='§' or normalize-space(.)='#' "
                   "or normalize-space(.)='🔗']")
# MediaWiki chrome: "[edit]" links and "[12]" citation markers (Wikipedia is read a lot)
MEDIAWIKI_XPATH = ("//span[contains(concat(' ',normalize-space(@class),' '),' mw-editsection ')] "
                   "| //sup[contains(concat(' ',normalize-space(@class),' '),' reference ')]")
KEEP_ALWAYS = {"html", "body", "main", "article"}

FENCE = re.compile(r"^\s*(```+|~~~+)")
_IMG_MD = re.compile(r"!\[[^\]]*\]\((?:[^()]|\([^()]*\))*\)")
_LINK_MD = re.compile(r"\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)")
HTML_TAG = re.compile(r"<!--.*?-->|</?[a-zA-Z][a-zA-Z0-9:-]*(?:\s[^<>]*)?/?>")
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_ZERO_WIDTH = re.compile(r"[​-‏⁠﻿­]")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def text_len(el) -> int:
    return len(" ".join(el.text_content().split()))


def to_md(fragment: str) -> str:
    return markdownify(
        fragment,
        heading_style="ATX",
        bullets="-",
        strip=["a", "img"],
        escape_underscores=False,
        escape_asterisks=False,
    )


def _drop(elements) -> None:
    for el in elements:
        if el.getparent() is not None and el.tag not in KEEP_ALWAYS:
            el.drop_tree()


def clean_html(html: str) -> tuple[str, int, str, str]:
    """Returns (markdown, images_removed, title, cleaned_body_html)."""
    html = html[: config.MAX_HTML_CHARS]
    doc = lxml_html.document_fromstring(
        html.encode("utf-8", "replace"), parser=lxml_html.HTMLParser(encoding="utf-8")
    )
    title = " ".join((doc.findtext(".//title") or "").split())

    etree.strip_elements(doc, etree.Comment, with_tail=False)
    _drop(doc.xpath(HIDDEN_XPATH) + doc.xpath("//" + " | //".join(NOISE_TAGS))
          + doc.xpath(ROLE_XPATH) + doc.xpath(PERMALINK_XPATH) + doc.xpath(MEDIAWIKI_XPATH))
    # site headers/banners (menus, logos) have no h1-h3; article headers do, so keep those
    _drop([el for el in doc.xpath("//header | //*[@role='banner']") if not el.xpath(".//h1|.//h2|.//h3")])

    body = doc.find("body")
    root = body if body is not None else doc
    cleaned_html = etree.tostring(root, encoding="unicode", method="html")  # used by page_select
    body_len = max(text_len(root), 1)
    # a single <main> (or <article>) holding most of the text is the content; skip what's around it
    for cands in (doc.xpath("//main | //*[@role='main']"), doc.xpath("//article")):
        if len(cands) == 1:
            n = text_len(cands[0])
            if n >= 500 and n >= 0.35 * body_len:
                root = cands[0]
                break

    images = len(root.xpath(".//img"))
    md, extra_images = clean_markdown(to_md(etree.tostring(root, encoding="unicode", method="html")))
    return md, images + extra_images, title, cleaned_html


def _clean_line(line: str) -> tuple[str, int]:
    """Clean one markdown line outside code fences. Returns (line, images_removed)."""
    spans: list[str] = []

    def stash(m):  # protect inline code from tag/link stripping
        spans.append(m.group(0))
        return f"\x00{len(spans) - 1}\x00"

    line = _CODE_SPAN.sub(stash, line)
    line, n_img = _IMG_MD.subn("", line)
    line = _LINK_MD.sub(r"\1", line)
    line = HTML_TAG.sub("", line)
    line = re.sub(r"(?<=\S)[ \t]{2,}", " ", line)
    line = re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], line)
    return line.rstrip(), n_img


def clean_markdown(md: str) -> tuple[str, int]:
    """Remove images, links and stray tags outside code fences; collapse blank lines.

    Returns (markdown, images_removed)."""
    md = _CTRL.sub("", _ZERO_WIDTH.sub("", md.replace("\xa0", " ").replace("\r\n", "\n")))
    out: list[str] = []
    images = 0
    in_fence = False
    for line in md.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
            out.append(line.strip())
            continue
        if in_fence:
            out.append(line.rstrip())
            continue
        line, n = _clean_line(line)
        images += n
        if re.fullmatch(r"\s*([-*+]|#{1,6}|\|)?\s*", line):  # empty bullet / heading / blank
            line = ""
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip(), images


def one_line(s: str, limit: int) -> str:
    """Collapse to a single line of at most `limit` chars, cut at a word boundary."""
    s = " ".join(HTML_TAG.sub("", s or "").split())
    if len(s) <= limit:
        return s
    cut = s[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.6 else cut).rstrip(" ,.;:") + "..."
