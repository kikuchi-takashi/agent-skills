#!/usr/bin/env python3
"""編集前後の PPTX を比較し、意図しないレイアウト変化を検出する。"""

import argparse
import copy
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET

import pptx_lint as L


def xml_without(node, tags=()):
    if node is None:
        return None
    clone = copy.deepcopy(node)
    for child in list(clone):
        if child.tag in tags:
            clone.remove(child)
    return ET.tostring(clone, encoding="unicode")


def shape_snapshot(shape, z_index):
    el = shape["el"]
    sp_pr = el.find(L.q("p", "spPr"))
    if sp_pr is None and shape["kind"] in ("table", "chart", "graphic"):
        sp_pr = el.find(L.q("p", "xfrm"))
    body_pr = shape["body_pr"]
    para_style = []
    for para in shape["paragraphs"]:
        para_style.append({
            "p": [para[k] for k in ("line_spacing", "line_pts", "before", "after",
                                      "algn", "bullet", "mar_l", "indent", "level")],
            "runs": [[run.get("size"), run.get("bold"), run.get("color")]
                     for run in para["runs"] if run.get("text") != "\n"],
            "fonts": sorted(para["fonts"]),
        })
    src_rect = el.find(".//" + L.q("a", "srcRect"))
    grid = el.find(".//" + L.q("a", "tblGrid"))
    table_rows = el.findall(".//" + L.q("a", "tr"))
    return {
        "id": shape["id"], "name": shape["name"], "kind": shape["kind"],
        "box": [round(v, 4) for v in shape["box"]] if shape["box"] else None,
        "z": z_index, "text": shape["text"], "placeholder": shape["placeholder"],
        "body": xml_without(body_pr), "paragraph_style": para_style,
        "format": xml_without(sp_pr, (L.q("a", "xfrm"),)),
        "crop": dict(src_rect.attrib) if src_rect is not None else None,
        "table": {
            "columns": [int(col.get("w", "0")) for col in grid] if grid is not None else [],
            "rows": [int(row.get("h", "0")) for row in table_rows],
        } if shape["kind"] == "table" else None,
        "object": shape,
    }


def digest(pkg, part):
    return hashlib.sha256(pkg.zip.read(part)).hexdigest() if part in pkg.names else None


def snapshot(path):
    pkg = L.Package(path)
    slides = L.slide_order(pkg)
    result = {
        "canvas": L.canvas_size(pkg),
        "theme": digest(pkg, "ppt/theme/theme1.xml"),
        "slides": {}, "order": slides, "shared": {},
    }
    target_users = {}
    for index, part in enumerate(slides, 1):
        layout = pkg.related(part, "/slideLayout")
        master = pkg.related(layout, "/slideMaster") if layout else None
        layout_pos = L.placeholder_positions(pkg, layout) if layout else {}
        master_pos = L.placeholder_positions(pkg, master) if master else {}
        shapes = L.collect_shapes(pkg, part, layout_pos, master_pos)
        result["slides"][part] = {
            "index": index, "layout": layout, "master": master,
            "shapes": {s["id"]: shape_snapshot(s, z) for z, s in enumerate(shapes)
                       if s["id"]},
        }
        for _, (rtype, target) in pkg.rels(part).items():
            if any(rtype.endswith(suffix) for suffix in
                   ("/chart", "/diagramData", "/oleObject", "/package")):
                target_users.setdefault(target, []).append(part)
    result["shared"] = {
        target: {"users": users, "digest": digest(pkg, target)}
        for target, users in target_users.items() if len(users) > 1
    }
    return result


