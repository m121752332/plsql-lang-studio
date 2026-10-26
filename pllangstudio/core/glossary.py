"""用語對照表（見 ADR-0010）。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import langfile
from .validate import covered


@dataclass
class Rule:
    find: str
    replace: str
    exceptions: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class Glossary:
    rules: list[Rule]
    simplified_exceptions: list[str]


def apply_rule(text: str, rule: Rule) -> str:
    if not rule.enabled or not rule.find:
        return text
    skip = covered(text, rule.exceptions)
    out, i, n = [], 0, len(rule.find)
    j = text.find(rule.find)
    while j >= 0:
        out.append(text[i:j])
        out.append(text[j:j + n] if skip & set(range(j, j + n)) else rule.replace)
        i = j + n
        j = text.find(rule.find, i)
    out.append(text[i:])
    return "".join(out)


def apply_rules(text: str, rules: list[Rule]) -> str:
    for r in rules:
        text = apply_rule(text, r)
    return text


def load(path: Path) -> Glossary:
    """檔案壞了（空檔、JSON 錯誤、欄位缺少）就改名成 .corrupt，改用預設用語表並重新存檔。"""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = [Rule(r["find"], r["replace"], r.get("except", []), r.get("enabled", True)) for r in data["rules"]]
        return Glossary(rules, data.get("simplified_exceptions", []))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        try:
            os.replace(path, path.with_name(path.name + ".corrupt"))
        except OSError:
            pass
        g = default()
        save(path, g)
        return g


def save(path: Path, g: Glossary) -> None:
    data = {
        "rules": [{"find": r.find, "replace": r.replace, "except": r.exceptions, "enabled": r.enabled}
                  for r in g.rules],
        "simplified_exceptions": g.simplified_exceptions,
    }
    langfile.atomic_write(Path(path), json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


# 2026-10-25～26 手動修正 Taiwan.lang 時確認過的規則與例外，順序有意義：較長的詞排前面。
_DEFAULT = [
    ("宏", "巨集", []),
    ("配置文件", "設定檔", []), ("配置嚮導", "設定精靈", []), ("配置", "設定", []),
    ("通過", "透過", ["通過計數", "通過]"]),
    ("訪問", "存取", []),
    ("註釋", "註解", []), ("文本", "文字", []), ("嚮導", "精靈", []),
    ("搜索欄", "搜尋列", []), ("搜索", "搜尋", []), ("工具欄", "工具列", []),
    ("自定義", "自訂", []), ("模板", "範本", []), ("新建", "新增", ["重新建"]),
    ("右鍵單擊", "按右鍵", []), ("單擊", "按一下", []), ("雙擊", "按兩下", []),
    ("高亮顯示", "醒目提示", []), ("高亮", "醒目提示", []),
    ("選項卡", "索引標籤", []), ("標籤頁", "分頁", []),
    ("撤銷", "復原", []), ("獲取", "取得", []),
    ("大數據", "大型資料", []), ("數據", "資料", []),
    ("賬戶", "帳戶", []), ("下劃線", "底線", []), ("創建", "建立", []),
    ("回車符", "歸位字元", []), ("回車字元", "歸位字元", []),
    ("匹配項", "相符項目", []), ("不匹配", "不相符", []), ("匹配", "相符", []),
    ("列表", "清單", []),
    ("會話", "工作階段", []), ("事務", "交易", []),
    ("首選項", "偏好設定", []), ("常規", "一般", []),
    ("天后", "天後", []),  # OpenCC 把「天后」當成神明名，PL/SQL 介面只會是「%1 天後過期」
]


def default() -> Glossary:
    return Glossary([Rule(f, r, list(e)) for f, r, e in _DEFAULT], ["游標", "批准"])
