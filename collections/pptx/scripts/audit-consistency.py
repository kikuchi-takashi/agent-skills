#!/usr/bin/env python3
"""pptx コレクションの文書・実装整合監査。リポジトリ保守用（配布物ではない）。

文書に書いた数値や名前が、骨格コードやスクリプトの実装と食い違っていないかを機械的に確かめる。
食い違いは利用者に見えない形で品質を落とすため、変更のたびに走らせる。

    python3 collections/pptx/scripts/audit-consistency.py
"""

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CREATE = ROOT / "pptx-create" / "references"
REVIEW = ROOT / "pptx-review"
SKELETON = re.search(r"```python\n(.*?)```",
                     (CREATE / "engine-notes.md").read_text(), re.S).group(1)
issues = []


def note(msg):
    issues.append(msg)


def skeleton_constants():
    head = SKELETON.split("def col(")[0]
    consts = dict(re.findall(r"^(M|GAP|COL_W) = ([\d.]+)", head, re.M))
    m = re.search(r"TITLE_Y, TITLE_H, BODY_Y, BODY_END, FOOT_Y = ([\d., ]+)", head)
    if m:
        consts.update(dict(zip(["TITLE_Y", "TITLE_H", "BODY_Y", "BODY_END", "FOOT_Y"],
                               [v.strip() for v in m.group(1).split(",")])))
    scales = {}
    for mode in ("talk", "doc"):
        m = re.search(r'"%s":\s*\{(.*?)\}' % mode, SKELETON, re.S)
        if m:
            scales[mode] = dict(re.findall(r'"(\w+)": (\d+)', m.group(1)))
    if not scales:                                   # 単一スケールの骨格にも対応
        m = re.search(r"SIZE = \{(.*?)\}", SKELETON, re.S)
        if m:
            scales["doc"] = dict(re.findall(r'"(\w+)": (\d+)', m.group(1)))
    colors = set(re.findall(r'"\w+": "([0-9A-F]{6})"', head))
    return consts, scales, colors


def in_range(value, text):
    """'14〜16' や '18' のような表記に値が収まるか。"""
    nums = [float(x) for x in re.findall(r"\d+", text)]
    if not nums:
        return True
    return min(nums) <= value <= max(nums)


