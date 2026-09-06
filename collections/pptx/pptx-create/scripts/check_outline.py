#!/usr/bin/env python3
"""構成（deck/outline.json）の検査。標準ライブラリだけで動く。

生成してから直すのは遅い。**主張文になっていないタイトル、決め手の無い形式選択、
出典の無い数字、骨格に無い原型**は、組む前にここで止める。

    python3 <skills>/pptx-create/scripts/check_outline.py deck/outline.json
    python3 <skills>/pptx-create/scripts/check_outline.py deck/outline.json --lock deck/design-lock.json

終了コード: 0=合格 / 1=指摘あり / 2=実行できない（lint と揃えてある）

`outline.md`（散文）は捨てない。**.json を正とし、.md はそこから起こす。**
.md は人が読んで筋を確かめるため（ゴーストデッキテスト）、.json は機械が
欠落を拾うためにある。二重に書かせるためではない。

JSON Schema は使わない。使えるライブラリに `jsonschema` が無いこともあるうえ、
ここで見たいのは型ではなく**書いたか／選んだか**なので、素朴な検査で足りる。
"""

import argparse
import json
import os
import pathlib
import re
import sys

EXIT_OK, EXIT_FINDINGS, EXIT_ERROR = 0, 1, 2

# 話題ラベル。pptx-review の pptx_lint.py と同じ語彙を持つ（片方だけ増やさない）
TOPIC_LABELS = {
    "まとめ", "概要", "背景", "目的", "課題", "現状", "目次", "アジェンダ", "市場概況",
    "今後の展望", "展望", "ポイント", "要点", "はじめに", "おわりに", "結論", "提案",
    "次のステップ", "検討事項", "考察", "分析", "方針", "施策", "全体像", "サマリー",
}
TOPIC_SUFFIXES = ("について", "のご紹介", "の全体像", "の概要", "の背景", "の課題", "の現状")
NO_TITLE_ROLES = {"表紙", "章扉", "目次", "付録の扉"}
DIGITS = re.compile(r"[0-9０-９]")
# 日付・時期は主張ではないので出典を求めない（「10月から着手」に出典は要らない）
WHEN = re.compile(r"[0-9０-９]+\s*(?:年度?|月|日|週|期|Q[1-4１-４]|四半期|か月|ヶ月|カ月)")


def archetypes():
    """骨格の skeleton() が持つ原型名。骨格に無い名前を構成に書かせない。"""
    notes = pathlib.Path(__file__).resolve().parents[1] / "references" / "engine-notes.md"
    try:
        block = re.search(r"```python\n(.*?)```", notes.read_text(encoding="utf-8"), re.S).group(1)
    except (OSError, AttributeError):
        return None                       # 骨格が読めないなら原型の照合は飛ばす
    return set(re.findall(r'if kind == "([\w-]+)"', block))


def check(pages, known, grammar):
    out = []

    def note(n, msg):
        out.append("ページ %s: %s" % (n, msg))

    for i, page in enumerate(pages, 1):
        n = page.get("n", i)
        role = str(page.get("role", "")).strip()
        title = str(page.get("title", "")).strip()

        if not title and role not in NO_TITLE_ROLES:
            note(n, "タイトルが空。主張を一文で書く")
        elif title:
            bare = title.rstrip("。").strip()
            if bare in TOPIC_LABELS or bare.endswith(TOPIC_SUFFIXES):
                note(n, "タイトルが話題ラベル「%s」。主張を一文で書く" % title[:30])

        cands = page.get("candidates") or []
        because = str(page.get("chosen_because", "")).strip()
        if role not in NO_TITLE_ROLES:
            if len(cands) < 2:
                note(n, "形式の候補が %d 個。2つ以上出してから選ぶ" % len(cands))
            if not because:
                note(n, "選んだ決め手が空。理由を書けないなら、まだ選んでいない")

        arch = str(page.get("archetype", "")).strip()
        if known is not None and arch and arch not in known:
            note(n, "原型「%s」は骨格に無い（%s）" % (arch, "、".join(sorted(known)[:6]) + " など"))

        body = " ".join(str(page.get(k, "")) for k in ("title", "exhibit", "note"))
        if DIGITS.search(WHEN.sub("", body)) and not str(page.get("evidence", "")).strip():
            note(n, "数字があるのに出典が無い。evidence を書くか「要確認」と書く")

    densities = [str(p.get("density", "")).strip() for p in pages if p.get("density")]
    if len(densities) >= 4 and len(set(densities)) == 1:
        out.append("デッキ全体: 密度が全ページ「%s」で同じ。密なページの後に余白のページを置く" % densities[0])

    if grammar:
        out.extend(check_grammar(pages, grammar))
    return out


def check_grammar(pages, grammar):
    """デッキの文法が要求する読みの筋を見る。**検査できるものだけを見る。**

    「各展示物に含意を付ける」のような文意の判断は機械にできない。それは
    pptx-review の visual-qa-prompt.md の観点に置き、ここでは扱わない。
    """
    out = []
    arc = [str(a).strip() for a in (grammar.get("arc") or [])]
    if not arc:
        return out
    lead = arc[0]
    body = [p for p in pages if str(p.get("role", "")).strip() not in NO_TITLE_ROLES]
    if lead and body:
        head = body[:3]
        if not any(lead in str(p.get("role", "")) or lead in str(p.get("title", "")) for p in head):
            out.append("文法 %s: 読みの筋が「%s」から始まるのに、本文の最初の3枚に現れない"
                       % (grammar.get("id", "?"), lead))
    seen = [a for a in arc if any(a in str(p.get("role", "")) for p in pages)]
    if seen and seen != [a for a in arc if a in seen]:
        out.append("文法 %s: 段の順序が %s になっている。arc は %s"
                   % (grammar.get("id", "?"), "→".join(seen), "→".join(arc)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="構成（outline.json）の検査")
    ap.add_argument("outline", help="deck/outline.json")
    ap.add_argument("--lock", help="deck/design-lock.json（grammar があれば読みの筋も見る）")
    args = ap.parse_args(argv)

    try:
        data = json.loads(pathlib.Path(args.outline).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("ERROR: %s を読めない: %s" % (args.outline, exc), file=sys.stderr)
        return EXIT_ERROR
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        print("ERROR: pages が空。1ページ1オブジェクトで書く", file=sys.stderr)
        return EXIT_ERROR

    grammar = None
    if args.lock:
        try:
            grammar = json.loads(pathlib.Path(args.lock).read_text(encoding="utf-8")).get("grammar")
        except (OSError, ValueError) as exc:
            print("ERROR: %s を読めない: %s" % (args.lock, exc), file=sys.stderr)
            return EXIT_ERROR

    findings = check(pages, archetypes(), grammar)
    print("--- check_outline: %d ページ, %d 件" % (len(pages), len(findings)))
    for line in findings:
        print("  " + line, file=sys.stderr)
    return EXIT_FINDINGS if findings else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
