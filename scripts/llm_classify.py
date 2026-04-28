#!/usr/bin/env python3
"""LLM-based classifier for prompts that the keyword classifier (classify.py) couldn't bucket.

Uses Claude Haiku 4.5 with prompt caching: the system prompt + category menu is cached,
so each batch of N prompts only pays for the prompts themselves on input.

Run after merge.py + classify.py:
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 scripts/llm_classify.py            # default: classify Uncategorized only
    python3 scripts/llm_classify.py --include-general  # also reclassify "General" bucket
    python3 scripts/llm_classify.py --dry-run  # show what would change

Cost (Haiku 4.5, $1/MT input, $5/MT output, 90% cache discount on cached input):
    ~152 prompts * ~150 input tok + ~10 output tok per item
    ~= 23K input + 1.5K output, batched. Total < $0.01.
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
MODEL_NAME = "gpt-image-2"
OUT_DIR = ROOT / "models" / MODEL_NAME
JSON_PATH = OUT_DIR / "prompts.json"
CAT_DIR = OUT_DIR / "by-category"
STATS_PATH = OUT_DIR / "_stats.json"

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

CATEGORIES = [
    ("UI Mockup", "App screen, web design, dashboard, landing page, wireframe, SaaS interface"),
    ("Logo", "Brand mark, monogram, wordmark, brand identity, emblem"),
    ("Icon", "App icon, icon set, sticker pack (when iconographic)"),
    ("Infographic", "Cross-section, knowledge map, technical diagram, sketchnote, annotated illustration"),
    ("Text Rendering", "Typography poster, lettering, calligraphy, kinetic type"),
    ("Poster", "Movie/event/concert/key visual/marketing/propaganda poster"),
    ("Comic", "Manga, graphic novel, comic strip, webtoon, panel layout"),
    ("3D Scene", "Isometric, miniature world, diorama, low-poly, voxel, claymation"),
    ("Photography", "Photorealistic photo, film photography (Fujifilm/35mm/Polaroid), cinematic photo"),
    ("Portrait", "Headshot, profile, close-up of person, fashion portrait, self-portrait"),
    ("Character", "Character sheet, character design, mascot, hero/villain design"),
    ("Anime", "Anime/manga style illustration, Studio Ghibli, shojo/shonen"),
    ("Sticker", "Sticker sheet, kawaii sticker, line stickers"),
    ("Product", "Product photography/mockup, packaging design"),
    ("Architecture", "Building elevation, interior design, skyline, brutalist"),
    ("Food", "Plated dish, cookbook page, recipe card, latte art"),
    ("Landscape", "Wide vista, panorama, aerial view, nature photograph"),
    ("Fashion", "Editorial fashion, runway, lookbook, magazine cover"),
    ("Map", "World/fantasy/treasure/subway/tourist map"),
    ("Education", "Coloring book, worksheet, kids book, textbook illustration, storybook page"),
    ("Thumbnail", "YouTube thumbnail, TikTok cover, video reel cover"),
    ("Game", "Game asset, RPG portrait, trading card, game UI, pixel art"),
    ("Meme", "Meme template, wojak, distracted boyfriend, drake meme"),
    ("Restyle", "Style transfer using a reference image, recreate composition from a photo"),
    ("Editorial", "Magazine spread, editorial collage, fashion editorial layout"),
    ("Storyboard", "Multi-frame storyboard, scene-by-scene shot list"),
    ("Illustration", "Generic illustrative work that doesn't fit anywhere more specific"),
    ("Worldbuilding", "Fictional world references, faction sheets, lore visual"),
    ("Copy-Paste Library", "A copy-paste prompt library or template collection itself"),
    ("General", "Use ONLY when prompt is too short / ambiguous / generic to fit anything above"),
]

CATEGORY_NAMES = {c[0] for c in CATEGORIES}

SYSTEM_PROMPT = (
    "You are a precise image-prompt classifier. Given a list of AI image-generation prompts, "
    "return a JSON array where each element has the prompt's id and the single best category. "
    "Choose ONLY from the menu below. Match by intent of the prompt's primary deliverable, not by "
    "background details. If a prompt asks for a poster of a portrait, choose Poster. If it asks for "
    "a character sheet of an anime girl, choose Character (more specific than Anime). When in doubt "
    "between two categories, prefer the more specific one. Use 'General' only as a last resort.\n\n"
    "CATEGORY MENU:\n"
    + "\n".join(f"- {name}: {desc}" for name, desc in CATEGORIES)
    + "\n\nReturn ONLY a JSON array of {\"id\": str, \"category\": str} objects. No commentary."
)


def load_data():
    return json.load(JSON_PATH.open())


def save_data(data):
    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def rebuild_by_category(data):
    for old in CAT_DIR.glob("*.md"):
        old.unlink()
    CAT_DIR.mkdir(parents=True, exist_ok=True)
    by_cat = defaultdict(list)
    for r in data:
        by_cat[r["category"]].append(r)
    for cat, items in sorted(by_cat.items()):
        slug = re.sub(r"[^a-z0-9]+", "-", cat.lower()).strip("-") or "uncategorized"
        with (CAT_DIR / f"{slug}.md").open("w") as f:
            f.write(f"# {cat} ({len(items)})\n\n")
            for r in items:
                title = r.get("title") or (r["prompt"][:60].replace("\n", " ") + "...")
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
    return by_cat


def chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def classify_batch(client, batch):
    """Send N prompts in one call. Returns list of {id, category} dicts."""
    payload = [
        {"id": r["id"], "prompt": r["prompt"][:1500]}  # truncate huge prompts
        for r in batch
    ]
    user_msg = (
        "Classify each of these prompts. Return a JSON array.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            raise
        result = json.loads(m.group(0))
    usage = resp.usage
    return result, usage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-general", action="store_true",
                        help="Also reclassify entries currently in 'General'")
    parser.add_argument("--batch-size", type=int, default=25,
                        help="Prompts per API call (default 25)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY env var not set.", file=sys.stderr)
        sys.exit(1)

    data = load_data()
    target_cats = {"Uncategorized"}
    if args.include_general:
        target_cats.add("General")
    candidates = [r for r in data if r["category"] in target_cats]
    print(f"Found {len(candidates)} entries to reclassify (categories: {sorted(target_cats)})")
    if not candidates:
        return

    client = anthropic.Anthropic()
    by_id = {r["id"]: r for r in data}
    changes = Counter()
    total_in = total_out = total_cache_in = total_cache_read = 0
    started = time.time()

    for i, batch in enumerate(chunks(candidates, args.batch_size), start=1):
        print(f"  batch {i}: {len(batch)} prompts...", end=" ", flush=True)
        try:
            result, usage = classify_batch(client, batch)
        except Exception as e:
            print(f"\n  ERROR on batch {i}: {e}", file=sys.stderr)
            continue
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        total_cache_in += getattr(usage, "cache_creation_input_tokens", 0) or 0
        total_cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0

        for entry in result:
            rid, cat = entry.get("id"), entry.get("category")
            if rid in by_id and cat in CATEGORY_NAMES:
                old = by_id[rid]["category"]
                if old != cat:
                    if not args.dry_run:
                        by_id[rid]["category"] = cat
                    changes[(old, cat)] += 1
        print(f"ok ({len(result)} classified)")

    elapsed = time.time() - started
    cost_in = total_in / 1_000_000 * 1.0
    cost_cache_in = total_cache_in / 1_000_000 * 1.25  # cache write 25% premium
    cost_cache_read = total_cache_read / 1_000_000 * 0.10  # cache read 90% off
    cost_out = total_out / 1_000_000 * 5.0
    total_cost = cost_in + cost_cache_in + cost_cache_read + cost_out

    print()
    print(f"Done in {elapsed:.1f}s")
    print(f"Tokens: input={total_in} cache_write={total_cache_in} cache_read={total_cache_read} output={total_out}")
    print(f"Estimated cost: ${total_cost:.4f}")
    print()

    print(f"=== Reclassification summary ({sum(changes.values())} changes) ===")
    new_cat_totals = Counter()
    for (old, new), n in sorted(changes.items(), key=lambda x: -x[1]):
        new_cat_totals[new] += n
        print(f"  {old:<15} -> {new:<20} {n}")

    if args.dry_run:
        print("\n[dry-run] No files written.")
        return

    save_data(data)
    by_cat = rebuild_by_category(data)
    stats = {
        "model": MODEL_NAME,
        "total": len(data),
        "by_category": {k: len(v) for k, v in sorted(by_cat.items(), key=lambda x: -len(x[1]))},
    }
    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2))
    print("Updated prompts.json + by-category/ + _stats.json")


if __name__ == "__main__":
    main()