def check_grid(consts):
    lock_md = (CREATE / "design-lock.md").read_text()
    patterns = {
        "M": r"余白: 上下左右 ([\d.]+)",
        "TITLE_Y": r"タイトル: y ([\d.]+)",
        "BODY_Y": r"本文開始: y ([\d.]+)",
        "BODY_END": r"本文終端: y ([\d.]+)",
        "GAP": r"要素間の最小間隔: ([\d.]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, lock_md)
        if m and key in consts and float(consts[key]) != float(m.group(1)):
            note("グリッド %s: 骨格 %s / design-lock.md %s" % (key, consts[key], m.group(1)))


def check_type_scale(scales):
    """骨格の各密度モードのサイズが、文書の型スケールの範囲に収まっているか。"""
    lock_md = (CREATE / "design-lock.md").read_text()
    rows = {label: {"talk": talk, "doc": doc} for label, talk, doc in re.findall(
        r"\| (表紙タイトル|ページタイトル|小見出し|本文|注記|出典) \| ([\d〜—]+) \| ([\d〜—]+) \|", lock_md)}
    mapping = {"cover": "表紙タイトル", "title": "ページタイトル", "h2": "小見出し",
               "body": "本文", "note": "注記", "source": "出典"}
    for mode, sizes in scales.items():
        for key, label in mapping.items():
            if key not in sizes or label not in rows:
                continue
            doc = rows[label].get(mode, "")
            if not re.search(r"\d", doc):        # 「—」の欄は範囲を定めていない
                continue
            if not in_range(float(sizes[key]), doc):
                note("型スケール %s（%s）: 骨格 %spt が design-lock.md の %s に収まらない"
                     % (label, mode, sizes[key], doc))


def check_guardrails(consts, _scales):
    qa = (CREATE / "qa.md").read_text()
    pairs = [("余白", r"\| 余白 \| 上下左右 ([\d.]+)in", "M"),
             ("要素間の最小間隔", r"\| 要素間の最小間隔 \| ([\d.]+)in", "GAP")]
    for label, pat, key in pairs:
        m = re.search(pat, qa)
        if m and key in consts and float(consts[key]) != float(m.group(1)):
            note("数値ガードレール %s: qa.md %s / 骨格 %s" % (label, m.group(1), consts[key]))


def check_flags():
    """このコレクションのスクリプトに渡しているフラグが実在するかを見る。
    外部コマンド（描画に使う実行ファイルなど）のフラグは対象外。"""
    scripts = ("pptx_lint.py", "render_preview.py", "extract_style.py")
    every = {"--help"}
    for script in scripts:
        out = subprocess.run([sys.executable, str(REVIEW / "scripts" / script), "--help"],
                             capture_output=True, text=True).stdout
        every |= set(re.findall(r"(--[a-z-]+)", out))
    docs = [CREATE / "qa.md", REVIEW / "SKILL.md", ROOT / "pptx-edit" / "SKILL.md",
            ROOT / "pptx-edit" / "references" / "match-existing-design.md",
            CREATE / "engine-notes.md", CREATE / "typography-ja.md",
            ROOT / "pptx-create" / "SKILL.md"]
    for doc in docs:
        text = doc.read_text()
        used = set()
        for block in re.findall(r"```(?:python|bash)?\n(.*?)```", text, re.S):
            if not any(name in block for name in scripts):
                continue                                  # 外部コマンドだけの塊は見ない
            used |= set(re.findall(r'"(--[a-z-]+)"', block))
        used |= set("--" + x for x in re.findall(r"`--([a-z-]+)`", text))
        for flag in sorted(used - every):
            note("%s が存在しないフラグ %s を使っている" % (doc.name, flag))


def check_lock_roundtrip(sample):
    if not sample or not os.path.exists(sample):
        return
    with tempfile.TemporaryDirectory() as td:
        lock = os.path.join(td, "lock.json")
        subprocess.run([sys.executable, str(REVIEW / "scripts" / "extract_style.py"), sample,
                        "--json-out", lock], capture_output=True)
        if not os.path.exists(lock):
            note("extract_style がロックを書き出せない")
            return
        data = json.load(open(lock, encoding="utf-8"))
        for key in ("fonts", "colors", "min_font_pt", "allow"):
            if key not in data:
                note("extract_style の出力に %s が無い（lint の --lock が期待する）" % key)
        r = subprocess.run([sys.executable, str(REVIEW / "scripts" / "pptx_lint.py"), sample,
                            "--lock", lock], capture_output=True, text=True)
        if r.returncode >= 2:
            note("extract_style の出力を --lock に渡すと lint が異常終了する")


def check_codes():
    lint_src = (REVIEW / "scripts" / "pptx_lint.py").read_text()
    rubric = (REVIEW / "references" / "review-rubric.md").read_text()
    declared = set()
    for group in re.findall(r"\| ([A-Z_]{4,}(?: / [A-Z_]{4,})*) \|", rubric):
        declared.update(group.split(" / "))
    for code in sorted(declared):
        if code not in lint_src:
            note("監査基準にあるが lint に無いコード: %s" % code)
    emitted = set(re.findall(r'"code": "([A-Z_]+)"', lint_src))
    emitted |= set(re.findall(r'add\((?:r\["index"\]|i|index), "([A-Z_]+)"', lint_src))
    emitted |= set(re.findall(r'add\("([A-Z_]+)"', lint_src))
    for code in sorted(emitted - declared):
        note("lint が出すが監査基準に無いコード: %s" % code)


def check_components():
    """文書が挙げる部品が骨格に実装されているか。"""
    fns = set(re.findall(r"^def (\w+)", SKELETON, re.M))
    named = set(re.findall(r"`(table|timeline|flow|metrics|quote|before_after|chrome|picture|scrim)`",
                           (CREATE / "layout-catalog.md").read_text()))
    for name in sorted(named - fns):
        note("layout-catalog.md が挙げる部品 %s が骨格に無い" % name)


def check_chart_kinds():
    """骨格の CHART_KINDS と、文書が挙げる図表の種類が一致するか。"""
    m = re.search(r"CHART_KINDS = \{(.*?)\}", SKELETON, re.S)
    if not m:
        note("骨格に CHART_KINDS が無い")
        return
    kinds = set(re.findall(r'"(\w+)":', m.group(1)))
    for doc in (CREATE / "design-principles.md", CREATE / "layout-catalog.md"):
        named = set(re.findall(r"`(bar|bar_stacked|bar_h|line|area|pie|doughnut)`", doc.read_text()))
        for kind in sorted(named - kinds):
            note("%s が挙げる図表 %s が骨格に無い" % (doc.name, kind))


def check_archetypes():
    kinds = set(re.findall(r'if kind == "([\w-]+)"', SKELETON))
    fns = set(re.findall(r"^def slide_(\w+)", SKELETON, re.M))
    for doc in (CREATE / "layout-catalog.md", ROOT / "pptx-create" / "SKILL.md"):
        named = set(re.findall(r"`(cover|divider|claim-evidence|split-asymmetric|comparison|"
                               r"statement|hero-number|trend|structure|photo-full|photo-half|"
                               r"roadmap|before-after|metrics|table|steps|closing|appendix)`",
                               doc.read_text()))
        for kind in sorted(named - kinds):
            note("%s が挙げる原型 %s に skeleton() の実装が無い" % (doc.name, kind))
    if not fns:
        note("骨格にレイアウト関数が1つも無い")


def main():
    sample = sys.argv[1] if len(sys.argv) > 1 else None
    consts, scales, _ = skeleton_constants()
    check_grid(consts)
    check_type_scale(scales)
    check_guardrails(consts, scales)
    check_flags()
    check_codes()
    check_archetypes()
    check_chart_kinds()
    check_components()
    check_lock_roundtrip(sample)
    print("=== 文書と実装の整合監査 ===")
    for i in issues:
        print("NG", i)
    print("問題 %d 件" % len(issues))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
