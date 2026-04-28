# image-prompt-vault

A curated, model-organized vault of AI image-generation prompts.

Each model gets its own folder. Prompts are aggregated from public upstream sources, deduped, normalized into a single schema, and split by category for browsing. As new image models ship, drop a new folder under `models/`, write a loader in `scripts/merge.py`, and re-run.

## Structure

```
image-prompt-vault/
├── models/
│   └── gpt-image-2/
│       ├── prompts.json      # full merged dataset (canonical)
│       ├── prompts.csv       # spreadsheet view
│       ├── _stats.json       # counts per upstream / per category
│       └── by-category/      # per-category .md files for browsing
├── scripts/
│   └── merge.py              # one-shot aggregator, re-run anytime
└── NOTICE.md                 # attribution + takedown policy
```

## Schema (one row per prompt)

| field | meaning |
|---|---|
| `id` | 12-char fingerprint of normalized prompt text (stable dedup key) |
| `prompt` | the full prompt text |
| `title` | short label (when upstream provided) |
| `category` | normalized bucket (Poster / Portrait / UI Mockup / 3D Scene / ...) |
| `language` | `en` / `zh` / etc. |
| `quality` | A / B / C grade (only when upstream provided) |
| `author` | original creator handle (e.g. `@dotey`, `@BubbleBrain`) |
| `source_url` | original post URL (X / Reddit / etc.) |
| `image_url` | preview image URL on upstream CDN (NOT vendored locally) |
| `published_at` | original post date |
| `upstream_repo` | which awesome-* repo this came from |
| `upstream_channel` | upstream's source label |

## Adding a new model

1. `mkdir models/<model-slug>`
2. Add a `load_<source>()` function in `scripts/merge.py` for each upstream source for that model.
3. Run `python3 scripts/merge.py`.
4. Commit + push.

## Current dataset (gpt-image-2)

See `models/gpt-image-2/_stats.json` for live counts.

## Sources & License

Prompts in this repo are aggregated from publicly visible posts and curated awesome-* repos. Original `author` and `source_url` fields are preserved on every entry.

If you are a prompt author and want your work removed or re-attributed, open an issue. See `NOTICE.md`.

This repo's tooling (Python scripts, structure, README) is MIT. The aggregated prompts themselves remain the property of their original authors.
