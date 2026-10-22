# Loomwell vector workflow

Original Loomwell templates, palette and an export launcher for the VectorCraft engine. This is a workflow add-on; it does not rebrand or modify the upstream application.

## Export

From this fork's repository root:

```sh
python3 loomwell/export.py list
python3 loomwell/export.py export website --output ./out/loomwell
python3 loomwell/export.py export social --output ./out/loomwell
python3 loomwell/export.py export square --output ./out/loomwell
python3 loomwell/export.py export all --output ./out/loomwell
```

The launcher finds `target/release/vectorcraft-cli`, Loomwell's maintained per-app build directory, or `vectorcraft-cli` on PATH. A standalone checkout can select any compatible local build explicitly:

```sh
python3 loomwell/export.py export all --output ./out/loomwell \
  --cli /absolute/path/to/vectorcraft-cli
```

Python's standard library is sufficient. There are no model API calls, accounts, downloads, or Atlas imports. Existing personal editor preferences are disabled for the headless export.

## Templates and files

| ID | Canvas | Purpose |
| --- | --- | --- |
| `website` | 1600 × 900 | Website hero artwork with a caption, button treatment and woven illustration |
| `social` | 1200 × 630 | Landscape social / Open Graph image |
| `square` | 1080 × 1080 | Square social post |

Each export writes named `.svg`, `.png`, `.pdf` and editable `.vectorcraft` files, plus the authoring `.source.svg`. `manifest.json` records dimensions, renderer version, palette, copy and SHA-256 digests. These are design assets, not a functional website or an interactive HTML component.

The checked-in `templates/` masters can be opened directly in VectorCraft. Text stays live in the bundled Source Serif 4 and Source Sans 3 fonts; woven bands stay editable paths. Native documents include four named global Loomwell swatches. SVG output keeps text editable, so a website using it should provide those fonts, outline type through VectorCraft, or choose bundled PNG output when exact typography is required.

## Brand and copy

Edit `brand.json` to change the four primary colors: forest `#182822`, paper `#f5f2e9`, sage `#d5e5b3`, terracotta `#b86e4d`. `templates/loomwell.vcswatches` is an importable native library with named global colors and a Loomwell group; `templates/loomwell.gpl` is a portable RGB palette. The launcher regenerates both beside every export. Load either through VectorCraft's Swatch Libraries menu.

Edit `content.json`, or pass a partial override:

```sh
python3 loomwell/export.py export social --output ./out/campaign \
  --content ./my-copy.json
```

```json
{
  "headline": "See the context.\nKeep the correction.",
  "subheadline": "Reviewed ecommerce agent examples\nfor training and evaluation.",
  "eyebrow": "ECOMMERCE AGENT EXPERIENCE",
  "footer": "RETURNS / EXCHANGES / REFUNDS"
}
```

Supported keys are `headline`, `subheadline`, `eyebrow`, `footer`, `call_to_action`, `status` and `site`. Unknown keys fail clearly. Headline is limited to two lines of 24 characters; subheadline to two lines of 55 characters. Other copy has bounded lengths. The exporter also checks the engine's actual text bounds against the canvas and copy columns, so wide glyphs can require shorter copy even within the character limit. Line breaks are explicit. XML-sensitive text is escaped by the authoring code.

Exports are rendered and checked in a temporary staging directory. A failed render, font check or text overflow leaves the previous delivery intact; successful files are installed with the manifest last.

Default copy describes Loomwell's early pilot. It claims no customers, revenue, guaranteed earnings, or measured model improvements. The illustration is original geometry and contains no customer records.

## Verify

```sh
VECTORCRAFT_CLI=/absolute/path/to/vectorcraft-cli \
  python3 -m unittest discover -s loomwell -p 'test_*.py'
```

The tests export all three templates, verify dimensions and file digests, inspect exact font resolution and live text, reopen a native master, and exercise portable-copy/content-error handling. A wide-glyph overflow test verifies that a failed export preserves the previous delivery. The repository-wide gate is `cargo xtask ci`; its result depends on the full upstream development prerequisites as well as this add-on.

Code and original artwork in this pack are available under MIT OR Apache-2.0, following this fork's code license. See the license texts alongside this file. Existing upstream application notices and its separate ArtCraft brand terms remain in force; this pack contains no ArtCraft marks and does not imply endorsement.
