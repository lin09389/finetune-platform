from auto_fix_encoding import (
    fix_file,
    fix_truncated_chinese,
    fix_unterminated_strings,
    is_valid_python,
)


def test_fix_unterminated_strings_closes_double_quote():
    content = 'x = "abc?'
    fixed = fix_unterminated_strings(content)
    assert fixed.count('"') % 2 == 0
    assert is_valid_python(fixed)


def test_fix_unterminated_strings_closes_single_quote():
    content = "x = 'abc?"
    fixed = fix_unterminated_strings(content)
    assert fixed.count("'") % 2 == 0
    assert is_valid_python(fixed)


def test_fix_truncated_chinese_rewrites_question_mark_after_cjk():
    fixed = fix_truncated_chinese("中文?")
    assert "?" not in fixed


def test_fix_file_can_repair_simple_invalid_python(tmp_path):
    target = tmp_path / "broken.py"
    target.write_text('x = "hello?', encoding="utf-8")

    success, message = fix_file(str(target))
    assert success, message
    repaired = target.read_text(encoding="utf-8")
    assert is_valid_python(repaired)
