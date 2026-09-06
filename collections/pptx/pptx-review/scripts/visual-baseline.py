#!/usr/bin/env python3
"""描画の見た目の回帰検査。pptx-suite の保守用。

lint は幾何の数値を見る。ここは**描かれた画素**を見る。描画側の退行——
消したはずの枠が描かれる、面が塗られない、線が太る——は数値に出ないため、
画素を基準画像と突き合わせる以外に捕まえる手が無い。

    python3 collections/pptx/pptx-review/scripts/visual-baseline.py            # 照合
    python3 collections/pptx/pptx-review/scripts/visual-baseline.py --update   # 基準を更新

**文字を置かない。** 文字のある画は実行環境にある書体で変わるので、機械を
またいで再現しない（実測: 同じデッキでも和文書体の有無で全ページの画素が
変わる）。図形だけの画は書体に依らず、同じ入力なら同じ画素になる（実測:
17ページすべてでハッシュ一致）。基準にできるのは後者だけである。
"""

import argparse
import hashlib
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
RENDER = ROOT / "pptx-review" / "scripts" / "render_preview.py"
ENGINE = ROOT / "pptx-create" / "references" / "engine-notes.md"
BASELINE = pathlib.Path(__file__).resolve().parent / "baseline" / "shapes.png"
LOCK = {
    "fonts": ["Yu Gothic"],
    "palette_basis": "基準画像用。色は固定でよい（見た目の退行だけを見る）",
    "palette": {"bg": "FFFFFF", "text": "1A1A1A", "muted": "5C5C5C", "line": "D9D9D6",
                "panel": "F4F4F2", "primary": "1F2A44", "accent": "E86A1F"},
}

EXIT_OK, EXIT_DIFF, EXIT_ERROR = 0, 1, 2


def skeleton(workdir):
    """骨格を読み込んだ名前空間を返す。"""
    import json
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


def fixture(scope, path):
    """**文字を置かない**図形だけの1枚。描き方が変わると画素が変わる要素を並べる。"""
    from pptx.util import Inches
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.dml.color import RGBColor

    prs = scope["new_deck"]()
    s = scope["blank"](prs)
    C, W, H = scope["C"], scope["W"], scope["H"]
    scope["rect"](s, 0, 0, W, H, "bg")                       # 地
    scope["rect"](s, 0.6, 0.5, 5.6, 1.0, "panel")            # 淡い面
    scope["rect"](s, 6.6, 0.5, 5.6, 1.0, "primary")          # 濃い面
    scope["rect"](s, 0.6, 1.8, 12.1, 0.02, "line")           # 罫線
    scope["rect"](s, 0.6, 2.1, 2.5, 1.0, "panel", rounded=True)   # 角丸
    scope["rect"](s, 3.4, 2.1, 2.5, 1.0)                     # 塗りも線も無い（何も描かれないのが正）
    # 形ごとに枠の扱いが分かれるので、専用の描き方を持たない形も入れる
    for i, kind in enumerate((MSO_SHAPE.RIGHT_ARROW, MSO_SHAPE.CHEVRON, MSO_SHAPE.OVAL,
                              MSO_SHAPE.SNIP_1_RECTANGLE)):
        sh = s.shapes.add_shape(kind, Inches(6.2 + i * 1.7), Inches(2.1), Inches(1.5), Inches(1.0))
        sh.fill.solid()
        sh.fill.fore_color.rgb = RGBColor.from_string(C["panel"])
        sh.line.fill.background()                            # 線は明示的に消す
        sh.shadow.inherit = False
    lined = s.shapes.add_shape(MSO_SHAPE.CHEVRON, Inches(0.6), Inches(3.4),
                               Inches(1.5), Inches(1.0))
    lined.fill.solid()
    lined.fill.fore_color.rgb = RGBColor.from_string(C["bg"])
    lined.line.color.rgb = RGBColor.from_string(C["accent"])          # 線は「ある」側
    lined.shadow.inherit = False
    a = scope["rect"](s, 2.6, 3.4, 2.0, 1.0, "panel")
    b = scope["rect"](s, 5.6, 3.4, 2.0, 1.0, "panel")
    scope["connect"](s, a, b)                                # 直線のつなぎ
    c = scope["rect"](s, 8.6, 4.9, 2.0, 1.0, "panel")
    scope["connect"](s, b, c)                                # 段違い＝直角に折れる
    scope["scrim"](s, 0.6, 5.6, 5.6, 1.0)                    # 半透明の面
    prs.save(path)


def render(pptx_path, out_prefix):
    subprocess.run([sys.executable, str(RENDER), pptx_path, "--out", out_prefix],
                   capture_output=True, check=True)
    return out_prefix + "-01.png"


def main():
    ap = argparse.ArgumentParser(description="描画の見た目の回帰検査（図形だけ・書体に依らない）")
    ap.add_argument("--update", action="store_true", help="基準画像を今の描画で置き換える")
    ap.add_argument("--out", help="差分が出たときに今の画像を書き出す先")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as workdir:
        try:
            scope = skeleton(workdir)
            pptx_path = os.path.join(workdir, "shapes.pptx")
            fixture(scope, pptx_path)
            current = render(pptx_path, os.path.join(workdir, "shapes"))
        except Exception as exc:
            print("ERROR: 基準画像を作れない: %s" % exc, file=sys.stderr)
            return EXIT_ERROR
        blob = open(current, "rb").read()
        digest = hashlib.sha256(blob).hexdigest()

        if args.update or not BASELINE.exists():
            BASELINE.parent.mkdir(parents=True, exist_ok=True)
            BASELINE.write_bytes(blob)
            print("基準画像を書いた: %s (sha256 %s)" % (BASELINE, digest[:16]))
            return EXIT_OK

        base = BASELINE.read_bytes()
        if base == blob:
            print("見た目の回帰なし (sha256 %s)" % digest[:16])
            return EXIT_OK

        dest = args.out or str(BASELINE.with_name("shapes-current.png"))
        pathlib.Path(dest).write_bytes(blob)
        print("NG 描画が変わった。基準 %s / 現在 %s"
              % (hashlib.sha256(base).hexdigest()[:16], digest[:16]))
        print("  基準: %s" % BASELINE)
        print("  現在: %s" % dest)
        print("  2枚を見比べ、意図した変更なら --update で基準を更新する")
        return EXIT_DIFF


if __name__ == "__main__":
    sys.exit(main())
