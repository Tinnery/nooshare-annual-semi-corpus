"""check 命令纯函数单测：不访问 PG / RustFS，不依赖网络。"""

from annual_semi_corpus.cli import (
    build_md_key,
    compare_keys,
    period_to_slot,
    project_actual_keys,
)


def test_period_to_slot_q_format():
    """q 词法：q2 -> 2、q4 -> 4；q1/q3 不产生 published 对象。"""
    assert period_to_slot("2008q1") is None
    assert period_to_slot("2008q2") == (2008, 2)
    assert period_to_slot("2008q3") is None
    assert period_to_slot("2018Q4") == (2018, 4)
    assert period_to_slot("bad-period") is None


def test_period_to_slot_h_format():
    """h 词法：h1 -> 2（半年报）、h2 -> 4（年报）。"""
    assert period_to_slot("2018h1") == (2018, 2)
    assert period_to_slot("2018h2") == (2018, 4)
    assert period_to_slot("2018h3") is None


def test_build_md_key():
    """published key 命名契约。"""
    assert build_md_key("000001", 2018, 4) == "published/000001/000001_2018_4.md"
    assert build_md_key("000001", 2018, 2, "custom/") == "custom/000001/000001_2018_2.md"


def test_compare_keys():
    """期望−实有=缺失，实有−期望=孤儿；结果有序便于稳定输出。"""
    result = compare_keys({"a", "b", "c"}, {"b", "c", "d"})
    assert result.expected_count == 3
    assert result.actual_count == 3
    assert result.missing == ("a",)
    assert result.orphans == ("d",)


def test_project_actual_keys_by_code():
    """public 模式：多个 md 折叠为同一 code 前缀。"""
    keys = {
        "published/000001/000001_2018_4.md",
        "published/000001/000001_2019_2.md",
        "published/000002/000002_2018_2.md",
        "other/000003.md",
    }
    assert project_actual_keys(keys, "published/", True) == {
        "published/000001/",
        "published/000002/",
    }
    assert project_actual_keys(keys, "published/", False) == keys
