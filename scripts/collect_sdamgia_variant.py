"""Small reproducible snapshot of one Sdamgia variant; no subject annotation.

Requires lxml. Run from any directory: python scripts/collect_sdamgia_variant.py
Use --offline to rebuild records from the saved snapshot and asset manifest.
"""
import argparse
import copy
import gzip
import hashlib
import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from lxml import html, etree

ROOT = Path(__file__).resolve().parents[1]
VARIANT = "90702516"
URL = f"https://math-ege.sdamgia.ru/test?id={VARIANT}&print=true"
RAW = ROOT / "data/raw/sdamgia" / VARIANT
OUT = ROOT / "data/processed/sdamgia" / VARIANT


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Research sample collector (one variant)"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            data = gzip.decompress(data)
        return data, response.headers.get_content_type()


def clean_text(value):
    return re.sub(r"\s+", " ", value.replace("\xad", "")).strip()


def canonical(node):
    node = copy.deepcopy(node)
    # Same formula is supplied in several responsive layouts. Keep the visible one.
    for el in node.xpath('.//span[contains(concat(" ", @class, " "), " tex-span ")]'):
        if "display:none" in el.get("style", "").replace(" ", ""):
            el.drop_tree()
    for el in node.xpath('.//script | .//style'):
        el.drop_tree()
    for el in node.iter():
        if not isinstance(el.tag, str):
            continue
        el.attrib.pop("onclick", None)
        style = re.sub(r"display\s*:\s*none\s*;?", "", el.get("style", ""))
        if "style" in el.attrib:
            el.set("style", style)
    return node


