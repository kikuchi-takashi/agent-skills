#!/usr/bin/env python3
"""生成後の設計〜実装対応表と、目視QA証跡を作成・検査する。"""

import argparse
import hashlib
import json
import os
import pathlib
import sys

import pptx_lint as L


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def read_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def actual_slides(path):
    pkg = L.Package(path)
    result = []
    for index, part in enumerate(L.slide_order(pkg), 1):
        layout = pkg.related(part, "/slideLayout")
        master = pkg.related(layout, "/slideMaster") if layout else None
        shapes = L.collect_shapes(
            pkg, part,
            L.placeholder_positions(pkg, layout) if layout else {},
            L.placeholder_positions(pkg, master) if master else {},
        )
        title = next((s["text"] for s in shapes if L.is_title(s)), "")
        result.append({"n": index, "part": part, "title": title,
                       "shape_count": len(shapes),
                       "kinds": sorted(set(s["kind"] for s in shapes))})
    return result


def init(args):
    out = pathlib.Path(args.json_out)
    map_out = pathlib.Path(args.map_out)
    existing = [str(path) for path in (out, map_out) if path.exists()]
    if existing and not args.force:
        raise ValueError("output exists: %s; use --force" % ", ".join(existing))
    spec = read_json(args.spec)
    actual = actual_slides(args.pptx)
    planned = {s.get("n", i): s for i, s in enumerate(spec.get("slides", []), 1)}
    expected = set(range(1, len(actual) + 1))
    if set(planned) != expected:
        raise ValueError("implementation-spec のページ番号が実物と一致しない")
    prefix = pathlib.Path(args.preview_prefix)
    sheet = pathlib.Path(str(prefix) + "-sheet.png")
    missing = []
    slides = []
    for slide in actual:
        preview = pathlib.Path("%s-%02d.png" % (prefix, slide["n"]))
        if not preview.exists():
            missing.append(str(preview))
        plan = planned.get(slide["n"], {})
        impl = plan.get("implementation", {})
        slides.append({
            "n": slide["n"], "title": slide["title"], "part": slide["part"],
            "planned_archetype": plan.get("archetype", ""),
            "planned_function": impl.get("function", ""),
            "design_intent": impl.get("design_intent", ""),
            "actual_shape_count": slide["shape_count"], "actual_kinds": slide["kinds"],
            "preview": str(preview), "preview_sha256": digest(preview) if preview.exists() else "",
            "implementation_match": {"status": "pending", "evidence": ""},
            "individual_review": {"status": "pending", "evidence": ""},
        })
    if not sheet.exists():
        missing.append(str(sheet))
    if missing:
        raise ValueError("preview が不足: %s" % ", ".join(missing))
    complex_kinds = sorted({kind for slide in slides for kind in slide["actual_kinds"]
                            if kind in ("chart", "graphic", "picture")})
    manifest = {
        "pptx": args.pptx, "pptx_sha256": digest(args.pptx),
        "formal_qa": {"status": "pending", "evidence": [],
                      "required": ["reopen", "outline", "implementation-spec", "lint"]},
        "design_qa": {"status": "pending", "evidence": [],
                      "required": ["signature", "form-choice", "hero", "rhythm"]},
        "sheet_review": {"status": "pending", "preview": str(sheet),
                         "preview_sha256": digest(sheet), "evidence": ""},
        "native_render_review": {
            "required": bool(complex_kinds),
            "kinds": complex_kinds,
            "status": "pending" if complex_kinds else "not-applicable",
            "evidence": "" if complex_kinds else "簡易描画で扱える図形だけ",
        },
        "slides": slides,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_map(map_out, manifest)
    return 0


def write_map(path, manifest):
    lines = ["# 設計〜実装対応表", "",
             "| p. | タイトル | 設計意図 | 原型 | 実装関数 | 実物 | 個別preview |",
             "|---:|---|---|---|---|---|---|"]
    for slide in manifest["slides"]:
        actual = "%d図形 / %s" % (slide["actual_shape_count"], ", ".join(slide["actual_kinds"]))
        values = [slide["n"], slide["title"], slide["design_intent"],
                  slide["planned_archetype"], slide["planned_function"], actual, slide["preview"]]
        lines.append("| %s |" % " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in values))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def passed_block(block):
    evidence = block.get("evidence")
    if block.get("status") != "pass" or not evidence:
        return False
    required = block.get("required", [])
    if isinstance(evidence, dict) and required:
        return all(str(evidence.get(key, "")).strip() for key in required)
    if isinstance(evidence, list) and required:
        return len([v for v in evidence if str(v).strip()]) >= len(required)
    return len(str(evidence).strip()) >= 8


def check(args):
    manifest = read_json(args.manifest)
    findings = []
    for name in ("formal_qa", "design_qa", "sheet_review"):
        if not passed_block(manifest.get(name, {})):
            findings.append("%s が pass でなく、根拠も揃っていない" % name)
    native = manifest.get("native_render_review", {})
    if native.get("required") and not passed_block(native):
        findings.append("図表・画像等があるためPowerPoint互換描画の確認が必要")
    slides = manifest.get("slides", [])
    if not slides:
        findings.append("slides が空")
    for slide in slides:
        for name in ("implementation_match", "individual_review"):
            if not passed_block(slide.get(name, {})):
                findings.append("p.%s %s が未完了" % (slide.get("n", "?"), name))
    previews = [slide.get("preview") for slide in slides]
    if len(set(previews)) != len(previews) or any(not p or not os.path.exists(p) for p in previews):
        findings.append("全ページ固有の個別previewが存在しない")
    else:
        for slide in slides:
            if digest(slide["preview"]) != slide.get("preview_sha256"):
                findings.append("p.%s 個別previewが証跡作成後に変わった" % slide.get("n", "?"))
    sheet = manifest.get("sheet_review", {}).get("preview")
    if not sheet or not os.path.exists(sheet):
        findings.append("一覧previewが存在しない")
    elif digest(sheet) != manifest.get("sheet_review", {}).get("preview_sha256"):
        findings.append("一覧previewが証跡作成後に変わった")
    pptx = manifest.get("pptx")
    if not pptx or not os.path.exists(pptx):
        findings.append("対象PPTXが存在しない")
    elif digest(pptx) != manifest.get("pptx_sha256"):
        findings.append("対象PPTXが証跡作成後に変わった")
    individual_evidence = [str(slide.get("individual_review", {}).get("evidence", "")).strip()
                           for slide in slides]
    if len(set(individual_evidence)) != len(individual_evidence):
        findings.append("全ページに同じ個別目視所見が使われている")
    print("--- qa_evidence: %d ページ, %d 件" % (len(slides), len(findings)))
    for finding in findings:
        print("  " + finding, file=sys.stderr)
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="設計〜実装対応表と目視QA証跡を管理する")
    sub = parser.add_subparsers(dest="command")
    make = sub.add_parser("init", help="生成後に対応表と未記入のQA証跡を作る")
    make.add_argument("pptx")
    make.add_argument("--spec", required=True)
    make.add_argument("--preview-prefix", required=True)
    make.add_argument("--json-out", required=True)
    make.add_argument("--map-out", required=True)
    make.add_argument("--force", action="store_true")
    verify = sub.add_parser("check", help="全ページ目視と形式/デザインQAの完了を検査する")
    verify.add_argument("manifest")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return init(args)
        if args.command == "check":
            return check(args)
        parser.print_help()
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
