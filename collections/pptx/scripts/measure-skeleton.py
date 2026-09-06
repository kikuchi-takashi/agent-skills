#!/usr/bin/env python3
"""骨格が何を防いでいるかを測る。リポジトリ保守用（配布物ではない）。

これまでの根拠は「lint が通る」だけで、**骨格を使わない場合と比べていない**。
同じ内容を「骨格で組んだ版」と「素の python-pptx で組んだ版」で作り、
lint の指摘数と描画のはみ出し数を比べる。

    python3 collections/pptx/scripts/measure-skeleton.py

人手の採点は入れない。ここで言えるのは「骨格が機械的に検出できる欠陥を
どれだけ減らすか」だけであり、**デッキが良いかどうかは測っていない**。
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
RENDER = ROOT / "pptx-review" / "scripts" / "render_preview.py"
ENGINE = ROOT / "pptx-create" / "references" / "engine-notes.md"
LOCK = {"fonts": ["Yu Gothic"], "palette_basis": "測定用",
        "palette": {"bg": "FFFFFF", "text": "1A1A1A", "muted": "5C5C5C", "line": "D9D9D6",
                    "panel": "F4F4F2", "primary": "1F2A44", "accent": "E86A1F"}}

# 同じ内容。骨格版と素版で、この文言をそのまま使う。
TITLE = "西日本の配送遅延は在庫の偏りが原因である"
BODY = ["拠点別の在庫回転日数を見ると、西日本の3拠点だけが基準の18日を大きく上回る。",
        "遅延の申告件数は在庫回転日数と強く相関しており、輸送能力の不足では説明できない。",
        "したがって、輸送便を増やす前に在庫配置を直す必要がある。"]
CATS = ["東北", "関東", "中部", "近畿", "中国", "九州"]
VALS = (16.2, 15.1, 17.8, 24.3, 26.1, 25.4)
SOURCE = "出典: 社内WMS 2026年4-8月の実績"


def skeleton_scope(workdir):
    deck = pathlib.Path(workdir) / "deck"
    deck.mkdir(parents=True, exist_ok=True)
    (deck / "design-lock.json").write_text(json.dumps(LOCK, ensure_ascii=False), encoding="utf-8")
    block = re.search(r"```python\n(.*?)```", ENGINE.read_text(encoding="utf-8"), re.S).group(1)
    block = block.replace('if __name__ == "__main__":\n    build()', "")
    scope, cwd = {}, os.getcwd()
    os.chdir(workdir)
    try:
        exec(compile(block, "skeleton", "exec"), scope)
    finally:
        os.chdir(cwd)
    return scope


def build_with_skeleton(scope, path):
    prs = scope["new_deck"]()
    for i in range(4):
        s = scope["blank"](prs)
        scope["page_title"](s, "%s（%d）" % (TITLE, i + 1))
        scope["place"](s, BODY, scope["M"], scope["BODY_Y"], 7.0)
        scope["page_source"](s, SOURCE)
    s = scope["blank"](prs)
    scope["slide_claim_evidence"](prs, TITLE, BODY, SOURCE,
                                  lambda sl, x, y, w, h: scope["chart"](
                                      sl, x, y, w, h, CATS, [("在庫回転日数", VALS)]))
    prs.save(path)


def build_plain(path):
    """素の python-pptx。座標も高さも手で置き、既定の書式に任せる。
    「骨格を使わないとこうなる」を再現するのが目的で、下手に書いてはいない。"""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    for i in range(4):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        t = s.shapes.add_textbox(Inches(0.6), Inches(0.6), Inches(12.1), Inches(1.0))
        t.text_frame.text = "%s（%d）" % (TITLE, i + 1)
        t.text_frame.paragraphs[0].runs[0].font.size = Pt(28)
        t.text_frame.paragraphs[0].runs[0].font.bold = True
        b = s.shapes.add_textbox(Inches(0.6), Inches(2.2), Inches(7.0), Inches(1.4))
        b.text_frame.word_wrap = True
        for j, line in enumerate(BODY):
            para = b.text_frame.paragraphs[0] if j == 0 else b.text_frame.add_paragraph()
            run = para.add_run()
            run.text = line
            run.font.size = Pt(16)
        f = s.shapes.add_textbox(Inches(0.6), Inches(6.8), Inches(9.0), Inches(0.35))
        f.text_frame.text = SOURCE
        f.text_frame.paragraphs[0].runs[0].font.size = Pt(10)
    s = prs.slides.add_slide(prs.slide_layouts[6])
    t = s.shapes.add_textbox(Inches(0.6), Inches(0.6), Inches(12.1), Inches(1.0))
    t.text_frame.text = TITLE
    t.text_frame.paragraphs[0].runs[0].font.size = Pt(28)
    data = CategoryChartData()
    data.categories = CATS
    data.add_series("在庫回転日数", VALS)
    s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.6), Inches(2.2),
                       Inches(7.0), Inches(4.0), data)
    b = s.shapes.add_textbox(Inches(8.0), Inches(2.2), Inches(4.7), Inches(1.4))
    b.text_frame.word_wrap = True
    for j, line in enumerate(BODY):
        para = b.text_frame.paragraphs[0] if j == 0 else b.text_frame.add_paragraph()
        run = para.add_run()
        run.text = line
        run.font.size = Pt(16)
    prs.save(path)


def measure(path, workdir, tag):
    out = os.path.join(workdir, tag + ".json")
    subprocess.run([sys.executable, str(LINT), path, "--json-out", out], capture_output=True)
    report = json.load(open(out, encoding="utf-8"))
    codes = {}
    for slide in report["slides"]:
        for f in slide["findings"]:
            codes[f["code"]] = codes.get(f["code"], 0) + 1
    for f in report["deck_findings"]:
        codes[f["code"]] = codes.get(f["code"], 0) + 1
    render = subprocess.run([sys.executable, str(RENDER), path,
                             "--out", os.path.join(workdir, tag)], capture_output=True, text=True)
    overflow = len(re.findall(r"超過", render.stdout + render.stderr))
    # 箱が自動で伸びる設定（spAutoFit）だと、溢れる代わりに箱が下へ伸びて
    # 下のものと重なる。**検査そのものができなくなる**ので別に数える。
    import zipfile
    autofit = 0
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if re.match(r"ppt/slides/slide\d+\.xml", name):
                autofit += z.read(name).decode("utf-8").count("<a:spAutoFit/>")
    return codes, overflow, autofit


def main():
    with tempfile.TemporaryDirectory() as workdir:
        scope = skeleton_scope(workdir)
        a = os.path.join(workdir, "skeleton.pptx")
        b = os.path.join(workdir, "plain.pptx")
        build_with_skeleton(scope, a)
        build_plain(b)
        ca, oa, fa = measure(a, workdir, "sk")
        cb, ob, fb = measure(b, workdir, "pl")

    print("同じ内容を、骨格で組んだ場合と素の python-pptx で組んだ場合")
    print("%-28s %8s %8s" % ("指摘コード", "骨格", "素"))
    for code in sorted(set(ca) | set(cb)):
        print("%-28s %8d %8d" % (code, ca.get(code, 0), cb.get(code, 0)))
    print("%-28s %8d %8d" % ("指摘の合計", sum(ca.values()), sum(cb.values())))
    print("%-28s %8d %8d" % ("描画のはみ出し", oa, ob))
    print("%-28s %8d %8d" % ("検査できない箱(spAutoFit)", fa, fb))
    print("\n測っているのは機械的に検出できる欠陥の数だけで、デッキの良し悪しではない。")
    print("spAutoFit の箱は、溢れる代わりに下へ伸びて次の要素と重なる。溢れとして")
    print("計上されないので、素の版の「はみ出し 0」は健全さではなく**測れていない**ことを表す。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
