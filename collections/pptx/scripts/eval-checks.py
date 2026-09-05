#!/usr/bin/env python3
"""pptx コレクションの検査精度テスト。リポジトリ保守用（配布物ではない）。

pptx-create の骨格でデッキを組み、pptx-review の lint が
「出るべき指摘を出し、出てはいけない指摘を出さない」ことを確かめる。

    python3 collections/pptx/scripts/eval-checks.py

python-pptx が必要。lint 自体は標準ライブラリだけで動く。
"""

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
LINT = ROOT / "pptx-review" / "scripts" / "pptx_lint.py"
ENGINE = ROOT / "pptx-create" / "references" / "engine-notes.md"
BLOCK = re.search(r"```python\n(.*?)```", ENGINE.read_text(), re.S).group(1).replace(
    'if __name__ == "__main__":\n    build()', "")
LOCK = {"fonts": ["Yu Gothic"],
        "colors": ["FFFFFF", "1A1A1A", "5C5C5C", "D9D9D6", "F4F4F2", "22313F", "B7282E"],
        "min_font_pt": 12}
CASES = []


def case(name, expect=(), forbid=(), lock=False):
    def wrap(fn):
        CASES.append((name, set(expect), set(forbid), fn, lock))
        return fn
    return wrap


def env(workdir):
    scope = {}
    cwd = os.getcwd()
    os.chdir(workdir)
    try:
        exec(compile(BLOCK, "skeleton", "exec"), scope)
    finally:
        os.chdir(cwd)
    return scope


def base(g, prs, n=5, title_size=None, body_size=None):
    """揃った本文ページを n 枚積む。"""
    for i in range(n):
        s = g["blank"](prs)
        g["text"](s, g["M"], g["TITLE_Y"], g["W"] - 2 * g["M"], g["TITLE_H"],
                  "揃ったページ %d の主張を一文で書いたタイトル" % (i + 1),
                  title_size or g["SIZE"]["title"], bold=True)
        g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.4, ["本文の一行目です。", "本文の二行目です。"],
                  body_size or g["SIZE"]["body"])
        g["page_source"](s, "出典: 資料")


# ---------------------------------------------------------------- 出てはいけない

@case("一文ページ", forbid=["MARGIN_DRIFT", "TITLE_POSITION_DRIFT", "BODY_SIZE_DRIFT"])
def _(g, p):
    base(g, p)
    g["slide_statement"](p, "問いは費用ではなく、許容できる欠品率である。")


@case("大きな数字", forbid=["TITLE_SIZE_DRIFT", "BODY_SIZE_DRIFT", "FONT_TOO_SMALL"])
def _(g, p):
    base(g, p)
    g["slide_hero_number"](p, "増分の3分の2は配送頻度で説明できる", "1.4pt", "増分 2.1pt のうち",
                           ["配送コストが月8.2万円上がった。"], "出典: 実績")


@case("濃い章扉", forbid=["PALETTE_DRIFT", "TITLE_POSITION_DRIFT", "COLOR_BAND", "SIDE_STRIPE"])
def _(g, p):
    base(g, p)
    g["slide_divider"](p, "02", "打ち手をどう選ぶか")


@case("白地の表紙", forbid=["TITLE_SIZE_DRIFT", "TITLE_POSITION_DRIFT"])
def _(g, p):
    g["slide_cover"](p, "在庫回転は改善したが、粗利は物流費に食われている", "上期レビュー", dark=False)
    base(g, p)


@case("淡い面色と図の地", forbid=["PALETTE_DRIFT", "TEXT_SHAPE_COLLISION"])
def _(g, p):
    base(g, p)
    g["slide_claim_evidence"](p, "図の地に淡い面を敷いたページの主張", ["読み取りの一文。"], "出典: 資料",
                              lambda sl, x, y, w, h: g["text"](sl, x, y, w, 0.4, "図の説明",
                                                               g["SIZE"]["note"], color="muted"))


@case("非対称分割", forbid=["MARGIN_DRIFT", "BODY_SIZE_DRIFT"])
def _(g, p):
    base(g, p)
    g["slide_split"](p, "残る0.7ポイントは燃料費である", ["前提"], ["為替に連動する。"], "出典: 通知")