def text_with_math(node):
    node = copy.deepcopy(node)
    for img in node.xpath('.//img'):
        # Source alt is an accessibility description, not valid LaTeX.
        img.tail = " " + (img.get("alt") or "[рисунок]") + " " + (img.tail or "")
    return clean_text(node.text_content())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--retry-assets", action="store_true", help="Keep the snapshot, fetch only failed/missing assets")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (RAW / "assets").mkdir(exist_ok=True)
    if not args.offline and not args.retry_assets:
        payload, content_type = fetch(URL)
        RAW.joinpath("variant.html").write_bytes(payload)
        dump(RAW / "acquisition.json", {
            "url": URL, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "content_type": content_type, "sha256": hashlib.sha256(payload).hexdigest(),
            "collection_scope": "one variant, public content only",
            "provenance_status": "site_labels_as_fipi_not_verified_against_official_pdf",
            "usage_rights": "No reuse license established; source attribution retained; not relicensed by this repository.",
        })
    payload = (RAW / "variant.html").read_bytes()
    tree = html.fromstring(payload.decode("utf-8"))
    problems = tree.xpath('//div[@class="prob_maindiv"]')
    assert len(problems) == 19, f"Expected 19 tasks, got {len(problems)}"
    task_parts = []
    for pos, problem in enumerate(problems, 1):
        nums = problem.xpath('.//span[@class="prob_nums"]')[0]
        link = nums.xpath('.//a')[0]
        task_id = link.text_content().strip()
        statement = canonical(problem.xpath('.//div[@class="pbody"]')[0])
        solution = canonical(problem.xpath('./div[@class="solution"]')[0])
        criteria = problem.xpath('./div[@class="prob_crits"]')
        criteria = canonical(criteria[0]) if criteria else None
        answers = problem.xpath('./div[@class="answer"]')
        if answers:
            answer = canonical(answers[0])
        else:
            # Extended answers are included as the last paragraph in the solution.
            candidates = solution.xpath('.//p')
            candidates = [p for p in candidates if clean_text(p.text_content()).startswith("Ответ:")]
            answer = canonical(candidates[-1]) if candidates else None
        source_links = problem.xpath('.//div[@class="attr4"]//a')
        sources = list({urljoin(URL, a.get("href")): clean_text(a.text_content()) for a in source_links}.items())
        topic = problem.xpath('.//div[@class="align-left"]/div[not(@class)]')
        topic = [clean_text(e.text_content()) for e in topic if clean_text(e.text_content())]
        topic = [label for label in topic if not re.match(r"Источники?:", label)]
        record = {
            "variant_id": VARIANT, "position": pos, "site_task_id": task_id,
            "site_type": clean_text(nums.text_content()).split("№")[0].strip(),
            "url": urljoin(URL, link.get("href")), "variant_url": URL,
            "site_topic_labels": topic,
            "site_source_links": [{"url": u, "label": label} for u, label in sources],
            "provenance_status": "not_verified_against_official_pdf",
            "solution_validation_status": "not_mathematically_validated_in_this_collection",
            "dataset_role": "development_sample_not_holdout",
        }
        task_parts.append((record, {"statement": statement, "solution": solution, "answer": answer, "criteria": criteria}))

    urls = sorted({urljoin(URL, img.get("src")) for _, parts in task_parts for node in parts.values()
                   if node is not None for img in node.xpath('.//img')})
    if not args.offline:
        cache = json.loads((RAW / "assets.json").read_text()) if (RAW / "assets.json").exists() else []
        cache = {a["url"]: a for a in cache}
        def asset(url):
            cached = cache.get(url, {})
            if cached.get("status") == "ok":
                cached_path = ROOT / cached["path"]
                if cached_path.exists() and hashlib.sha256(cached_path.read_bytes()).hexdigest() == cached["sha256"]:
                    return cached
            name = hashlib.sha256(url.encode()).hexdigest()[:20]
            try:
                data, mime = fetch(url)
                ext = {"image/svg+xml": ".svg", "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif"}.get(mime)
                if ext is None:
                    raise ValueError(f"Unexpected media type {mime}")
                if ext == ".svg":
                    etree.fromstring(data)
                path = RAW / "assets" / (name + ext)
                path.write_bytes(data)
                return {"url": url, "path": str(path.relative_to(ROOT)), "content_type": mime,
                        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "status": "ok"}
            except Exception as exc:
                return {"url": url, "status": "error", "error": str(exc)}
        with ThreadPoolExecutor(max_workers=4) as pool:
            assets = list(pool.map(asset, urls))
        dump(RAW / "assets.json", assets)
    assets = json.loads((RAW / "assets.json").read_text())
    by_url = {a["url"]: a for a in assets}
    records = []
    preview = ['<!doctype html><html lang="ru"><meta charset="utf-8"><title>19 задач — пробный набор</title>',
               '<style>body{max-width:1050px;margin:30px auto;font:18px/1.55 serif;padding:20px}article{border-top:2px solid #aaa;padding:25px 0}img{max-width:100%}img.tex{vertical-align:middle}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:7px}h3{clear:both}.source{font:14px sans-serif;color:#555}</style>',
               '<h1>Вариант 90702516: пробный набор из 19 задач</h1><p>Источник: Решу ЕГЭ. Официальное происхождение не сверено. Формулы сохранены изображениями; собственной разметки нет.</p>']
    for record, parts in task_parts:
        refs = []
        for field, node in parts.items():
            record[field] = None
            if node is None:
                continue
            image_refs = []
            formula_count = 0
            for img in node.xpath('.//img'):
                url = urljoin(URL, img.get("src"))
                asset_info = by_url[url]
                role = "formula" if "tex" in img.get("class", "").split() else "figure"
                formula_count += role == "formula"
                image_refs.append({"url": url, "role": role, "path": asset_info.get("path"), "status": asset_info["status"]})
                if asset_info["status"] == "ok":
                    img.set("src", os.path.relpath(ROOT / asset_info["path"], OUT))
            record[field] = {"html": html.tostring(node, encoding="unicode", with_tail=False),
                             "text_accessibility": text_with_math(node), "images": image_refs,
                             "formula_image_count": formula_count}
            refs.extend(image_refs)
        record["asset_errors"] = sorted({r["url"] for r in refs if r["status"] != "ok"})
        records.append(record)
        preview.append(f'<article id="task-{record["position"]}"><h2>№{record["position"]} · ID {record["site_task_id"]}</h2><p class="source"><a href="{record["url"]}">Оригинал</a> · {"; ".join(record["site_topic_labels"])}</p>')
        for field, label in [("statement", "Условие"), ("answer", "Ответ"), ("solution", "Решение"), ("criteria", "Критерии")]:
            if record[field]:
                preview.append(f'<h3>{label}</h3>' + record[field]["html"])
        preview.append('</article>')
    preview.append('</html>')
    OUT.joinpath("preview.html").write_text("\n".join(preview))
    OUT.joinpath("tasks.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    stats = {
        "tasks": len(records),
        **{f"with_{f}": sum(r[f] is not None and bool(r[f]["text_accessibility"]) for r in records) for f in ["statement", "answer", "solution", "criteria"]},
        "with_statement_figures": sum(any(i["role"] == "figure" for i in r["statement"]["images"]) for r in records),
        "with_statement_formula_images": sum(r["statement"]["formula_image_count"] > 0 for r in records),
        "with_site_source_links": sum(bool(r["site_source_links"]) for r in records),
        "unique_task_ids": len({r["site_task_id"] for r in records}),
        "exact_duplicate_statement_groups": [],
        "unique_assets": len(assets), "asset_errors": sum(a["status"] != "ok" for a in assets),
        "assets_integrity_ok": all((ROOT / a["path"]).exists() and hashlib.sha256((ROOT / a["path"]).read_bytes()).hexdigest() == a["sha256"] for a in assets if a["status"] == "ok"),
        "positions_ok": [r["position"] for r in records] == list(range(1, 20)),
    }
    grouped = {}
    for r in records:
        signature = [r["statement"]["text_accessibility"],
                     [by_url[i["url"]].get("sha256", i["url"]) for i in r["statement"]["images"]]]
        key = hashlib.sha256(json.dumps(signature, ensure_ascii=False).encode()).hexdigest()
        grouped.setdefault(key, []).append(r["position"])
    stats["exact_duplicate_statement_groups"] = [v for v in grouped.values() if len(v) > 1]
    dump(OUT / "stats.json", stats)
    assert stats["positions_ok"] and stats["unique_task_ids"] == 19
    assert stats["assets_integrity_ok"]
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if stats["asset_errors"]:
        raise SystemExit("Asset failures: see assets.json; sample is incomplete")


if __name__ == "__main__":
    main()
