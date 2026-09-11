"""Unit tests for tools/md_lint.py."""
from tools.md_lint import (
    check_line_width,
    check_ordered_lists,
    check_orphan_words,
    check_spacing,
    check_tight_wrap,
    display_width,
    group_prose_paragraphs,
    needs_space,
    tokenize,
    wrap_tokens,
)


# --- display width -----------------------------------------------------

def test_display_width_ascii():
    assert display_width("hello") == 5


def test_display_width_cjk_is_double():
    assert display_width("你好") == 4


# --- line width / URL & path exemption ----------------------------------

def test_long_line_is_flagged():
    line = "a" * 81
    issues = check_line_width([line])
    assert len(issues) == 1
    assert issues[0].line_no == 1


def test_bare_long_url_is_exempt():
    line = "https://example.com/" + "a" * 80
    assert check_line_width([line]) == []


def test_bare_long_windows_path_is_exempt():
    line = "C:\\" + "a" * 80
    assert check_line_width([line]) == []


def test_bare_long_unix_path_is_exempt():
    line = "/" + "a" * 80
    assert check_line_width([line]) == []


def test_lone_long_markdown_link_line_is_exempt():
    line = "[" + "a" * 40 + "](https://example.com/" + "b" * 40 + ")"
    assert check_line_width([line]) == []


def test_lone_long_markdown_link_in_blockquote_is_exempt():
    line = "> [" + "a" * 40 + "](https://example.com/" + "b" * 40 + ")"
    assert check_line_width([line]) == []


def test_link_plus_other_text_still_checked():
    line = "見 [" + "a" * 40 + "](https://example.com/" + "b" * 40 + ") 這裡"
    issues = check_line_width([line])
    assert len(issues) == 1


# --- orphan word check: pure ASCII paragraph ----------------------------

def test_ascii_paragraph_with_orphan_last_word():
    paragraph = "A" * 76 + " wordtwo"
    issues = check_orphan_words(paragraph)
    assert len(issues) == 1
    assert "wordtwo" in issues[0]


def test_ascii_paragraph_without_orphan():
    paragraph = "A" * 76 + " wordtwo three"
    assert check_orphan_words(paragraph) == []


# --- orphan word check: pure CJK paragraph ------------------------------

def test_pure_cjk_paragraph_never_orphan():
    paragraph = "測試" * 60
    assert check_orphan_words(paragraph) == []


# --- orphan word check: mixed CJK/ASCII ---------------------------------

def test_mixed_paragraph_with_cjk_padding_is_not_orphan():
    paragraph = "測" * 37 + " word"
    assert check_orphan_words(paragraph) == []


def test_mixed_paragraph_ascii_word_alone_is_orphan():
    paragraph = "A" * 76 + " lonely"
    issues = check_orphan_words(paragraph)
    assert len(issues) == 1
    assert "lonely" in issues[0]


# --- orphan word check: markdown link atom ------------------------------

def test_link_alone_on_wrapped_line_is_orphan():
    paragraph = "A" * 76 + " [link text](https://example.com/page)"
    issues = check_orphan_words(paragraph)
    assert len(issues) == 1


def test_link_not_alone_is_not_orphan():
    paragraph = "A" * 79 + " 測 [link text](https://example.com/page)"
    assert check_orphan_words(paragraph) == []


# --- wrap_tokens: packing must account for the real space an ascii ------
# --- word/link needs from its CJK neighbour ------------------------------

def test_wrap_tokens_reserves_space_before_ascii_word():
    # 38 CJK chars (width 76) + a real space + "word" (width 4) = 81,
    # one over the limit -- packing by token width alone (ignoring the
    # space) would wrongly fit it on one line.
    tokens = tokenize("測" * 38 + " word")
    wrapped = wrap_tokens(tokens)
    assert len(wrapped) == 2
    assert wrapped[1] == ["word"]


def test_wrap_tokens_no_space_around_punctuation():
    tokens = tokenize("測試。word")
    wrapped = wrap_tokens(tokens)
    assert wrapped == [["測", "試", "。", "word"]]


def test_needs_space_ignores_punctuation_fused_onto_a_token():
    # "(2019" is one token (paren + digits, no internal space), but it
    # still starts with an exempt "(" so no space belongs before it.
    assert needs_space("圖", "(2019") is False
    # "star," ends with an exempt "," so no space belongs after it.
    assert needs_space("star,", "對") is False
    # A plain CJK/ASCII-word boundary still needs its space.
    assert needs_space("在", "PTT") is True


def test_needs_space_around_em_dash():
    # "——" is East_Asian_Width "Ambiguous" (not W/F), so it is not a
    # single CJK char, and this house style always spaces it out like
    # a word ("一份 —— 這樣"), unlike closing punctuation.
    assert needs_space("份", "——") is True
    assert needs_space("——", "這樣") is True