@case("強調色を1ページで使う", forbid=["PALETTE_DRIFT"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "この値は前提が崩れると変わる")
    g["text"](s, g["M"], g["BODY_Y"], 5.0, 1.0, "▲ 12%", 32, color="accent", bold=True)


@case("密度を変えた表ページ（20pt）", forbid=["BODY_SIZE_DRIFT"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "選択肢は3つあり、週3回が最も良い")
    g["text"](s, g["M"], g["BODY_Y"], g["W"] - 2 * g["M"], 2.5,
              ["週5回: +2.1pt", "週4回: +1.5pt", "週3回: +0.9pt"], 20)


@case("左端の僅かな差（0.08in）", forbid=["MARGIN_DRIFT"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "左端がごく僅かに違うページの主張")
    g["text"](s, g["M"] + 0.08, g["BODY_Y"], 7.0, 1.0, "本文", g["SIZE"]["body"])


@case("ロックに登録した指摘は判定から外れる", forbid=["PALETTE_DRIFT"], lock=True)
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "文字色を意図的に変えたページの主張")
    g["C"]["odd"] = "222222"
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.0, "意図的に別の文字色。", g["SIZE"]["body"], color="odd")


# ---------------------------------------------------------------- 出るべき

@case("タイトル30pt", expect=["TITLE_SIZE_DRIFT"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["text"](s, g["M"], g["TITLE_Y"], g["W"] - 2 * g["M"], g["TITLE_H"], "サイズだけずれたタイトル", 30, bold=True)
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.0, "本文", g["SIZE"]["body"])


@case("タイトル位置ずれ", expect=["TITLE_POSITION_DRIFT", "MARGIN_DRIFT"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["text"](s, 1.2, 0.4, 10.0, g["TITLE_H"], "位置だけずれたタイトル", g["SIZE"]["title"], bold=True)
    g["text"](s, 1.2, g["BODY_Y"], 7.0, 1.0, "本文", g["SIZE"]["body"])


@case("本文17pt", expect=["BODY_SIZE_DRIFT"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "本文サイズだけずれたページの主張")
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.2, ["本文が17ptになっている。", "他は16pt。"], 17)


@case("文字色222222", expect=["PALETTE_DRIFT"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "文字色だけずれたページの主張")
    g["C"]["odd"] = "222222"
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.2, ["文字色が222222になっている。"], g["SIZE"]["body"], color="odd")


@case("文章だけ7枚", expect=["FORM_FAMILY_MONOTONE"])
def _(g, p):
    base(g, p, n=7)


@case("タイトル下の飾り線", expect=["ACCENT_LINE_UNDER_TITLE"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "飾り線を引いたページの主張")
    g["rect"](s, g["M"], 1.9, 3.0, 0.05, "accent")
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.0, "本文", g["SIZE"]["body"])


@case("絵文字と誇張語彙", expect=["EMOJI", "AI_VOCAB"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "絵文字を入れたページの主張")
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.0, "🚀 シームレスな体験を実現します", g["SIZE"]["body"])


@case("話題ラベルのタイトル", expect=["TITLE_TOPIC_LABEL"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "まとめ")
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.0, "本文", g["SIZE"]["body"])


@case("仮置き文言", expect=["PLACEHOLDER_TEXT"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "仮置きが残っているページの主張")
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.0, "ここに数値を入力", g["SIZE"]["body"])


# ---------------------------------------------------------------- 判断が難しい条件

@case("多数派が割れている（3対3）",
      forbid=["TITLE_POSITION_DRIFT", "MARGIN_DRIFT"])
def _(g, p):
    for i in range(3):
        s = g["blank"](p)
        g["text"](s, g["M"], g["TITLE_Y"], g["W"] - 2 * g["M"], g["TITLE_H"],
                  "型Aのページ %d の主張を一文で書く" % (i + 1), g["SIZE"]["title"], bold=True)
        g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.4, ["本文の行。"], g["SIZE"]["body"])
    for i in range(3):
        s = g["blank"](p)
        g["text"](s, 1.2, 0.9, 11.0, g["TITLE_H"],
                  "型Bのページ %d の主張を一文で書く" % (i + 1), g["SIZE"]["title"], bold=True)
        g["text"](s, 1.2, 2.5, 7.0, 1.4, ["本文の行。"], g["SIZE"]["body"])


@case("多数派が既定値ではないデッキ", expect=["MARGIN_DRIFT"])
def _(g, p):
    for i in range(5):
        s = g["blank"](p)
        g["text"](s, 1.0, 0.8, 11.0, g["TITLE_H"],
                  "左端1.0で揃ったページ %d の主張" % (i + 1), g["SIZE"]["title"], bold=True)
        g["text"](s, 1.0, 2.4, 11.0, 1.4, ["本文の行。"], g["SIZE"]["body"])
    s = g["blank"](p)
    g["text"](s, 0.6, 0.8, 11.0, g["TITLE_H"], "左端だけ0.6のページの主張", g["SIZE"]["title"], bold=True)
    g["text"](s, 0.6, 2.4, 11.0, 1.4, ["本文の行。"], g["SIZE"]["body"])


@case("本文ちょうど4枚＋ずれ1枚", expect=["TITLE_POSITION_DRIFT"])
def _(g, p):
    base(g, p, n=4)
    s = g["blank"](p)
    g["text"](s, 1.5, 0.3, 8.0, g["TITLE_H"], "5枚目でずれる", g["SIZE"]["title"], bold=True)
    g["text"](s, 1.5, g["BODY_Y"], 7.0, 1.4, ["本文の行。"], g["SIZE"]["body"])


@case("グループ内のタイトル", expect=["TITLE_POSITION_DRIFT"])
def _(g, p):
    from pptx.util import Inches, Pt
    base(g, p)
    s = g["blank"](p)
    group = s.shapes.add_group_shape()
    inner = group.shapes.add_textbox(Inches(1.3), Inches(0.35), Inches(9), Inches(1.2))
    run = inner.text_frame.paragraphs[0].add_run()
    run.text = "グループ内のタイトル"
    run.font.size = Pt(g["SIZE"]["title"])
    run.font.bold = True
    g["text"](s, 1.3, g["BODY_Y"], 7.0, 1.4, ["本文の行。"], g["SIZE"]["body"])


def main():
    workdir = tempfile.mkdtemp(prefix="pptx-eval-")
    deck_dir = os.path.join(workdir, "deck")
    os.makedirs(deck_dir, exist_ok=True)
    with open(os.path.join(deck_dir, "design-lock.json"), "w", encoding="utf-8") as fh:
        json.dump(LOCK, fh, ensure_ascii=False)
    allow_lock = os.path.join(deck_dir, "allow-lock.json")
    with open(allow_lock, "w", encoding="utf-8") as fh:
        json.dump(dict(LOCK, allow=[{"code": "PALETTE_DRIFT", "reason": "意図的"}]), fh, ensure_ascii=False)

    ok = failures = 0
    for i, (name, expect, forbid, fn, use_lock) in enumerate(CASES):
        scope = env(workdir)
        prs = scope["new_deck"]()
        fn(scope, prs)
        path = os.path.join(workdir, "case-%02d.pptx" % i)
        prs.save(path)
        out = os.path.join(workdir, "case-%02d.json" % i)
        cmd = [sys.executable, str(LINT), path, "--json-out", out]
        if use_lock:
            cmd += ["--lock", allow_lock]
        subprocess.run(cmd, capture_output=True)
        report = json.load(open(out, encoding="utf-8"))
        codes = set()
        for slide in report["slides"]:
            codes.update(f["code"] for f in slide["findings"] if not f.get("allowed"))
        codes.update(f["code"] for f in report["deck_findings"] if not f.get("allowed"))
        missing, wrong = expect - codes, forbid & codes
        if missing or wrong:
            failures += 1
            print("NG  %-30s 出なかった: %s / 出てはいけない: %s"
                  % (name, sorted(missing) or "-", sorted(wrong) or "-"))
        else:
            ok += 1
            print("ok  %s" % name)
    print("\n%d/%d 合格" % (ok, ok + failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
