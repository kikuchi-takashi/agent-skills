#!/usr/bin/env python3
"""pptx コレクションの検査精度テスト。リポジトリ保守用（配布物ではない）。

pptx-create の骨格でデッキを組み、pptx-review の lint が
「出るべき指摘を出し、出てはいけない指摘を出さない」ことを確かめる。

    python3 collections/pptx/scripts/eval-checks.py

python-pptx が必要。lint 自体は標準ライブラリだけで動く。
"""

import json
import math
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
LINT = ROOT / "pptx-review" / "scripts" / "pptx_lint.py"
PALETTE_SCRIPT = ROOT / "pptx-design" / "scripts" / "generate_palette.py"
ENGINE = ROOT / "pptx-create" / "references" / "engine-notes.md"
BLOCK = re.search(r"```python\n(.*?)```", ENGINE.read_text(), re.S).group(1).replace(
    'if __name__ == "__main__":\n    build()', "")
TEST_PALETTE = {
    "bg": "FFFEF8", "text": "17251F", "muted": "5B6F65",
    "line": "CAD8D0", "panel": "EEF5F0", "primary": "176B55", "accent": "C46A24",
}
LOCK = {"fonts": ["Yu Gothic"],
        "palette_basis": "評価用の緑と橙。固定色への回帰を検出する",
        "palette": TEST_PALETTE,
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


@case("ロックに登録した指摘は判定から外れる",
      forbid=["PALETTE_DRIFT", "DESIGN_LOCK_COLOR"], lock=True)
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


@case("タイトル29pt（1ptだけ違う）", expect=["TITLE_SIZE_DRIFT"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["text"](s, g["M"], g["TITLE_Y"], g["W"] - 2 * g["M"], g["TITLE_H"],
              "1ptだけ違うタイトル", g["SIZE"]["title"] + 1, bold=True)
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.4, ["本文の行。"], g["SIZE"]["body"])


@case("タイトル位置 0.09in の差", forbid=["TITLE_POSITION_DRIFT"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["text"](s, g["M"] + 0.09, g["TITLE_Y"], g["W"] - 2 * g["M"], g["TITLE_H"],
              "ごく僅かに動いたタイトル", g["SIZE"]["title"], bold=True)
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.4, ["本文の行。"], g["SIZE"]["body"])


# 折り返しが確実に起きるよう、幅を狭めたタイトル枠で試す（1行あたり約10文字）
_NARROW = 4.0


@case("タイトルの最終行が1文字", expect=["TITLE_ORPHAN_LINE"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["text"](s, g["M"], g["TITLE_Y"], _NARROW, g["TITLE_H"],
              "一次対応の負荷が固定費として定着しつつあるこ", g["SIZE"]["title"], bold=True)
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.4, ["本文の行。"], g["SIZE"]["body"])


@case("折り返すが最終行は十分長い", forbid=["TITLE_ORPHAN_LINE"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["text"](s, g["M"], g["TITLE_Y"], _NARROW, g["TITLE_H"],
              "一次対応の負荷が固定費として定着している", g["SIZE"]["title"], bold=True)
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.4, ["本文の行。"], g["SIZE"]["body"])


@case("新しい原型（推移・構造・付録）", forbid=["TITLE_POSITION_DRIFT", "MARGIN_DRIFT",
                                              "BODY_SIZE_DRIFT", "TEXT_OVERFLOW_LIKELY"])
def _(g, p):
    base(g, p)
    g["slide_trend"](p, "問い合わせ件数は3年連続で増えている",
                     ["2024年度", "2025年度", "2026年度"], [("件数（千件）", (8.2, 9.1, 10.7))],
                     ["伸びは年8%で安定している。"], "出典: 集計", kind="line")
    g["slide_structure"](p, "打ち手は効果と着手のしやすさで4つに分かれる",
                         [("すぐ効く", "自動応答の導入。"), ("効くが重い", "基幹連携。"),
                          ("軽いが小さい", "FAQ整備。"), ("後回し", "全面刷新。")],
                         ("効果 →", "着手のしやすさ →"), "出典: 整理")
    g["slide_appendix"](p, "算出の前提", ["実績を年換算した。"], "出典: 実績")


@case("図表7種がすべて作れる", forbid=["TEXT_OVERFLOW_LIKELY"])
def _(g, p):
    base(g, p)
    for kind in ("bar", "bar_stacked", "line", "area", "pie", "doughnut", "bar_h"):
        s = g["blank"](p)
        g["page_title"](s, "図表 %s を主役にしたページの主張" % kind)
        series = [("系列1", (3.0, 5.0, 4.0))]
        if kind in ("bar_stacked", "line", "area"):
            series.append(("系列2", (1.0, 2.0, 1.5)))
        g["chart"](s, g["M"], g["BODY_Y"], 7.0, 3.5, ["A", "B", "C"], series, kind=kind)


@case("新しい原型（工程・対比・指標・表）", forbid=["TITLE_POSITION_DRIFT", "MARGIN_DRIFT",
                                                  "BODY_SIZE_DRIFT", "TEXT_OVERFLOW_LIKELY",
                                                  "FONT_TOO_SMALL"])
def _(g, p):
    base(g, p)
    g["slide_roadmap"](p, "10月から12月で段階的に進める",
                       [("10月", "対象業務の選定"), ("11月", "実機での確認"), ("12月", "導入可否の判断")],
                       ["各段階の終わりに確認の場を設ける。"], "出典: 計画")
    g["slide_before_after"](p, "一次対応にかける時間は半分になる",
                            ["月480時間", "残業 月40時間"], ["月240時間", "残業 月10時間"],
                            ["削減分は個別対応に回す。"], source="出典: 試算")
    g["slide_metrics"](p, "3つの指標で効果を測る",
                       [("40%", "対応時間の削減"), ("290件", "月間の自動応答"), ("1.2か月", "投資回収")],
                       ["いずれも導入3か月時点の見込みである。"], "出典: 試算")
    g["slide_table"](p, "選択肢は3つあり、Aが最も早い",
                     [["案", "費用", "期間"], ["A", "180万円", "3か月"], ["B", "340万円", "6か月"]],
                     ["費用と期間は比例しない。"], [2, 1, 1], "出典: 試算")


@case("部品（流れ・引用・ページ番号）", forbid=["TEXT_OVERFLOW_LIKELY", "FONT_TOO_SMALL",
                                              "TEXT_SHAPE_COLLISION"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "処理は3段で流れる")
    g["flow"](s, g["M"], g["BODY_Y"], g["W"] - 2 * g["M"], 1.8,
              [("受付", "質問を受ける"), ("判定", "定型かを見る"), ("応答", "回答を返す")])
    g["quote"](s, g["M"], 4.6, 9.0, ["「同じ質問に何度も答えていた」"], "サポート部 担当者")
    g["chrome"](s, page=6, total=6, section="第2章 打ち手")


@case("主役のいない等分の数字を咎める", expect=["EQUAL_EMPHASIS"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "3つの指標がいずれも改善した")
    cols = g["spread"](3, g["M"], g["W"] - 2 * g["M"], gap=0.5)
    for (cx, cw), (value, label) in zip(cols, [("42%", "解約率"), ("18日", "リード"), ("3.1倍", "問合せ")]):
        g["text"](s, cx, g["BODY_Y"], cw, 1.0, value, 44, color="accent", bold=True)
        g["text"](s, cx, g["BODY_Y"] + 1.1, cw, 0.4, label, g["SIZE"]["note"], color="muted")


@case("metrics は主役があるので咎めない", forbid=["EQUAL_EMPHASIS"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "解約率の低下が最も効いた")
    g["metrics"](s, g["M"], g["BODY_Y"], g["W"] - 2 * g["M"],
                 [("42%", "解約率の低下"), ("18日", "リード短縮"), ("3.1倍", "問合せ増")])


@case("1ページに字種が多すぎると咎める", expect=["TYPE_SIZE_COUNT"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "字の大きさが揃っていないページの主張")
    for i, size in enumerate((36, 30, 24, 20, 16)):
        g["text"](s, g["M"], g["BODY_Y"] + i * 0.7, 9.0, 0.6, "大きさ %dpt の行" % size, size)


@case("字種が4種までなら咎めない", forbid=["TYPE_SIZE_COUNT"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "字の大きさを4種に収めたページの主張")
    for i, size in enumerate((g["SIZE"]["h2"], g["SIZE"]["body"], g["SIZE"]["note"])):
        g["text"](s, g["M"], g["BODY_Y"] + i * 0.8, 9.0, 0.6, "大きさ %dpt の行" % size, size)


@case("濃い面のページが4枚あると咎める", expect=["DARK_PAGE_OVERUSE"])
def _(g, p):
    base(g, p)
    for i in range(4):
        s = g["blank"](p)
        g["rect"](s, 0, 0, g["W"], g["H"], "primary")
        g["text"](s, g["M"], 3.0, 9.0, 1.0, "第%d章 ここから変える" % (i + 1), g["SIZE"]["cover"], color="bg")
    for i in range(4):
        s = g["blank"](p)
        g["page_title"](s, "本文ページ%dの主張をここに書く" % (i + 1))
        g["text"](s, g["M"], g["BODY_Y"], 9.0, 2.0, ["本文の行", "本文の行"], g["SIZE"]["body"])


@case("濃い面が3枚までなら咎めない", forbid=["DARK_PAGE_OVERUSE"])
def _(g, p):
    base(g, p)
    for i in range(3):
        s = g["blank"](p)
        g["rect"](s, 0, 0, g["W"], g["H"], "primary")
        g["text"](s, g["M"], 3.0, 9.0, 1.0, "第%d章 ここから変える" % (i + 1), g["SIZE"]["cover"], color="bg")
    for i in range(4):
        s = g["blank"](p)
        g["page_title"](s, "本文ページ%dの主張をここに書く" % (i + 1))
        g["text"](s, g["M"], g["BODY_Y"], 9.0, 2.0, ["本文の行", "本文の行"], g["SIZE"]["body"])


@case("入れ子の箇条書き", forbid=["TEXT_OVERFLOW_LIKELY"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "対象を3つに絞って進める")
    g["text"](s, g["M"], g["BODY_Y"], 8.0, 3.0,
              ["対象を3つに絞る", "\u3000定型の問い合わせ", "\u3000FAQ で答えられるもの", "期限は12月末"],
              g["SIZE"]["body"], bullets=True)


@case("図形に直接文字を書くと咎める", expect=["SHAPE_TEXT_UNSTYLED"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "図形に直接文字を書いたページの主張")
    shape = g["rect"](s, g["M"], g["BODY_Y"], 3.0, 1.4, "panel")
    shape.text_frame.text = "受付"


@case("box_text なら咎めない", forbid=["SHAPE_TEXT_UNSTYLED", "SHAPE_TEXT_TOP_ANCHORED",
                                       "TEXT_OVERFLOW_LIKELY"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "文字入りの四角を並べたページの主張")
    for i, label in enumerate(["受付", "問い合わせ内容を分類して定型かどうかを判定する",
                               "API /v1/classify で判定"]):
        g["box_text"](s, g["M"] + i * 4.15, g["BODY_Y"], 3.8, 1.6, label)


_LONG = "在庫の滞留は拠点ごとの判断基準の違いから生まれており、輸送能力の不足では説明できない。"


@case("長い文言でも原型が溢れない", forbid=["TEXT_OVERFLOW_LIKELY", "TEXT_OVERLAP",
                                            "TEXT_SHAPE_COLLISION", "FONT_TOO_SMALL"])
def _(g, p):
    base(g, p)
    g["slide_hero_number"](p, "滞留在庫が占める割合", "38.2%",
                           "西日本3拠点の在庫のうち、90日以上まったく動いていないものの割合",
                           [_LONG, _LONG], "出典: 実績")
    g["slide_structure"](p, "拠点の位置づけを二軸で整理する",
                         [("再編対象", _LONG), ("投資対象", _LONG),
                          ("維持", _LONG), ("要観察", _LONG)],
                         ("需要の伸び", "在庫の健全性"), "出典: 整理")
    g["slide_metrics"](p, "見込む効果",
                       [("12.4", "年間の削減見込み額（百万円、保管費と廃棄費の合計）"),
                        ("15%", "滞留在庫比率"), ("3か月", "効果が出るまでの期間")],
                       [_LONG], "出典: 試算")
    g["slide_before_after"](p, "基準を変えると判断が変わる", [_LONG], [_LONG],
                            [_LONG], source="出典: 試算")


@case("折り返す表・時系列・表紙が崩れない", forbid=["TEXT_OVERFLOW_LIKELY", "TEXT_OVERLAP",
                                                  "TEXT_SHAPE_COLLISION"])
def _(g, p):
    base(g, p)
    g["slide_cover"](p, ["物流拠点の再編と在庫配置基準の見直しに関する経営会議への提案"],
                     ["経営企画部 物流戦略チーム", "2026年9月6日", "社外秘"])
    g["slide_table"](p, "拠点別の費用と効果",
                     [["拠点と担当部門", "現状費用", "見込費用", "差分と備考"],
                      ["近畿（西日本統括部が担当）", "42.1", "36.8", "-5.3 保管費の削減が主"],
                      ["中国", "28.4", "25.1", "-3.3"]],
                     [_LONG], [3, 1, 1, 3], "出典: 試算")
    g["slide_roadmap"](p, "再編の行程",
                       [("10月", "滞留在庫の棚卸しと引き当て可否の判定"),
                        ("12月", "近畿拠点で在庫配置の基準を作り直す"),
                        ("2月", "中国・九州の2拠点へ展開する")],
                       [_LONG], "出典: 計画")


@case("淡い面の上の薄い文字を咎める", expect=["TEXT_CONTRAST_LOW"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "淡い面の上に薄い文字を置いたページの主張")
    g["rect"](s, g["M"], g["BODY_Y"], 6.0, 2.0, "panel")          # 淡い面
    g["text"](s, g["M"] + 0.3, g["BODY_Y"] + 0.3, 5.4, 1.4,
              ["この行は淡い面の上に罫線色で置かれていて読めない。"],
              g["SIZE"]["body"], color="line")                    # 面とほぼ同じ明るさ


@case("本文色と出典色は咎めない", forbid=["TEXT_CONTRAST_LOW"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "地の上に本文色と補助色を置いたページの主張")
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.4, ["本文の色で書いた行。"], g["SIZE"]["body"])
    g["text"](s, g["M"], g["BODY_Y"] + 1.6, 7.0, 0.5, ["補助の色で書いた行。"],
              g["SIZE"]["body"], color="muted")
    g["page_source"](s, "出典: 資料")


@case("写真の上の文字は咎めない（判定できないため）", forbid=["TEXT_CONTRAST_LOW"])
def _(g, p):
    import io
    from PIL import Image
    base(g, p)
    s = g["blank"](p)
    buf = io.BytesIO()
    Image.new("RGB", (600, 400), (120, 120, 120)).save(buf, "PNG")
    buf.seek(0)
    from pptx.util import Inches
    s.shapes.add_picture(buf, Inches(0), Inches(0), Inches(g["W"]), Inches(g["H"]))
    g["scrim"](s, 0, 4.0, g["W"], 3.5)                            # 半透明の面
    g["text"](s, 0.8, 4.6, 8.0, 1.0, ["写真の上に置いた一文。"], g["SIZE"]["h2"], color="bg")


@case("図の注記は枠の外に出る", forbid=["TEXT_SHAPE_COLLISION", "TEXT_OVERLAP",
                                       "TEXT_CONTRAST_LOW", "OUT_OF_CANVAS"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "西日本の3拠点だけが基準を大きく上回るページの主張")
    ex = (g["M"], 2.2, 8.0, 3.6)
    g["chart"](s, ex[0], ex[1], ex[2], ex[3], ["東北", "関東", "中部", "近畿", "中国", "九州"],
               [("在庫回転日数", (16.2, 15.1, 17.8, 24.3, 26.1, 25.4))])
    g["annotate"](s, ex, (7.4, 2.9), "この3拠点が基準の18日を超える")
    g["annotate"](s, ex, (2.2, 5.4), "基準内")
    g["page_source"](s, "出典: 社内WMS")


@case("タイトルを後から置くと咎める", expect=["READING_ORDER_TITLE_LATE"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.4, ["本文の一行目です。"], g["SIZE"]["body"])
    g["text"](s, g["M"], g["BODY_Y"] + 1.6, 7.0, 1.4, ["本文の二行目です。"], g["SIZE"]["body"])
    g["page_title"](s, "本文の後にタイトルを置いたページの主張")   # 重ね順が最後＝読み上げも最後


@case("出典を先に置くと咎める", expect=["READING_ORDER_FOOTER_EARLY"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "出典を先に置いたページの主張")
    g["page_source"](s, "出典: 資料")                              # 本文より先
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.4, ["本文の一行目です。"], g["SIZE"]["body"])


@case("骨格どおりの順序は咎めない",
      forbid=["READING_ORDER_TITLE_LATE", "READING_ORDER_FOOTER_EARLY"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "骨格の順序どおりに置いたページの主張")
    g["text"](s, g["M"], g["BODY_Y"], 7.0, 1.4, ["本文の一行目です。"], g["SIZE"]["body"])
    g["text"](s, g["M"], g["BODY_Y"] + 1.6, 7.0, 1.4, ["本文の二行目です。"], g["SIZE"]["body"])
    g["page_source"](s, "出典: 資料")


@case("順序の無い棒が値順でないと咎める", expect=["CHART_BARS_UNSORTED"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "拠点別の在庫回転日数を比べたページの主張")
    g["chart"](s, g["M"], g["BODY_Y"], 8.0, 3.0, ["東北", "関東", "中部", "近畿", "中国"],
               [("回転日数", (16.2, 24.3, 17.8, 26.1, 15.1))])


@case("値順に並んだ棒は咎めない", forbid=["CHART_BARS_UNSORTED"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "拠点別の在庫回転日数を大きい順に並べたページの主張")
    g["chart"](s, g["M"], g["BODY_Y"], 8.0, 3.0, ["中国", "近畿", "中部", "東北", "関東"],
               [("回転日数", (26.1, 24.3, 17.8, 16.2, 15.1))])


@case("円が6区分以上だと咎める", expect=["CHART_PIE_TOO_MANY"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "内訳を円で示したページの主張")
    g["chart"](s, g["M"], g["BODY_Y"], 6.0, 3.5, ["A", "B", "C", "D", "E", "F"],
               [("構成比", (30.0, 25.0, 15.0, 12.0, 10.0, 8.0))], kind="pie")


@case("系列が5本以上だと咎める", expect=["CHART_TOO_MANY_SERIES"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "系列を多く重ねたページの主張")
    g["chart"](s, g["M"], g["BODY_Y"], 8.0, 3.0, ["1月", "2月", "3月"],
               [("系列%d" % i, (1.0 + i, 2.0 + i, 3.0 + i)) for i in range(5)], kind="line")


@case("代替テキストの無い図表を咎める", expect=["ALT_TEXT_MISSING"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "図表に代替テキストを付けていないページの主張")
    g["chart"](s, g["M"], g["BODY_Y"], 7.0, 3.0, ["近畿", "中国"], [("回転日数", (24.3, 26.1))])


@case("種類しか言わない代替テキストを咎める", expect=["ALT_TEXT_USELESS"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "代替テキストが種類だけのページの主張")
    ch = g["chart"](s, g["M"], g["BODY_Y"], 7.0, 3.0, ["近畿", "中国"], [("回転日数", (24.3, 26.1))])
    g["describe"](next(sh for sh in s.shapes if sh.has_chart), "グラフ")


@case("中身を言う代替テキストは咎めない", forbid=["ALT_TEXT_MISSING", "ALT_TEXT_USELESS"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "代替テキストに中身を書いたページの主張")
    g["chart"](s, g["M"], g["BODY_Y"], 7.0, 3.0, ["近畿", "中国"], [("回転日数", (24.3, 26.1))])
    g["describe"](next(sh for sh in s.shapes if sh.has_chart),
                  "拠点別の在庫回転日数。近畿も中国も基準の18日を超える")


@case("座標で線を引くと咎める", expect=["CONNECTOR_DIAGONAL"])
def _(g, p):
    from pptx.util import Inches
    from pptx.enum.shapes import MSO_CONNECTOR
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "斜めの線で結んだページの主張")
    a = g["box_text"](s, g["M"], 2.4, 3.0, 1.2, "受付")
    b = g["box_text"](s, 5.4, 4.2, 3.0, 1.2, "判定")
    s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, a.left + a.width, a.top + a.height // 2,
                           b.left, b.top + b.height // 2)


@case("connect なら咎めない", forbid=["CONNECTOR_DIAGONAL", "CONNECTOR_DETACHED"])
def _(g, p):
    base(g, p)
    s = g["blank"](p)
    g["page_title"](s, "図形を線で結んだページの主張")
    a = g["box_text"](s, g["M"], 2.4, 3.0, 1.2, "受付")
    b = g["box_text"](s, 5.4, 4.2, 3.0, 1.2, "判定")
    c = g["box_text"](s, 9.6, 2.4, 3.0, 1.2, "応答")
    g["connect"](s, a, b)
    g["connect"](s, b, c)


def main():
    workdir = tempfile.mkdtemp(prefix="pptx-eval-")
    deck_dir = os.path.join(workdir, "deck")
    os.makedirs(deck_dir, exist_ok=True)
    with open(os.path.join(deck_dir, "design-lock.json"), "w", encoding="utf-8") as fh:
        json.dump(LOCK, fh, ensure_ascii=False)
    allow_lock = os.path.join(deck_dir, "allow-lock.json")
    with open(allow_lock, "w", encoding="utf-8") as fh:
        json.dump(
            dict(
                LOCK,
                colors=["222222"],
                allow=[{"code": "PALETTE_DRIFT", "reason": "意図的"}],
            ),
            fh,
            ensure_ascii=False,
        )

    ok = failures = 0
    palette_scope = env(workdir)
    if (
        palette_scope["C"] == TEST_PALETTE
        and "22313F" not in palette_scope["C"].values()
    ):
        ok += 1
        print("ok  デザインロックの役割付きpaletteを生成骨格が使う")
    else:
        failures += 1
        print("NG  デザインロックの役割付きpaletteを生成骨格が使う")

    legacy_colors = ["FFFFFF", "222222", "666666", "DDDDDD", "F5F5F5", "123456", "CC5500"]
    with open(os.path.join(deck_dir, "design-lock.json"), "w", encoding="utf-8") as fh:
        json.dump({"fonts": ["Yu Gothic"], "colors": legacy_colors}, fh)
    legacy_scope = env(workdir)
    expected_legacy = dict(zip(legacy_scope["PALETTE_ROLES"], legacy_colors))
    if legacy_scope["C"] == expected_legacy:
        ok += 1
        print("ok  旧colors形式のデザインロックを互換読み込み")
    else:
        failures += 1
        print("NG  旧colors形式のデザインロックを互換読み込み")
    with open(os.path.join(deck_dir, "design-lock.json"), "w", encoding="utf-8") as fh:
        json.dump(LOCK, fh, ensure_ascii=False)

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

    # 行送りは実寸(spcPts)で書き出す。倍率(spcPct)だと見る側の書体で高さが変わり、
    # こちらの高さ計算とも合わなくなる。
    from pptx.oxml.ns import qn as _qn
    scope = env(workdir)
    spacing_prs = scope["new_deck"]()
    spacing_slide = scope["blank"](spacing_prs)
    scope["page_title"](spacing_slide, "行送りの書き出しを確かめるページの主張")
    ppr = spacing_slide.shapes[0].text_frame.paragraphs[0]._p.find(_qn("a:pPr"))
    if (ppr is not None
            and ppr.find(_qn("a:lnSpc") + "/" + _qn("a:spcPts")) is not None
            and ppr.find(_qn("a:lnSpc") + "/" + _qn("a:spcPct")) is None):
        ok += 1
        print("ok  行送りを実寸で書き出す")
    else:
        failures += 1
        print("NG  行送りを実寸で書き出す")

    # 原型の升目より多く渡したとき、黙って捨てない。
    steps_prs = scope["new_deck"]()
    steps_slide = scope["slide_steps"](steps_prs, "5つの手順を渡しても消えない",
                                       [(str(i + 1), "%d月" % (i + 1), "手順 %d の内容" % (i + 1))
                                        for i in range(5)])
    texts = [sh.text_frame.text for sh in steps_slide.shapes if sh.has_text_frame]
    dropped = []
    for extra in (("見出し", lambda: scope["slide_comparison"](
                       steps_prs, "3列渡す", ["A", "B", "C"], [["a"], ["b"], ["c"]])),
                  ("象限", lambda: scope["slide_structure"](
                       steps_prs, "5象限渡す", [("見出し", "説明")] * 5))):
        try:
            extra[1]()
            dropped.append(extra[0])
        except ValueError:
            pass
    if "5" in texts and "手順 5 の内容" in texts and not dropped:
        ok += 1
        print("ok  升目より多い中身を黙って捨てない")
    else:
        failures += 1
        print("NG  升目より多い中身を黙って捨てない（捨てた: %s）" % (dropped or "-"))

    # 入らない文言は、溢れたまま書き出さずに止める。
    over = _LONG * 4
    stop_prs = scope["new_deck"]()
    stop_slide = scope["blank"](stop_prs)
    stopped = 0
    for build in (lambda: scope["slide_structure"](stop_prs, "入らない二軸",
                                                   [("見出し", over)] * 4),
                  lambda: scope["place"](stop_slide, [over], scope["M"], 5.6, 9.0),
                  lambda: scope["slide_table"](stop_prs, "行が多すぎる表",
                                               [["列"]] + [[over]] * 6)):
        try:
            build()
        except ValueError:
            stopped += 1
    if stopped == 3:
        ok += 1
        print("ok  収まらない文言は黙って溢れさせずに止める")
    else:
        failures += 1
        print("NG  収まらない文言は黙って溢れさせずに止める（止まった: %d/3）" % stopped)

    # 素材の正規化: 置く前に回転・色空間・画素数を揃える。python-pptx は素材の
    # バイト列をそのまま埋めるので、ここを飛ばすと横倒しの写真や CMYK が受け手に渡る。
    try:
        from PIL import Image, ImageOps  # noqa: F401
        import io as _io
        scope = env(workdir)
        mat = pathlib.Path(workdir) / "mat"
        mat.mkdir(exist_ok=True)
        rotated, cmyk = str(mat / "rot.jpg"), str(mat / "cmyk.jpg")
        big = Image.new("RGB", (4000, 3000), (200, 80, 40))
        exif = big.getexif()
        exif[274] = 6                                  # Orientation = 90度回転
        big.save(rotated, exif=exif, dpi=(300, 300))
        Image.new("CMYK", (800, 600), (0, 120, 200, 10)).save(cmyk)
        before = set(os.listdir(str(mat)))
        pic_prs = scope["new_deck"]()
        pic_slide = scope["blank"](pic_prs)
        scope["picture"](pic_slide, rotated, 0.6, 0.6, 3.0, 4.0)
        scope["picture"](pic_slide, cmyk, 5.0, 0.6, 4.0, 3.0)
        out_pptx = str(mat / "pics.pptx")
        pic_prs.save(out_pptx)
        embedded = []
        with zipfile.ZipFile(out_pptx) as z:
            for name in sorted(n for n in z.namelist() if n.startswith("ppt/media")):
                with Image.open(_io.BytesIO(z.read(name))) as im:
                    embedded.append((im.size, im.mode))
        leftovers = set(os.listdir(str(mat))) - before - {"pics.pptx"}
        normalized = (embedded == [((1800, 2400), "RGB"), ((800, 600), "RGB")]
                      and not leftovers)
    except Exception:
        normalized = False
    if normalized:
        ok += 1
        print("ok  写真は回転・色空間・画素数を揃えてから埋め込む")
    else:
        failures += 1
        print("NG  写真は回転・色空間・画素数を揃えてから埋め込む")

    # 線を明示的に消した図形に、描画が枠を足さない。足すと、コードから枠を消しても
    # 描画画像に残り、消えない枠を追いかけることになる。
    try:
        from PIL import Image
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.dml.color import RGBColor
        from pptx.util import Inches, Pt
        scope = env(workdir)
        bd_prs = scope["new_deck"]()
        bd = scope["blank"](bd_prs)
        scope["rect"](bd, 0, 0, scope["W"], scope["H"], "bg")
        geoms = (MSO_SHAPE.RECTANGLE, MSO_SHAPE.ROUNDED_RECTANGLE, MSO_SHAPE.RIGHT_ARROW,
                 MSO_SHAPE.CHEVRON, MSO_SHAPE.OVAL, MSO_SHAPE.SNIP_1_RECTANGLE)
        for i, kind in enumerate(geoms):                 # 塗りあり・線は明示的に消す
            sh = bd.shapes.add_shape(kind, Inches(0.6 + i * 2.1), Inches(2.0),
                                     Inches(1.8), Inches(1.2))
            sh.fill.solid()
            sh.fill.fore_color.rgb = RGBColor.from_string(TEST_PALETTE["panel"])
            sh.line.fill.background()
            sh.shadow.inherit = False
        lined = bd.shapes.add_shape(MSO_SHAPE.CHEVRON, Inches(0.6), Inches(4.0),
                                    Inches(1.8), Inches(1.2))
        lined.fill.solid()
        lined.fill.fore_color.rgb = RGBColor.from_string(TEST_PALETTE["panel"])
        lined.line.color.rgb = RGBColor.from_string(TEST_PALETTE["accent"])
        lined.line.width = Pt(2)
        lined.shadow.inherit = False
        bd_path = os.path.join(workdir, "borders.pptx")
        bd_prs.save(bd_path)
        render = ROOT / "pptx-review" / "scripts" / "render_preview.py"
        subprocess.run([sys.executable, str(render), bd_path,
                        "--out", os.path.join(workdir, "bd")], capture_output=True, check=True)
        img = Image.open(os.path.join(workdir, "bd-01.png")).convert("RGB")
        sx, sy = img.width / scope["W"], img.height / scope["H"]
        panel = tuple(int(TEST_PALETTE["panel"][i:i + 2], 16) for i in (0, 2, 4))
        accent = tuple(int(TEST_PALETTE["accent"][i:i + 2], 16) for i in (0, 2, 4))
        edges = [img.getpixel((int(round((0.6 + i * 2.1 + 0.9) * sx)), int(round(2.0 * sy))))
                 for i in range(len(geoms))]
        kept = img.getpixel((int(round(1.5 * sx)), int(round(4.0 * sy))))
        borders_ok = all(e == panel for e in edges) and kept == accent
    except Exception:
        borders_ok = False
    if borders_ok:
        ok += 1
        print("ok  線を消した図形に描画が枠を足さない（ある線は描く）")
    else:
        failures += 1
        print("NG  線を消した図形に描画が枠を足さない（ある線は描く）")

    # 構成の検査: 生成する前に、書いたか／選んだかを機械で見る。
    check_outline = ROOT / "pptx-create" / "scripts" / "check_outline.py"
    good = {"pages": [
        {"n": 1, "role": "表紙", "title": "拠点再編の提案", "archetype": "cover", "density": "low"},
        {"n": 2, "role": "結論", "title": "西日本の遅延は在庫の偏りが原因である",
         "archetype": "claim-evidence", "exhibit": "chart:bar", "evidence": "社内WMS",
         "density": "high", "candidates": ["claim-evidence", "comparison"],
         "chosen_because": "軸が1つなので棒"},
        {"n": 3, "role": "行動", "title": "10月から棚卸しに着手したい", "archetype": "closing",
         "density": "mid", "candidates": ["closing", "steps"], "chosen_because": "順序が無い"}]}
    bad = {"pages": [
        {"n": 1, "role": "本文", "title": "まとめ", "archetype": "claim-evidence",
         "exhibit": "38.2%の削減", "density": "high",
         "candidates": ["claim-evidence"], "chosen_because": ""},
        {"n": 2, "role": "本文", "title": "二つ目の主張を一文で書いた行",
         "archetype": "bento-grid", "density": "high",
         "candidates": ["a", "b"], "chosen_because": "見栄えがよい"},
        {"n": 3, "role": "本文", "title": "三つ目の主張を一文で書いた行",
         "archetype": "comparison", "density": "high",
         "candidates": ["comparison", "table"], "chosen_because": "軸が1つ"},
        {"n": 4, "role": "本文", "title": "四つ目の主張を一文で書いた行",
         "archetype": "table", "density": "high",
         "candidates": ["table", "trend"], "chosen_because": "値を照合させる"}]}
    grammar_lock = dict(LOCK, grammar={"id": "answer-led", "arc": ["結論", "証拠", "行動"],
                                       "escalate": ["CARD_ROW"]})
    paths = {}
    for name, payload in (("good", good), ("bad", bad), ("glock", grammar_lock)):
        paths[name] = os.path.join(workdir, name + ".json")
        with open(paths[name], "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
    r_good = subprocess.run([sys.executable, str(check_outline), paths["good"],
                             "--lock", paths["glock"]], capture_output=True, text=True)
    r_bad = subprocess.run([sys.executable, str(check_outline), paths["bad"],
                            "--lock", paths["glock"]], capture_output=True, text=True)
    bad_out = r_bad.stdout + r_bad.stderr
    outline_ok = (
        r_good.returncode == 0
        and r_bad.returncode == 1
        and "話題ラベル" in bad_out           # まとめ
        and "候補が 1 個" in bad_out          # 候補が足りない
        and "決め手が空" in bad_out           # 理由が無い
        and "骨格に無い" in bad_out           # bento-grid
        and "密度が全ページ" in bad_out       # 密度が一様
        and "文法 answer-led" in bad_out      # 読みの筋が結論から始まっていない
    )
    if outline_ok:
        ok += 1
        print("ok  構成の欠落を生成前に拾う")
    else:
        failures += 1
        print("NG  構成の欠落を生成前に拾う（good=%d bad=%d）" % (r_good.returncode, r_bad.returncode))

    # 注記が図の外に置けないときは、黙って重ねずに止まる。
    scope = env(workdir)
    anno_prs = scope["new_deck"]()
    anno_slide = scope["blank"](anno_prs)
    tight = (scope["M"], scope["BODY_Y"], scope["W"] - 2 * scope["M"],
             scope["BODY_END"] - scope["BODY_Y"])          # 本文領域いっぱいの図
    try:
        scope["annotate"](anno_slide, tight, (6.0, 4.0), "外に出す余地が無い注記")
        anno_stops = False
    except ValueError:
        anno_stops = True
    if anno_stops:
        ok += 1
        print("ok  注記を図の外に置けなければ止まる")
    else:
        failures += 1
        print("NG  注記を図の外に置けなければ止まる")

    # 折り返しの数え方: 骨格・lint・描画の三者が同じ行数を出す。
    # 割り算（全幅÷行幅）は行末の余りを数え落とし、実際より少なく出る。
    scope = env(workdir)
    wrap_ok = True
    detail = []
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "pptx-review" / "scripts"))
        lint_mod = importlib.import_module("pptx_lint")
        importlib.reload(lint_mod)
        for text, w, size in (
                ("「基準を変える」という判断には、営業部門の合意が要る。合意が取れない場合、効果は半減する。", 2.5, 16),
                ("季節品の入れ替え時期に旧品の引き取り先が決まらないまま新品が入ってくるため、在庫は増える。", 5.0, 16),
                ("在庫の滞留は拠点ごとの判断基準の違いから生まれており、輸送能力の不足では説明できない。", 3.3, 16)):
            plain = max(1, int(math.ceil(scope["text_width"](text, size) / (w * 72.0))))
            skeleton_n = scope["wrapped_lines"](text, w, size)
            lint_n = lint_mod.wrap_count(text, w * 72.0, size)
            detail.append((plain, skeleton_n, lint_n))
            if skeleton_n != lint_n or skeleton_n <= plain:
                wrap_ok = False
        # 禁則: 行頭に置けない文字は追い出す（行が増える側）
        if scope["wrapped_lines"]("あああああ、", 1.0, 72) < 2:
            wrap_ok = False
    except Exception:
        wrap_ok = False
    if wrap_ok:
        ok += 1
        print("ok  折り返しは実際に数え、骨格と lint が一致する")
    else:
        failures += 1
        print("NG  折り返しは実際に数え、骨格と lint が一致する（%s）" % detail)

    # 文法の禁じ手は重大度が上がる（allow の逆）。
    esc_prs = scope["new_deck"]()
    for i in range(5):
        sl = scope["blank"](esc_prs)
        scope["page_title"](sl, "揃ったページ %d の主張を一文で書いたタイトル" % (i + 1))
        scope["text"](sl, scope["M"], scope["BODY_Y"], 7.0, 1.4, ["本文の行。"], scope["SIZE"]["body"])
    card = scope["blank"](esc_prs)
    scope["page_title"](card, "同型のカードを3枚横に並べたページの主張")
    for i in range(3):
        scope["box_text"](card, scope["M"] + i * 4.15, scope["BODY_Y"], 3.8, 1.6,
                          "項目 %d" % (i + 1), fill="panel", rounded=True)
    esc_path = os.path.join(workdir, "escalate.pptx")
    esc_prs.save(esc_path)
    sev = {}
    for tag, lock_path in (("plain", None), ("grammar", paths["glock"])):
        out = os.path.join(workdir, "esc-%s.json" % tag)
        cmd = [sys.executable, str(LINT), esc_path, "--json-out", out]
        if lock_path:
            cmd += ["--lock", lock_path]
        subprocess.run(cmd, capture_output=True)
        report = json.load(open(out, encoding="utf-8"))
        sev[tag] = [f["severity"] for s_ in report["slides"] for f in s_["findings"]
                    if f["code"] == "CARD_ROW"]
    escalate_ok = sev.get("plain") == ["info"] and sev.get("grammar") == ["warning"]
    if escalate_ok:
        ok += 1
        print("ok  文法の禁じ手は重大度が上がる")
    else:
        failures += 1
        print("NG  文法の禁じ手は重大度が上がる（%s）" % sev)

    # 署名の候補: 当たれば出し、弱ければ何も出さない（無理に当てはめない）。
    motif = ROOT / "pptx-design" / "scripts" / "suggest_motif.py"
    hit = subprocess.run([sys.executable, str(motif), "--json",
                          "夜間物流の管制画面。遅延を検知して運用で捌く"],
                         capture_output=True, text=True)
    miss = subprocess.run([sys.executable, str(motif), "--json", "新しい人事制度の説明"],
                          capture_output=True, text=True)
    try:
        hit_names = [c["name"] for c in json.loads(hit.stdout)["candidates"]]
        miss_names = [c["name"] for c in json.loads(miss.stdout)["candidates"]]
        motif_ok = (hit.returncode == 0 and "計器" in hit_names
                    and miss.returncode == 1 and miss_names == [])
    except (ValueError, KeyError):
        motif_ok = False
    # 語彙を増やしたときに、主題性の薄い文へ誤って当たらないこと
    neutral_hits = 0
    for text in ("新しい人事制度の説明", "会社のミッションと価値観", "来期の組織体制",
                 "福利厚生の見直し", "オフィス移転のお知らせ"):
        r = subprocess.run([sys.executable, str(motif), "--json", text],
                           capture_output=True, text=True)
        try:
            neutral_hits += len(json.loads(r.stdout)["candidates"])
        except ValueError:
            neutral_hits += 99
    motif_ok = motif_ok and neutral_hits == 0
    if motif_ok:
        ok += 1
        print("ok  署名の候補は当たれば出し、弱ければ出さない")
    else:
        failures += 1
        print("NG  署名の候補は当たれば出し、弱ければ出さない")

    # フッター行の3つの持ち場は重ならない（出典・章名/付録の印・ページ番号）。
    foot = scope["FOOT"]
    if (foot["source"][0] + foot["source"][1] <= foot["section"][0] + 1e-6
            and foot["section"][0] + foot["section"][1] <= foot["page"][0] + 1e-6):
        ok += 1
        print("ok  フッター行の持ち場が重ならない")
    else:
        failures += 1
        print("NG  フッター行の持ち場が重ならない")

    # 出力先はスキルの手順どおり、事前作成なしでも書き出せる。
    sample = os.path.join(workdir, "case-00.pptx")
    nested_lock = os.path.join(workdir, "nested", "qa", "lock.json")
    nested_lint = os.path.join(workdir, "nested", "report", "lint.json")
    extract = ROOT / "pptx-review" / "scripts" / "extract_style.py"
    r1 = subprocess.run([sys.executable, str(extract), sample, "--json-out", nested_lock],
                        capture_output=True, text=True)
    r2 = subprocess.run([sys.executable, str(LINT), sample, "--json-out", nested_lint],
                        capture_output=True, text=True)
    if (r1.returncode == 0 and r2.returncode < 2
            and os.path.exists(nested_lock) and os.path.exists(nested_lint)):
        ok += 1
        print("ok  出力先ディレクトリの自動作成")
    else:
        failures += 1
        print("NG  出力先ディレクトリの自動作成")

    # タイトルを編集しても、同じページ・図形の既存指摘はbaselineとして残る。
    baseline = os.path.join(workdir, "baseline.json")
    changed = os.path.join(workdir, "baseline-title-changed.pptx")
    subprocess.run([sys.executable, str(LINT), sample, "--json-out", baseline], capture_output=True)
    from pptx import Presentation
    changed_prs = Presentation(sample)
    title_shape = next(
        sh for sh in changed_prs.slides[2].shapes
        if sh.has_text_frame and sh.text.strip()
    )
    title_shape.text_frame.paragraphs[0].runs[0].text = "変更後のタイトル"
    changed_prs.save(changed)
    changed_report = os.path.join(workdir, "baseline-title-changed.json")
    subprocess.run([sys.executable, str(LINT), changed, "--baseline", baseline,
                    "--json-out", changed_report], capture_output=True)
    report = json.load(open(changed_report, encoding="utf-8"))
    inherited = [f for f in report["slides"][2]["findings"]
                 if f["code"] == "LAYOUT_REPEATED" and f.get("baseline")]
    if inherited:
        ok += 1
        print("ok  タイトル変更後のbaseline照合")
    else:
        failures += 1
        print("NG  タイトル変更後のbaseline照合")

    # 並べ替え後に同じページ番号・図形名へ出た新規指摘を、既存扱いしない。
    scope = env(workdir)
    reorder_prs = scope["new_deck"]()
    for title, body in (("ページAの主張", "🚀 既存の指摘"),
                        ("ページBの主張", "通常の本文")):
        slide = scope["blank"](reorder_prs)
        scope["page_title"](slide, title)
        scope["text"](slide, scope["M"], scope["BODY_Y"], 7.0, 1.0,
                      body, scope["SIZE"]["body"])
    reorder_before = os.path.join(workdir, "reorder-before.pptx")
    reorder_prs.save(reorder_before)
    reorder_baseline = os.path.join(workdir, "reorder-baseline.json")
    subprocess.run([sys.executable, str(LINT), reorder_before,
                    "--json-out", reorder_baseline], capture_output=True)

    reordered = Presentation(reorder_before)
    body_a = next(sh for sh in reordered.slides[0].shapes
                  if sh.has_text_frame and "既存の指摘" in sh.text)
    body_b = next(sh for sh in reordered.slides[1].shapes
                  if sh.has_text_frame and "通常の本文" in sh.text)
    body_a.text_frame.paragraphs[0].runs[0].text = "通常の本文"
    body_b.text_frame.paragraphs[0].runs[0].text = "🚀 新しい指摘"
    reordered.slides._sldIdLst.insert(0, reordered.slides._sldIdLst[-1])
    reorder_after = os.path.join(workdir, "reorder-after.pptx")
    reordered.save(reorder_after)
    reorder_report_path = os.path.join(workdir, "reorder-after.json")
    subprocess.run([sys.executable, str(LINT), reorder_after,
                    "--baseline", reorder_baseline, "--json-out", reorder_report_path],
                   capture_output=True)
    reorder_report = json.load(open(reorder_report_path, encoding="utf-8"))
    new_emoji = [f for f in reorder_report["slides"][0]["findings"]
                 if f["code"] == "EMOJI" and not f.get("baseline")]
    if new_emoji:
        ok += 1
        print("ok  並べ替え後の新規指摘をbaseline扱いしない")
    else:
        failures += 1
        print("NG  並べ替え後の新規指摘をbaseline扱いしない")

    # 理由の無いallowは指摘を無効化できない。
    invalid_lock = os.path.join(workdir, "allow-without-reason.json")
    with open(invalid_lock, "w", encoding="utf-8") as fh:
        json.dump(dict(LOCK, allow=[{"code": "PALETTE_DRIFT"}]), fh, ensure_ascii=False)
    r3 = subprocess.run([sys.executable, str(LINT), sample, "--lock", invalid_lock],
                        capture_output=True, text=True)
    if r3.returncode == 2 and "non-empty reason" in r3.stderr:
        ok += 1
        print("ok  理由の無いallowを拒否")
    else:
        failures += 1
        print("NG  理由の無いallowを拒否")

    invalid_palette = os.path.join(workdir, "palette-without-basis.json")
    missing_basis = dict(LOCK)
    missing_basis.pop("palette_basis")
    with open(invalid_palette, "w", encoding="utf-8") as fh:
        json.dump(missing_basis, fh)
    r4 = subprocess.run(
        [sys.executable, str(LINT), sample, "--lock", invalid_palette],
        capture_output=True,
        text=True,
    )
    if r4.returncode == 2 and "palette_basis" in r4.stderr:
        ok += 1
        print("ok  根拠の無いpaletteを拒否")
    else:
        failures += 1
        print("NG  根拠の無いpaletteを拒否")

    intent_path = pathlib.Path(workdir) / "palette-intent.json"
    candidates_path = pathlib.Path(workdir) / "palette-candidates.json"
    preview_path = pathlib.Path(workdir) / "palette-candidates.pptx"
    generated_lock_path = pathlib.Path(workdir) / "generated-design-lock.json"
    intent = {
        "basis": "医療機器の白い筐体と状態表示。強調色は要対応を示す",
        "surface": "light",
        "accent_meaning": "要対応",
        "anchor_color": "167C80",
        "fonts": ["Yu Gothic"],
        "min_font_pt": 12,
    }
    intent_path.write_text(json.dumps(intent, ensure_ascii=False), encoding="utf-8")
    palette_run = subprocess.run(
        [
            sys.executable, str(PALETTE_SCRIPT), str(intent_path),
            "--candidates-out", str(candidates_path),
            "--preview-pptx", str(preview_path),
            "--select", "auto", "--lock-out", str(generated_lock_path),
        ],
        capture_output=True,
        text=True,
    )
    brand_intent_path = pathlib.Path(workdir) / "brand-palette-intent.json"
    brand_intent_path.write_text(
        json.dumps({
            "basis": "利用者指定のブランド色を主色として保持する",
            "surface": "light",
            "brand_colors": ["167C80"],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    brand_run = subprocess.run(
        [sys.executable, str(PALETTE_SCRIPT), str(brand_intent_path)],
        capture_output=True,
        text=True,
    )
    try:
        generated = json.loads(candidates_path.read_text(encoding="utf-8"))
        generated_lock = json.loads(generated_lock_path.read_text(encoding="utf-8"))
        brand_generated = json.loads(brand_run.stdout)
        from pptx import Presentation
        preview_slides = len(Presentation(str(preview_path)).slides)
        accents = {c["palette"]["accent"] for c in generated["candidates"]}
        primaries = {c["palette"]["primary"] for c in generated["candidates"]}
        checks_pass = all(
            c["checks"]["text_contrast"] >= 4.5
            and c["checks"]["muted_contrast"] >= 4.5
            and c["checks"]["primary_contrast"] >= 3.0
            and c["checks"]["accent_contrast"] >= 3.0
            and c["checks"]["color_vision_distance"] >= 45
            for c in generated["candidates"]
        )
        palette_ok = (
            palette_run.returncode == 0
            and len(generated["candidates"]) == 3
            and len(accents) == 3
            and len(primaries) == 3
            and preview_slides == 6
            and set(generated_lock["palette"]) == set(TEST_PALETTE)
            and len(generated_lock["chart_series"]) == 4
            and brand_run.returncode == 0
            and all(
                c["palette"]["primary"] == "167C80"
                for c in brand_generated["candidates"]
            )
            and checks_pass
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        palette_ok = False
    if palette_ok:
        ok += 1
        print("ok  高度デザイン用paletteを3案と比較PPTXへ自動生成")
    else:
        failures += 1
        print("NG  高度デザイン用paletteを3案と比較PPTXへ自動生成")

    invalid_intent = pathlib.Path(workdir) / "palette-intent-without-anchor.json"
    invalid_intent.write_text(
        json.dumps({"basis": "基準色のない主題", "surface": "light"}),
        encoding="utf-8",
    )
    missing_anchor = subprocess.run(
        [sys.executable, str(PALETTE_SCRIPT), str(invalid_intent)],
        capture_output=True,
        text=True,
    )
    overwrite = subprocess.run(
        [sys.executable, str(PALETTE_SCRIPT), str(intent_path),
         "--candidates-out", str(candidates_path)],
        capture_output=True,
        text=True,
    )
    if (
        missing_anchor.returncode == 2
        and "requires brand_colors" in missing_anchor.stderr
        and overwrite.returncode == 2
        and "output exists" in overwrite.stderr
    ):
        ok += 1
        print("ok  palette自動生成は基準色不足と既存出力の上書きを拒否")
    else:
        failures += 1
        print("NG  palette自動生成は基準色不足と既存出力の上書きを拒否")

    print("\n%d/%d 合格" % (ok, ok + failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
