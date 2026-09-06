#!/usr/bin/env python3
"""1つのテキスト図形を、書式・幾何を保ち、収まりを検査して差し替える。"""

import argparse
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve()
REVIEW_SCRIPTS = HERE.parents[2] / "pptx-review" / "scripts"
sys.path.insert(0, str(REVIEW_SCRIPTS))

import layout_guard as G  # noqa: E402
import pptx_lint as L  # noqa: E402


def lint_shape(path, slide_number, shape_id):
    pkg = L.Package(path)
    part = L.slide_order(pkg)[slide_number - 1]
    layout = pkg.related(part, "/slideLayout")
    master = pkg.related(layout, "/slideMaster") if layout else None
    shapes = L.collect_shapes(
        pkg, part,
        L.placeholder_positions(pkg, layout) if layout else {},
        L.placeholder_positions(pkg, master) if master else {},
    )
    return next((shape for shape in shapes if str(shape["id"]) == str(shape_id)), None)


def main(argv=None):
    parser = argparse.ArgumentParser(description="書式とレイアウトを壊さない単一図形の文言差し替え")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--slide", required=True, type=int, help="1始まりのページ番号")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--shape-id", type=int)
    target.add_argument("--shape-name")
    text = parser.add_mutually_exclusive_group(required=True)
    text.add_argument("--text")
    text.add_argument("--text-file")
    parser.add_argument("--max-fill", type=float, default=0.90,
                        help="必要寸法/箱寸法の上限。既定0.90")
    args = parser.parse_args(argv)
    temp_path = None
    try:
        src, dst = pathlib.Path(args.input), pathlib.Path(args.output)
        if src.resolve() == dst.resolve():
            raise ValueError("input と output は別名にする")
        if dst.exists():
            raise ValueError("output exists: %s" % dst)
        if not 0.5 <= args.max_fill < 1.0:
            raise ValueError("--max-fill は 0.5以上1.0未満")
        new_text = (pathlib.Path(args.text_file).read_text(encoding="utf-8")
                    if args.text_file else args.text)
        if "\n" in new_text or "\r" in new_text:
            raise ValueError("複数段落は安全経路の対象外。ページ分割または専用編集を使う")

        from pptx import Presentation
        prs = Presentation(str(src))
        if args.slide < 1 or args.slide > len(prs.slides):
            raise ValueError("slide が範囲外")
        slide = prs.slides[args.slide - 1]
        matches = [shape for shape in slide.shapes
                   if ((args.shape_id is not None and shape.shape_id == args.shape_id)
                       or (args.shape_name is not None and shape.name == args.shape_name))]
        if len(matches) != 1:
            raise ValueError("対象図形は1件である必要がある（%d件）" % len(matches))
        shape = matches[0]
        if not shape.has_text_frame or len(shape.text_frame.paragraphs) != 1:
            raise ValueError("単一段落のテキスト図形だけが安全経路の対象")
        para = shape.text_frame.paragraphs[0]
        if not para.runs:
            raise ValueError("既存runが無い。書式を安全に継承できない")
        source_shape = lint_shape(str(src), args.slide, shape.shape_id)
        source_fit = L.estimate_overflow(source_shape) if source_shape else None
        if source_fit and source_fit[1] in ("autogrow", "autofit"):
            raise RuntimeError("%s が有効。箱伸長・文字縮小を伴うため差し替えを中止" %
                               source_fit[1])
        old_text = para.text
        para.runs[0].text = new_text
        for run in para.runs[1:]:
            run.text = ""

        dst.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(prefix="pptx-safe-edit-", suffix=".pptx",
                                             dir=str(dst.parent), delete=False)
        temp_path = handle.name
        handle.close()
        prs.save(temp_path)

        findings = G.compare(G.snapshot(str(src)), G.snapshot(temp_path))
        active = [f for f in findings if f["code"] != "EDIT_TEXT_REFLOW_RISK"]
        if active:
            raise RuntimeError("文言以外の変化を検出: %s" %
                               ", ".join(sorted(set(f["code"] for f in active))))
        measured = lint_shape(temp_path, args.slide, shape.shape_id)
        fit = L.estimate_overflow(measured) if measured else None
        if fit is None:
            raise RuntimeError("文字の収まりを測定できない")
        ratio, confidence, axis = fit
        if confidence in ("autogrow", "autofit"):
            raise RuntimeError("%s が有効。箱伸長・文字縮小を伴うため差し替えを中止" % confidence)
        if ratio > args.max_fill:
            raise RuntimeError("収まりに余裕がない: %s比 %.2f > %.2f" %
                               ("横" if axis == "width" else "縦", ratio, args.max_fill))
        os.replace(temp_path, dst)
        temp_path = None
        print(json.dumps({"passed": True, "slide": args.slide, "shape_id": shape.shape_id,
                          "old_text": old_text, "new_text": new_text,
                          "fill_ratio": round(ratio, 3), "measurement": confidence},
                         ensure_ascii=False))
        return 0
    except RuntimeError as exc:
        print("REJECTED: %s" % exc, file=sys.stderr)
        return 1
    except (OSError, ValueError, IndexError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


if __name__ == "__main__":
    sys.exit(main())