def test_needs_space_before_markdown_link_from_cjk():
    # A link is a content word, not attaching punctuation -- it needs
    # a space from a plain CJK neighbour just like an English word
    # does, even though its token happens to start with "[".
    link = "[CONTRIBUTING.md](CONTRIBUTING.md)"
    assert needs_space("在", link) is True
    # But a colon before it is still exempt, same as any punctuation.
    assert needs_space(":", link) is False


# --- tokenize: ascii run must stop at a CJK character -------------------

def test_ascii_run_stops_before_cjk_with_no_space():
    tokens = tokenize("**不包含在這個 repo 裡**")
    assert tokens[:8] == ["**", "不", "包", "含", "在", "這", "個", "repo"]


def test_ascii_run_stops_before_cjk_punctuation_too():
    tokens = tokenize("裡**(不是我的東西)")
    assert tokens[0] == "裡"
    assert tokens[1] == "**("
    assert tokens[2] == "不"


# --- tight wrapping: paragraph must not break before it has to ----------

def test_loose_wrap_is_flagged():
    # 40 CJK chars (width 80) fit on one line, but this breaks after 39.
    lines = ["測" * 39, "測" * 2]
    issues = check_tight_wrap(lines)
    assert len(issues) == 1
    assert issues[0].line_no == 1


def test_tight_wrap_is_not_flagged():
    # Already broken at the canonical (tightest) point.
    lines = ["測" * 40, "測" * 1]
    assert check_tight_wrap(lines) == []


def test_single_line_paragraph_is_never_loose():
    assert check_tight_wrap(["A short line."]) == []


def test_loose_wrap_ignored_across_paragraph_break():
    # A blank line legitimately ends the paragraph, so the short first
    # line is not "loose" -- there is nothing to pull up into it.
    lines = ["測" * 10, "", "測" * 10]
    assert check_tight_wrap(lines) == []


def test_loose_wrap_ignores_list_and_table_lines():
    lines = ["- short item", "| a | b |"]
    assert check_tight_wrap(lines) == []


# --- ordered list sequencing --------------------------------------------

def test_ordered_list_correct_sequence():
    lines = ["1. one", "2. two", "3. three"]
    assert check_ordered_lists(lines) == []


def test_ordered_list_gap_is_flagged():
    lines = ["1. one", "2. two", "4. four"]
    issues = check_ordered_lists(lines)
    assert len(issues) == 1
    assert issues[0].line_no == 3
    assert "expected 3" in issues[0].message


def test_ordered_list_must_start_at_one():
    lines = ["2. two"]
    issues = check_ordered_lists(lines)
    assert len(issues) == 1
    assert "should start at 1" in issues[0].message


def test_nested_ordered_list_tracked_independently():
    lines = [
        "1. top one",
        "   1. nested one",
        "   2. nested two",
        "2. top two",
    ]
    assert check_ordered_lists(lines) == []


def test_nested_ordered_list_gap_is_flagged():
    lines = [
        "1. top one",
        "   1. nested one",
        "   3. nested three",
        "2. top two",
    ]
    issues = check_ordered_lists(lines)
    assert len(issues) == 1
    assert issues[0].line_no == 3


# --- stray spacing: literal space between two CJK characters ------------

def test_stray_space_between_cjk_chars_is_flagged():
    issues = check_spacing(["版權屬於各校及授課教 授"])
    assert len(issues) == 1
    assert issues[0].line_no == 1


def test_no_space_between_cjk_chars_is_not_flagged():
    assert check_spacing(["版權屬於各校及授課教授"]) == []


def test_space_between_cjk_and_ascii_is_not_flagged():
    # This is normal, expected spacing (see needs_space), not a typo.
    assert check_spacing(["歡迎透過 PTT 站內信"]) == []


def test_stray_space_inside_fenced_code_is_ignored():
    lines = ["```", "測 試", "```"]
    assert check_spacing(lines) == []


# --- blockquotes are wrappable prose, not excluded like lists/tables ----

def test_group_prose_paragraphs_strips_blockquote_marker():
    lines = ["> 第一行", "> 第二行"]
    groups = group_prose_paragraphs(lines)
    assert len(groups) == 1
    start, para_lines, prefix_width = groups[0]
    assert start == 0
    assert para_lines == ["第一行", "第二行"]
    assert prefix_width == display_width("> ")


def test_tight_wrap_accounts_for_blockquote_prefix_width():
    # 39 CJK chars (width 78) exactly fill a blockquote line's real
    # budget of 80 - 2 ("> ") = 78, so breaking after all 39 is tight.
    lines = ["> " + "測" * 39, "> " + "測"]
    assert check_tight_wrap(lines) == []


def test_loose_wrap_flagged_inside_blockquote():
    # Same 39-char budget, but broken one character too early.
    lines = ["> " + "測" * 38, "> " + "測" * 2]
    issues = check_tight_wrap(lines)
    assert len(issues) == 1
    assert issues[0].line_no == 1
