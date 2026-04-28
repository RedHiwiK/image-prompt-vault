#!/usr/bin/env python3
"""Keyword-based classifier for Uncategorized prompts.

Reads models/<model>/prompts.json, infers a category for any entry whose
category is "Uncategorized", and writes back to the same file. Idempotent:
re-running is a no-op except for newly added entries.

Run after merge.py:
    python3 scripts/merge.py
    python3 scripts/classify.py
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "gpt-image-2"
OUT_DIR = ROOT / "models" / MODEL
JSON_PATH = OUT_DIR / "prompts.json"
CAT_DIR = OUT_DIR / "by-category"
STATS_PATH = OUT_DIR / "_stats.json"

# Long-tail variants from upstream get normalized into canonical buckets.
NORMALIZE = {
    "architecture": "Architecture",
    "stickers": "Sticker",
    "sticker": "Sticker",
    "diagram": "Infographic",
    "saas": "UI Mockup",
    "editorial": "Editorial",
    "editorial collage": "Editorial",
    "branding": "Logo",
    "beauty": "Portrait",
    "cinematic": "Photography",
    "game": "Game",
    "game scene": "Game",
    "game concept art": "Game",
    "product visual": "Product",
    "packaging": "Product",
    "character sheet": "Character",
    "image editing": "Restyle",
    "copy-paste library": "Copy-Paste Library",
    "worldbuilding": "Worldbuilding",
    "storyboard": "Storyboard",
    "illustration": "Illustration",
}

# Ordered: first match wins. More specific categories must come first.
RULES = [
    ("UI Mockup",       r"\b(ui mockup|ui/ux|ux mockup|app mockup|app screen|landing page|website mockup|web design|wireframe|figma|dashboard mockup|mobile app screen)\b"),
    ("Logo",            r"\b(logo design|brand logo|monogram|wordmark|logotype|emblem|brand identity)\b"),
    ("Icon",            r"\b(icon set|app icon|sticker pack|emoji|ios icon|favicon)\b"),
    ("Infographic",     r"\b(infographic|sketchnote|cross.?section|cutaway diagram|exploded view|technical diagram|periodic table|cheat ?sheet|knowledge map|knowledge graph|how it works|step by step diagram|flow chart|flowchart|data viz|chart breakdown|annotated diagram|annotated illustration)\b"),
    ("Text Rendering",  r"\b(text rendering|typography poster|kinetic typography|lettering|typographic|word cloud|calligraphy|chinese calligraphy|kanji)\b"),
    ("Poster",          r"\b(poster|movie poster|propaganda poster|concert poster|event poster|tour poster|festival poster|anime poster|key visual|theatrical poster|marketing poster|billboard|海报)\b"),
    ("Comic",           r"\b(comic|manga|graphic novel|panel layout|4.?koma|comic strip|webtoon|漫画)\b"),
    ("3D Scene",        r"\b(3d scene|isometric|axonometric|claymation|low.?poly|voxel|miniature world|tiny world|diorama|cinema 4d|blender render|octane render|c4d)\b"),
    ("Photography",     r"\b(hyper.?realistic.*photo|nighttime street photo|street photography|fujifilm|kodak portra|film grain|analog film|polaroid|leica|35mm|cinematic photograph|photorealistic|product photography|food photography|landscape photography|wildlife photo)\b"),
    ("Portrait",        r"\b(portrait|profile picture|head ?shot|self.?portrait|cinematic portrait|fashion portrait|close.?up of (a |the |her|his|my )|人像|肖像)\b"),
    ("Character",       r"\b(character sheet|character design|character reference|turnaround sheet|chibi|mascot|character illustration|hero pose|villain design)\b"),
    ("Anime",           r"\b(anime style|anime illustration|studio ghibli|makoto shinkai|kyoto animation|sailor moon|shonen|shojo|gundam style)\b"),
    ("Sticker",         r"\b(sticker sheet|sticker design|line stickers|telegram sticker|kawaii sticker)\b"),
    ("Product",         r"\b(product packaging|packaging design|product mockup|bottle label|cosmetic packaging|cereal box|product shot|on store shelf)\b"),
    ("Architecture",    r"\b(architecture|architectural|interior design|building elevation|floor plan|cathedral|skyscraper|skyline|brutalist|art deco building)\b"),
    ("Food",            r"\b(food photography|recipe card|menu design|cookbook page|plated dish|latte art|coffee cup|cocktail menu)\b"),
    ("Landscape",       r"\b(landscape painting|mountain range|seascape|aerial view of|wide vista|panoramic landscape|nature photograph)\b"),
    ("Fashion",         r"\b(fashion editorial|runway|lookbook|streetwear|haute couture|fashion shoot|magazine cover|vogue|model wearing)\b"),
    ("Map",             r"\b(physical map|world map|fantasy map|treasure map|subway map|city map|tourist map|map of [a-z])\b"),
    ("Education",       r"\b(coloring book|worksheet|flash ?card|kids book|children'?s book|storybook page|textbook illustration|educational illustration|lesson plan)\b"),
    ("Thumbnail",       r"\b(youtube thumbnail|tiktok cover|video thumbnail|clickbait thumbnail|reel cover|short cover)\b"),
    ("Game",            r"\b(game asset|game ui|video ?game|pixel art game|tile set|game character|rpg portrait|trading card|playing card)\b"),
    ("Meme",            r"\b(meme|wojak|pepe|distracted boyfriend|drake meme|2 ?panel meme)\b"),
    ("Restyle",         r"\b(reference image|recreate.*reference|style transfer|same composition|using the (provided|attached) (reference|image|photo)|using my (reference|photo|portrait)|以我的)\b"),
]


def classify(text: str) -> str:
    if not text:
        return "Uncategorized"
    t = text.lower()
    for label, pattern in RULES:
        if re.search(pattern, t, flags=re.IGNORECASE):
            return label
    return "Uncategorized"


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


def main():
    data = json.load(JSON_PATH.open())
    before = Counter(r["category"] for r in data)

    for r in data:
        n = NORMALIZE.get(r["category"].strip().lower())
        if n:
            r["category"] = n

    changed = 0
    for r in data:
        if r["category"] in ("Uncategorized", "General"):
            inferred = classify(r["prompt"])
            if inferred != "Uncategorized" and inferred != r["category"]:
                r["category"] = inferred
                changed += 1
    after = Counter(r["category"] for r in data)

    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    by_cat = rebuild_by_category(data)
    stats = {
        "model": MODEL,
        "total": len(data),
        "by_category": {k: len(v) for k, v in sorted(by_cat.items(), key=lambda x: -len(x[1]))},
    }
    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2))

    print(f"Reclassified {changed} entries.")
    print()
    print(f"{'Category':<20} {'before':>8} {'after':>8} {'delta':>8}")
    for cat in sorted(set(before) | set(after), key=lambda c: -after.get(c, 0)):
        b, a = before.get(cat, 0), after.get(cat, 0)
        delta = a - b
        sign = "+" if delta > 0 else (" " if delta == 0 else "")
        print(f"{cat:<20} {b:>8} {a:>8}    {sign}{delta}")


if __name__ == "__main__":
    main()
