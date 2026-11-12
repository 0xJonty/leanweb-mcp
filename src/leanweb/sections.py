"""Heading outline of cleaned markdown, unique section labels, heading lookup and output trimming."""

import re
from dataclasses import dataclass

from . import config
from .clean import FENCE

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")


@dataclass
class Sec:
    level: int
    title: str
    start: int  # char offset of the heading line
    own_end: int = 0  # next heading of any level
    end: int = 0  # next heading of the same or higher level
    parent: int = -1
    anchor: int = -1
    label: str = ""  # unique: title, or "Parent > title" (+ " [n]") when the title repeats


def clean_title(t: str) -> str:
    t = re.sub(r"\\([\\`*_{}\[\]()#+\-.!])", r"\1", t)
    t = re.sub(r"\*\*|__|`", "", t)
    return " ".join(t.strip(" *_").split())


def norm(s: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", s.casefold()).split())


def parse_sections(md: str) -> list[Sec]:
    secs: list[Sec] = []
    offset = 0
    in_fence = False
    for line in md.splitlines(keepends=True):
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            m = _HEADING.match(line.rstrip("\n"))
            if m:
                title = clean_title(m.group(2))
                if title:
                    secs.append(Sec(len(m.group(1)), title, offset))
        offset += len(line)
    n = len(md)
    for i, s in enumerate(secs):
        s.own_end = secs[i + 1].start if i + 1 < len(secs) else n
        s.end = next((t.start for t in secs[i + 1:] if t.level <= s.level), n)
        s.parent = next((j for j in range(i - 1, -1, -1) if secs[j].level < s.level), -1)
    _label(secs)
    return secs


def _label(secs: list[Sec]) -> None:
    """Give every section a unique label usable as page_section's `heading`.

    A repeated title is prefixed with its parent when that is enough ("History > Development").
    Otherwise it uses the nearest earlier heading of the same or higher level with a unique title,
    because pages often put "What it does" / "Install" at the same level as the item they belong
    to ("3. Context7 > Install"). Anything still ambiguous gets " [2]", " [3]", ...
    """
    counts: dict[str, int] = {}
    for s in secs:
        counts[norm(s.title)] = counts.get(norm(s.title), 0) + 1
    by_parent: dict[str, int] = {}
    for s in secs:
        if s.parent >= 0:
            k = norm(secs[s.parent].title) + ">" + norm(s.title)
            by_parent[k] = by_parent.get(k, 0) + 1
    seen: dict[str, int] = {}
    for i, s in enumerate(secs):
        s.label = s.title
        if counts[norm(s.title)] > 1:
            s.anchor = next((j for j in range(i - 1, -1, -1)
                             if secs[j].level <= s.level and counts[norm(secs[j].title)] == 1), -1)
            if s.parent >= 0 and by_parent[norm(secs[s.parent].title) + ">" + norm(s.title)] == 1:
                s.label = f"{secs[s.parent].title} > {s.title}"
            elif s.anchor >= 0:
                s.label = f"{secs[s.anchor].title} > {s.title}"
        k = norm(s.label)
        seen[k] = seen.get(k, 0) + 1
        if seen[k] > 1:
            s.label += f" [{seen[k]}]"


def _context(secs: list[Sec], i: int) -> set[int]:
    """Indices that count as a 'parent' of section i for 'Parent > Child' lookups."""
    out: set[int] = set()
    todo = [secs[i].parent, secs[i].anchor]
    while todo:
        j = todo.pop()
        if j >= 0 and j not in out:
            out.add(j)
            todo += [secs[j].parent, secs[j].anchor]
    return out


def match(secs: list[Sec], query: str) -> list[int]:
    """Indices of sections matching `query`, best first.

    Order: exact label, then exact title, then titles containing the query (case/punctuation-insensitive).
    "Parent > Child" narrows to children of matching parents."""
    q = query.strip().lstrip("#").strip()
    exact_label = [i for i, s in enumerate(secs) if norm(s.label) == norm(q)]
    if exact_label:
        return exact_label[:1]
    parts = [p for p in (norm(x) for x in q.split(">")) if p]
    if not parts:
        return []
    everything = list(range(len(secs)))

    def find_in(cands: list[int], needle: str) -> list[int]:
        exact = [i for i in cands if norm(secs[i].title) == needle]
        contains = [i for i in cands if needle in norm(secs[i].title) and i not in exact]
        return exact + contains

    found = find_in(everything, parts[0])
    for part in parts[1:]:
        prev = set(found)
        found = [j for j in find_in(everything, part) if _context(secs, j) & prev]
    if not found and len(parts) > 1:  # the heading itself may contain '>'
        found = find_in(everything, norm(q))
    return found


# --- output helpers
def tok(n_chars: int) -> int:
    """Rough token estimate (chars / 4)."""
    return round(n_chars / 4)


def cut(text: str, limit: int) -> str:
    """Cut text to at most `limit` chars, preferring a line or word boundary."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    for sep in ("\n", " "):
        i = head.rfind(sep)
        if i >= limit * 0.8:
            return head[:i].rstrip()
    return head


def cap(text: str, limit: int, note: str = "\n[output truncated]") -> str:
    if len(text) <= limit:
        return text
    return cut(text, limit - len(note)) + note


def clamp(max_chars: int) -> int:
    return max(200, min(int(max_chars), config.READ_CEILING))