def load_allow(path):
    if not path:
        return []
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    entries = data.get("allow", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError("allow JSON must be a list or contain an allow list")
    for entry in entries:
        if (not isinstance(entry, dict) or not entry.get("code")
                or not isinstance(entry.get("reason"), str) or not entry["reason"].strip()):
            raise ValueError("allow entries require code and non-empty reason")
    return entries


def compare(before, after):
    findings = []

    def add(code, severity, message, slide=None, shape=None):
        item = {"code": code, "severity": severity, "message": message}
        if slide is not None:
            item["slide"] = slide
        if shape:
            item["shape"] = shape
        findings.append(item)

    if before["canvas"] != after["canvas"]:
        add("CANVAS_CHANGED", "error", "スライドサイズが変更された")
    if before["theme"] != after["theme"]:
        add("THEME_CHANGED", "error", "テーマが変更された。全ページの色・書体が変わりうる")
    common_parts = set(before["slides"]) & set(after["slides"])
    for part in sorted(common_parts):
        left, right = before["slides"][part], after["slides"][part]
        slide = right["index"]
        if left["layout"] != right["layout"] or left["master"] != right["master"]:
            add("SLIDE_LAYOUT_CHANGED", "error", "既存スライドのlayout/master参照が変わった", slide)
        left_ids, right_ids = set(left["shapes"]), set(right["shapes"])
        for sid in sorted(left_ids - right_ids):
            old = left["shapes"][sid]
            add("SHAPE_REMOVED", "warning", "既存図形が削除された", slide, old["name"] or sid)
        for sid in sorted(right_ids - left_ids):
            new = right["shapes"][sid]
            add("SHAPE_ADDED", "warning", "図形が追加された", slide, new["name"] or sid)
        common_ids = left_ids & right_ids
        left_order = [sid for sid, _ in sorted(left["shapes"].items(), key=lambda kv: kv[1]["z"])
                      if sid in common_ids]
        right_order = [sid for sid, _ in sorted(right["shapes"].items(), key=lambda kv: kv[1]["z"])
                       if sid in common_ids]
        if left_order != right_order:
            add("Z_ORDER_CHANGED", "warning", "既存図形の重ね順が変更された", slide)
        for sid in sorted(common_ids):
            old, new = left["shapes"][sid], right["shapes"][sid]
            name = new["name"] or sid
            if old["kind"] != new["kind"] or old["placeholder"] != new["placeholder"]:
                add("SHAPE_ROLE_CHANGED", "error", "図形種別またはplaceholderの役割が変わった", slide, name)
            if old["box"] != new["box"]:
                add("SHAPE_GEOMETRY_CHANGED", "warning",
                    "位置・大きさが %s から %s に変わった" % (old["box"], new["box"]), slide, name)
            if old["body"] != new["body"]:
                add("TEXT_FRAME_CHANGED", "warning", "余白・折返し・縦位置・自動調整が変わった", slide, name)
            if old["paragraph_style"] != new["paragraph_style"]:
                add("TEXT_STYLE_CHANGED", "warning", "段落・runの書式構造が変わった", slide, name)
            if old["format"] != new["format"]:
                add("SHAPE_FORMAT_CHANGED", "warning", "塗り・線・形状などの書式が変わった", slide, name)
            if old["crop"] != new["crop"]:
                add("PICTURE_CROP_CHANGED", "warning", "画像のcropが変わった", slide, name)
            if old["table"] != new["table"]:
                add("TABLE_GEOMETRY_CHANGED", "warning", "表の列幅または行高が変わった", slide, name)
            if old["text"] != new["text"]:
                fit = L.estimate_overflow(new["object"])
                if fit:
                    ratio, confidence, axis = fit
                    if confidence == "autogrow":
                        add("EDIT_AUTOFIT_REFLOW", "error",
                            "文言変更後も箱が自動伸長する。%s比 %.2f で後続要素へ重なりうる" %
                            ("横" if axis == "width" else "縦", ratio), slide, name)
                    elif ratio >= 1.02:
                        add("EDIT_TEXT_REFLOW_RISK", "error" if ratio >= 1.15 else "warning",
                            "文言変更後の収まりが%s比 %.2f" %
                            ("横" if axis == "width" else "縦", ratio), slide, name)
    for target, old in before["shared"].items():
        new = after["shared"].get(target)
        if new and old["digest"] != new["digest"]:
            slides = [after["slides"][p]["index"] for p in new["users"] if p in after["slides"]]
            add("SHARED_PART_CHANGED", "error",
                "%s は複数スライド p.%s が共有する部品。片方の編集が双方へ反映される" %
                (target, ",".join(str(i) for i in slides)))
    return findings


def apply_allow(findings, allow):
    for finding in findings:
        for entry in allow:
            if entry["code"] != finding["code"]:
                continue
            if entry.get("slide") is not None and entry["slide"] != finding.get("slide"):
                continue
            if entry.get("shape") and entry["shape"] != finding.get("shape"):
                continue
            finding["allowed"], finding["reason"] = True, entry["reason"].strip()
            break


def main(argv=None):
    parser = argparse.ArgumentParser(description="編集前後のPPTXでレイアウト変化を比較する")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--allow", help="意図した変更を理由つきで登録したJSON")
    parser.add_argument("--json-out")
    parser.add_argument("--strict", action="store_true", help="未許可のwarningも失敗にする")
    args = parser.parse_args(argv)
    try:
        findings = compare(snapshot(args.before), snapshot(args.after))
        apply_allow(findings, load_allow(args.allow))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    active = [f for f in findings if not f.get("allowed")]
    errors = sum(f["severity"] == "error" for f in active)
    warnings = sum(f["severity"] == "warning" for f in active)
    passed = errors == 0 and (not args.strict or warnings == 0)
    report = {"before": args.before, "after": args.after, "findings": findings,
              "summary": {"errors": errors, "warnings": warnings,
                          "allowed": len(findings) - len(active), "strict": args.strict},
              "passed": passed}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        parent = os.path.dirname(args.json_out)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(output + "\n")
    print(output)
    print("--- layout_guard: %d errors, %d warnings, passed=%s" %
          (errors, warnings, passed), file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
