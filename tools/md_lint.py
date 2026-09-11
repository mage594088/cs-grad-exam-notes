"""Custom CJK-width-aware Markdown checker.

Standard tools (markdownlint / remark-lint / textlint) do not handle
CJK display width together with orphan-word line wrapping, so this
project keeps a small standalone checker instead.

Checks performed on every ``*.md`` file:

1. Line width: CJK characters count as width 2 (via
   ``unicodedata.east_asian_width``), everything else as width 1.
   A line whose total display width exceeds ``MAX_WIDTH`` is flagged
   -- except a line that is *only* a bare URL or filesystem path,
   since those cannot be wrapped without breaking the link/path.
2. Orphan words: within a prose paragraph, wrapping the paragraph at
   ``MAX_WIDTH`` must not leave a wrapped line containing a single
   bare ASCII word with no CJK characters around it. A markdown link
   ``[text](url)`` counts as one atomic token for this purpose.
3. Ordered list sequencing: numbered list items (``1.``, ``2.``, ...)
   must run in order with no gaps, tracked independently per
   indentation level so nested lists are checked on their own.
4. Tight wrapping: a prose paragraph's hard-wrapped lines must match
   what a fresh greedy wrap of the same text would produce. Since
   ``tokenize()`` treats a real newline the same as a space, this
   catches a line that breaks well short of the width limit even
   though the next line's first word would still have fit.
5. Stray spacing: a literal space typed directly between two CJK
   characters on the same line is always a typo in this project's
   house style (see ``needs_space``) -- the width and tight-wrap
   checks don't catch this since they only reason about where a line
   *breaks*, not what whitespace already sits inside it.

Headings, table rows and list markers are excluded from the
orphan-word/tight-wrap paragraph checks (they are not wrappable
prose), but still go through the line-width check. Blockquotes *are*
wrappable prose in Markdown -- a blockquote's ``>`` marker is stripped
before these paragraph checks run, and its display width is accounted
for separately so the width-based checks still reflect what the
rendered line actually needs.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MAX_WIDTH = 80

URL_OR_PATH_RE = re.compile(r"^(https?://\S+|[A-Za-z]:\\\S*|/\S*)$")
LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
LINK_ONLY_RE = re.compile(r"^\[[^\]]*\]\([^)]*\)$")
ORDERED_ITEM_RE = re.compile(r"^(\s*)(\d+)\.\s+")
NON_PROSE_RE = re.compile(r"^\s*(#|\||[-*]\s|\d+\.\s)")
FENCE_RE = re.compile(r"^\s*```")
BLOCKQUOTE_PREFIX_RE = re.compile(r"^\s*>\s?")


def display_width(text: str) -> int:
    """Return the terminal display width of ``text``."""
    width = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        width += 2 if eaw in ("W", "F") else 1
    return width


def is_url_or_path_line(line: str) -> bool:
    """Is this line just one bare URL/path, or one markdown link?

    Either form is a single unbreakable token once a blockquote's
    leading ``> `` is stripped, so it is exempt from the width limit
    the same way a bare URL line already is.
    """
    stripped = line.strip()
    if URL_OR_PATH_RE.match(stripped):
        return True
    unquoted = BLOCKQUOTE_PREFIX_RE.sub("", line, count=1).strip()
    return bool(LINK_ONLY_RE.match(unquoted))


def _fence_mask(lines: list[str]) -> list[bool]:
    """Return a per-line mask that is True inside fenced code blocks."""
    mask = []
    in_fence = False
    for line in lines:
        if FENCE_RE.match(line):
            mask.append(True)
            in_fence = not in_fence
            continue
        mask.append(in_fence)
    return mask


@dataclass
class Issue:
    line_no: int
    message: str


def check_line_width(lines: list[str]) -> list[Issue]:
    issues = []
    fence = _fence_mask(lines)
    for i, line in enumerate(lines):
        if fence[i] or is_url_or_path_line(line):
            continue
        if display_width(line) > MAX_WIDTH:
            issues.append(Issue(i + 1, f"line exceeds {MAX_WIDTH} width"))
    return issues


def tokenize(text: str) -> list[str]:
    """Split text into CJK chars and whitespace-delimited words.

    A markdown link ``[text](url)`` is kept as one atomic token so it
    is never broken across a wrap point.
    """
    tokens: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        m = LINK_RE.match(text, i)
        if m:
            tokens.append(m.group(0))
            i = m.end()
            continue
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            tokens.append(ch)
            i += 1
            continue
        j = i
        while (
            j < n
            and not text[j].isspace()
            and not LINK_RE.match(text, j)
            and unicodedata.east_asian_width(text[j]) not in ("W", "F")
        ):
            j += 1
        tokens.append(text[i:j])
        i = j
    return tokens


PUNCT_NO_SPACE = set("。,.:;!?、()()「」『』-…《》【】*/~")


def is_cjk_char(token: str) -> bool:
    return len(token) == 1 and unicodedata.east_asian_width(token) in ("W", "F")


def needs_space(a: str, b: str) -> bool:
    """Would a real space belong between adjacent tokens ``a`` and ``b``?

    Matches this project's house style: an English word or markdown
    link token always has a real space around it when next to CJK
    text (e.g. "在 PTT 上"), but CJK-to-CJK is space-free, and a
    punctuation mark never gets a surrounding space either way -- even
    when it is fused onto a bigger token, e.g. the "(" starting
    "(2019" or the "," ending "star,", so only the outermost character
    of each token needs checking against ``PUNCT_NO_SPACE``.
    """
    if a and a[-1] in PUNCT_NO_SPACE:
        return False
    if b and b[0] in PUNCT_NO_SPACE:
        return False
    return not (is_cjk_char(a) and is_cjk_char(b))


def wrap_tokens(tokens: list[str], width: int = MAX_WIDTH) -> list[list[str]]:
    """Greedily pack tokens into lines no wider than ``width``.

    Accounts for the real space a token needs from its predecessor
    (see ``needs_space``) so the packing decision matches the same
    raw display width ``check_line_width`` enforces -- otherwise a
    line full of English words/links could be packed "optimally" by
    token width alone yet still overflow once real spaces are added.
    """
    lines: list[list[str]] = [[]]
    cur_width = 0
    for tok in tokens:
        tok_width = display_width(tok)
        gap = 1 if lines[-1] and needs_space(lines[-1][-1], tok) else 0
        if cur_width + gap + tok_width > width and lines[-1]:
            lines.append([])
            cur_width = 0
            gap = 0
        lines[-1].append(tok)
        cur_width += gap + tok_width
    return lines


def is_ascii_word(token: str) -> bool:
    return bool(token) and all(ord(c) < 128 for c in token)


def check_orphan_words(paragraph: str, width: int = MAX_WIDTH) -> list[str]:
    """Flag a paragraph whose *last* wrapped line is a lone ASCII word.

    Only the final wrapped line matters: a lone word part-way through
    a paragraph is normal (the next word simply didn't fit), but a
    lone word stranded on the last line, with no CJK characters
    around it, reads as an orphan.
    """
    tokens = tokenize(paragraph)
    wrapped = wrap_tokens(tokens, width=width)
    if len(wrapped) <= 1:
        return []
    last_line = wrapped[-1]
    if len(last_line) == 1 and is_ascii_word(last_line[0]):
        return [f"last wrapped line is an orphan word: {last_line[0]!r}"]
    return []


def group_prose_paragraphs(
    lines: list[str],
) -> list[tuple[int, list[str], int]]:
    """Group contiguous prose lines into paragraphs.

    Headings, table rows, list items and fenced code are treated as
    paragraph breaks and excluded entirely. A blockquote's leading
    ``> `` marker is stripped from each of its lines before grouping
    -- a blockquote is wrappable prose like any other paragraph, it
    just renders with that marker prepended.

    Returns each paragraph as (0-based start line number, list of
    stripped line texts, prefix display width) so callers that need
    per-line positions (not just the joined text) have them, and
    width-based checks can account for the marker that will prepend
    every rendered line of a blockquote paragraph.
    """
    fence = _fence_mask(lines)
    paragraphs: list[tuple[int, list[str], int]] = []
    current: list[str] = []
    start = 0
    prefix_width = 0
    for i, line in enumerate(lines):
        bq_match = BLOCKQUOTE_PREFIX_RE.match(line)
        content = line[bq_match.end():] if bq_match else line
        skip = (
            fence[i]
            or not line.strip()
            or (not bq_match and NON_PROSE_RE.match(line))
        )
        if skip:
            if current:
                paragraphs.append((start, current, prefix_width))
                current = []
            continue
        if not current:
            start = i
            prefix_width = display_width(bq_match.group(0)) if bq_match else 0
        current.append(content)
    if current:
        paragraphs.append((start, current, prefix_width))
    return paragraphs


def check_tight_wrap(lines: list[str]) -> list[Issue]:
    """Flag a paragraph that is hard-wrapped looser than it needs to be.

    ``tokenize()`` treats a real newline the same as a space, so
    re-wrapping a paragraph's full text with ``wrap_tokens()`` gives
    the canonical, tightest possible set of line breaks. If the
    paragraph's actual line breaks land at different token boundaries
    than that canonical wrap, at least one line broke before it had
    to -- e.g. because the next line's first word would still have
    fit within the width limit.
    """
    issues: list[Issue] = []
    for start, para_lines, prefix_width in group_prose_paragraphs(lines):
        if len(para_lines) <= 1:
            continue
        per_line_tokens = [tokenize(pl) for pl in para_lines]
        all_tokens = [tok for toks in per_line_tokens for tok in toks]

        actual_breaks: list[int] = []
        acc = 0
        for toks in per_line_tokens[:-1]:
            acc += len(toks)
            actual_breaks.append(acc)

        optimal_lines = wrap_tokens(all_tokens, width=MAX_WIDTH - prefix_width)
        optimal_breaks: list[int] = []
        acc = 0
        for toks in optimal_lines[:-1]:
            acc += len(toks)
            optimal_breaks.append(acc)

        if actual_breaks != optimal_breaks:
            issues.append(Issue(
                start + 1,
                "paragraph is wrapped looser than necessary; re-flow "
                "it to pack lines to the width limit",
            ))
    return issues


def check_spacing(lines: list[str]) -> list[Issue]:
    """Flag a literal space typed directly between two CJK characters.

    Two adjacent CJK characters never take a space between them in
    this project's house style (``needs_space`` always says False for
    a CJK/CJK pair), so a real space sitting between them in the
    source -- typically left behind by a manual edit or a rewrap done
    by hand -- is always a typo. This only needs to look at literal
    whitespace runs directly in the raw line; unlike the width and
    tight-wrap checks it has nothing to do with where a line breaks.
    """
    issues: list[Issue] = []
    fence = _fence_mask(lines)
    for i, line in enumerate(lines):
        if fence[i]:
            continue
        for m in re.finditer(r"[ \t]+", line):
            before, after = line[:m.start()], line[m.end():]
            both_cjk = (
                before and after
                and is_cjk_char(before[-1]) and is_cjk_char(after[0])
            )
            if both_cjk:
                issues.append(Issue(
                    i + 1,
                    f"unexpected space between {before[-1]!r} and "
                    f"{after[0]!r} -- CJK characters take no space "
                    "between them",
                ))
    return issues


def check_ordered_lists(lines: list[str]) -> list[Issue]:
    """Verify numbered list items run 1, 2, 3, ... per indent level.

    Each indentation level is tracked independently (a stack keyed by
    indent width) so nested lists get their own 1, 2, 3, ... sequence.
    """
    issues: list[Issue] = []
    fence = _fence_mask(lines)
    stack: list[tuple[int, int]] = []  # (indent, expected_next)
    for i, raw in enumerate(lines):
        if fence[i]:
            continue
        if not raw.strip():
            stack = []
            continue
        m = ORDERED_ITEM_RE.match(raw)
        if not m:
            continue
        indent = len(m.group(1))
        num = int(m.group(2))
        stack = [frame for frame in stack if frame[0] <= indent]
        if stack and stack[-1][0] == indent:
            expected = stack[-1][1]
            if num != expected:
                issues.append(Issue(
                    i + 1,
                    f"expected {expected} but got {num} "
                    "(same-level ordered list sequence broken)",
                ))
            stack[-1] = (indent, num + 1)
        else:
            if num != 1:
                issues.append(Issue(
                    i + 1, f"ordered list should start at 1, got {num}"
                ))
            stack.append((indent, num + 1))
    return issues


def lint_text(text: str, label: str = "<text>") -> list[str]:
    lines = text.splitlines()
    messages = [
        f"{label}:{issue.line_no}: {issue.message}"
        for issue in check_line_width(lines)
    ]
    messages += [
        f"{label}:{issue.line_no}: {issue.message}"
        for issue in check_ordered_lists(lines)
    ]
    messages += [
        f"{label}:{issue.line_no}: {issue.message}"
        for issue in check_tight_wrap(lines)
    ]
    messages += [
        f"{label}:{issue.line_no}: {issue.message}"
        for issue in check_spacing(lines)
    ]
    for _, para_lines, prefix_width in group_prose_paragraphs(lines):
        if len(para_lines) <= 1:
            continue
        para = "\n".join(para_lines)
        width = MAX_WIDTH - prefix_width
        messages += [
            f"{label}: {msg}" for msg in check_orphan_words(para, width=width)
        ]
    return messages


def lint_file(path: Path) -> list[str]:
    return lint_text(path.read_text(encoding="utf-8"), label=str(path))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    paths = [Path(p) for p in argv] if argv else sorted(Path(".").rglob("*.md"))
    messages: list[str] = []
    skip_dirs = {"venv", ".git", ".pytest_cache", "__pycache__"}
    for path in paths:
        if skip_dirs & set(path.parts):
            continue
        messages.extend(lint_file(path))
    for msg in messages:
        print(msg)
    return 1 if messages else 0


if __name__ == "__main__":
    raise SystemExit(main())
