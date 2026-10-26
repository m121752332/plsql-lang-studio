from pllangstudio.core import validate


def codes(source, target, exceptions=()):
    return {i.code for i in validate.check(source, target, exceptions)}


def test_ok_translation_has_no_issues():
    assert codes("&Cancel", "&取消") == set()


def test_missing_placeholder_is_error():
    issues = validate.check("%1 records deleted", "條記錄已刪除")
    assert [(i.level, i.code) for i in issues] == [("error", "PLACEHOLDER")]


def test_reordered_placeholders_are_fine():
    assert codes("Copy %1 to %2", "把 %2 複製自 %1") == set()


def test_lost_accelerator_is_warning():
    assert codes("&Cancel", "取消") == {"ACCEL"}


def test_double_ampersand_is_not_accelerator():
    assert codes("Tom && Jerry", "湯姆 && 傑利") == set()


def test_untranslated_word_is_warning():
    assert codes("Tablespace", "Tablespace") == {"UNTRANSLATED"}


def test_acronyms_paths_urls_are_not_untranslated():
    for s in ["DML", "AL32UTF8", "v 1.10 ", "Box1.bmp", r"U:\PLSQLdev\Icons\Box1.bmp",
              "http://www.allroundautomations.com/x.html"]:
        assert "UNTRANSLATED" not in codes(s, s), s


def test_simplified_char_detected_and_exceptions_respected():
    assert codes("Expires in %1 days", "%1 天后過期") == {"SIMPLIFIED"}
    assert validate.simplified_spans("%1 天后過期") == [(4, 5)]
    assert codes("Cursor", "游標", ["游標"]) == set()
    assert codes("Approve", "批准", ["游標", "批准"]) == set()


def test_exception_does_not_hide_other_simplified_chars():
    assert validate.simplified_spans("游標后", ["游標"]) == [(2, 3)]


def test_edge_spaces_warning():
    assert codes(" Logging", "日誌記錄") == {"SPACES"}
    assert codes(" Logging", " 日誌記錄") == set()
