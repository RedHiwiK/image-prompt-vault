#!/usr/bin/env python3
"""Merge AI image-generation prompts from upstream awesome-* repos into one normalized schema.

Usage:
    python3 scripts/merge.py

Reads from /tmp/gpt-img2-compare/* (cloned upstream repos) and writes:
    models/gpt-image-2/prompts.json   (full merged dataset)
    models/gpt-image-2/prompts.csv    (spreadsheet view)
    models/gpt-image-2/by-category/*.md  (browsable per-category lists)

Re-run anytime upstream repos update or a new model launches.
"""
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "gpt-image-2"
OUT_DIR = ROOT / "models" / MODEL
SRC_BASE = Path("/tmp/gpt-img2-compare")

CATEGORY_ALIASES = {
    "general": "General",
    "poster": "Poster",
    "portrait": "Portrait",
    "portrait & photography": "Portrait",
    "photography": "Portrait",
    "character illustration": "Character",
    "character": "Character",
    "infographic": "Infographic",
    "ui mockup": "UI Mockup",
    "ui": "UI Mockup",
    "3d scene": "3D Scene",
    "3d": "3D Scene",
    "comic": "Comic",
    "text rendering": "Text Rendering",
    "text": "Text Rendering",
    "logo": "Logo",
    "icon": "Icon",
    "product": "Product",
    "scene": "Scene",
    "anime": "Anime",
    "illustration": "Illustration",
}


def norm_category(raw: str) -> str:
    if not raw:
        return "Uncategorized"
    return CATEGORY_ALIASES.get(raw.strip().lower(), raw.strip())


def fingerprint(prompt: str) -> str:
    """Stable dedup key: lowercased, whitespace-collapsed first 200 chars."""
    if not prompt:
        return ""
    s = re.sub(r"\s+", " ", prompt.strip().lower())[:200]
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def load_peterRooo():
    p = SRC_BASE / "peterRooo_awesome-gpt-image-2-prompts/data/gpt-image-2-prompts.json"
    if not p.exists():
        return []
    out = []
    for r in json.load(p.open()):
        out.append({
            "prompt": r.get("prompt", "").strip(),
            "title": r.get("title"),
            "category": norm_category(r.get("category")),
            "language": r.get("language"),
            "quality": r.get("quality_grade"),
            "author": r.get("author_name"),
            "source_url": r.get("source_url"),
            "image_url": r.get("image_url"),
            "published_at": r.get("published_at") or r.get("date"),
            "upstream_repo": "peterRooo/awesome-gpt-image-2-prompts",
            "upstream_channel": r.get("channel"),
        })
    return out


def load_erickkkyt():
    p = SRC_BASE / "erickkkyt_awesome-gptimage2-prompts/prompts/prompts.json"
    if not p.exists():
        return []
    out = []
    for r in json.load(p.open()):
        img = r.get("image") or (r.get("images") or [None])[0]
        out.append({
            "prompt": (r.get("prompt") or "").strip(),
            "title": None,
            "category": "Uncategorized",
            "language": (r.get("languages") or [None])[0],
            "quality": None,
            "author": r.get("author_name") or r.get("author"),
            "source_url": r.get("source_url"),
            "image_url": img if isinstance(img, str) else (img.get("url") if isinstance(img, dict) else None),
            "published_at": r.get("published") or r.get("date"),
            "upstream_repo": "erickkkyt/awesome-gptimage2-prompts",
            "upstream_channel": r.get("source"),
        })
    return out


def load_EvoLinkAI():
    p = SRC_BASE / "EvoLinkAI_awesome-gpt-image-2-prompts/gpt_image2_prompts.json"
    if not p.exists():
        return []
    out = []
    for r in json.load(p.open()):
        out.append({
            "prompt": (r.get("text") or "").strip(),
            "title": None,
            "category": "Uncategorized",
            "language": r.get("lang"),
            "quality": None,
            "author": (r.get("author") or {}).get("username") if isinstance(r.get("author"), dict) else r.get("author"),
            "source_url": r.get("url"),
            "image_url": (r.get("media") or [{}])[0].get("url") if r.get("media") else None,
            "published_at": r.get("createdAt"),
            "upstream_repo": "EvoLinkAI/awesome-gpt-image-2-prompts",
            "upstream_channel": "x",
        })
    return out


def load_AzhuTech():
    p = SRC_BASE / "AzhuTech_awesome-gpt-image-2-prompts/catalog/prompts.json"
    if not p.exists():
        return []
    out = []
    for r in json.load(p.open()):
        out.append({
            "prompt": (r.get("prompt") or "").strip(),
            "title": r.get("title"),
            "category": norm_category((r.get("tags") or [None])[0] if r.get("tags") else None),
            "language": "en",
            "quality": None,
            "author": None,
            "source_url": None,
            "image_url": r.get("preview_image"),
            "published_at": None,
            "upstream_repo": "AzhuTech/awesome-gpt-image-2-prompts",
            "upstream_channel": "curated",
        })
    return out


def main():
    loaders = [load_peterRooo, load_erickkkyt, load_EvoLinkAI, load_AzhuTech]
    raw = []
    counts = {}
    for fn in loaders:
        items = fn()
        counts[fn.__name__.replace("load_", "")] = len(items)
        raw.extend(items)

    seen = {}
    for item in raw:
        if not item["prompt"] or len(item["prompt"]) < 20:
            continue
        fp = fingerprint(item["prompt"])
        if fp not in seen:
            item["id"] = fp[:12]
            seen[fp] = item

    merged = sorted(seen.values(), key=lambda x: (x["category"], x.get("title") or ""))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with (OUT_DIR / "prompts.json").open("w") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    fields = ["id", "category", "title", "language", "quality", "author",
              "source_url", "image_url", "published_at", "upstream_repo", "upstream_channel", "prompt"]
    with (OUT_DIR / "prompts.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in merged:
            w.writerow(r)

    by_cat = defaultdict(list)
    for r in merged:
        by_cat[r["category"]].append(r)

    cat_dir = OUT_DIR / "by-category"
    cat_dir.mkdir(exist_ok=True)
    for old in cat_dir.glob("*.md"):
        old.unlink()

    for cat, items in sorted(by_cat.items()):
        slug = re.sub(r"[^a-z0-9]+", "-", cat.lower()).strip("-") or "uncategorized"
        path = cat_dir / f"{slug}.md"
        with path.open("w") as f:
            f.write(f"# {cat} ({len(items)})\n\n")
            for r in items:
                title = r.get("title") or (r["prompt"][:60] + "...")
                f.write(f"## {title}\n\n")
                if r.get("author"):
                    f.write(f"- author: {r['author']}\n")
                if r.get("source_url"):
                    f.write(f"- source: {r['source_url']}\n")
                if r.get("image_url"):
                    f.write(f"- preview: {r['image_url']}\n")
                if r.get("language"):
                    f.write(f"- lang: {r['language']}\n")
                if r.get("quality"):
                    f.write(f"- quality: {r['quality']}\n")
                f.write(f"- upstream: {r['upstream_repo']}\n\n")
                f.write("```\n")
                f.write(r["prompt"])
                f.write("\n```\n\n")

    summary = {
        "model": MODEL,
        "total": len(merged),
        "raw_total": len(raw),
        "deduped": len(raw) - len(merged),
        "by_upstream": counts,
        "by_category": {k: len(v) for k, v in sorted(by_cat.items(), key=lambda x: -len(x[1]))},
    }
    with (OUT_DIR / "_stats.json").open("w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"Merged {len(merged)} unique prompts (raw {len(raw)}, dropped {len(raw)-len(merged)} dupes/short).")
    print(f"Per-upstream: {counts}")
    print(f"Top categories:")
    for c, items in sorted(by_cat.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {c:25s} {len(items)}")
    print(f"\nWritten to {OUT_DIR}")


if __name__ == "__main__":
    main()
