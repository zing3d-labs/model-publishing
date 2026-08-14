#!/usr/bin/env python3
"""Render a built MakerWorld description into a rough visual preview of the listing.

The point is not to look like MakerWorld -- it deliberately does not -- but to show
the copy and the photos in the shape and order they will actually be published, so
they can be reviewed before a browser ever opens.

Its value comes from sharing the publisher's own code path: the description is parsed
with description_fields.parse_description_fields() and converted with
description_fields.markdown_to_html(), which is the same function makerworld_update.py
pastes into CKEditor. So markdown that will not survive the publish does not survive
the preview either -- a list rendering as literal "- " lines here means it renders as
literal "- " lines on the live listing. A hand-drawn mock could not tell you that.

    python3 scripts/preview_listing.py model_pages/opengrid_inbox/build_config.yaml \
        --cover model_pages/opengrid_inbox/images/cover.jpg \
        --photo model_pages/opengrid_inbox/images/front.jpg

--cover and --photo mirror makerworld_update.py's flags exactly, in the same order and
with the same meaning (first --cover is the required 4:3 web cover, a second is the
optional 3:4 app cover), so the preview shows what that command would upload.
"""

import argparse
import base64
import html
import io
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from description_fields import markdown_to_html, parse_description_fields  # noqa: E402
from model_config import load_merged_config, project_slug  # noqa: E402

ROOT_DIR = SCRIPTS_DIR.parent

# Long edge for embedded photos. The preview inlines every image as a data URI so the
# file stands alone, and full-resolution phone shots make that unwieldy fast.
PREVIEW_LONG_EDGE = 1400
PREVIEW_QUALITY = 82

COVER_ROLES = ['Web cover, 4:3 — required', 'App cover, 3:4 — optional']


def resolve_description(config: dict, config_path: Path) -> Path:
    """Locate the built description the same way makerworld_update.py does."""
    site = config.get('templates', {}).get('sites', {}).get('makerworld')
    if not site or not site.get('output_file'):
        raise SystemExit(f"{config_path} has no templates.sites.makerworld.output_file")
    output_dir = config.get('build', {}).get('output_directory', 'dist/')
    path = ROOT_DIR / output_dir / project_slug(config_path, ROOT_DIR) / site['output_file']
    if not path.exists():
        raise SystemExit(
            f"{path} not found. Build it first:\n"
            f"  python3 scripts/scad_builder.py {config_path.relative_to(ROOT_DIR)} -d"
        )
    return path


def embed_image(path: Path) -> tuple[str, str]:
    """Return (data URI, "WxH") for an image, downscaled for preview weight."""
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("Pillow is needed to embed photos: pip install Pillow")

    with Image.open(path) as im:
        native = f"{im.width} x {im.height}"
        im = im.convert('RGB')
        if max(im.size) > PREVIEW_LONG_EDGE:
            scale = PREVIEW_LONG_EDGE / max(im.size)
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format='JPEG', quality=PREVIEW_QUALITY)
    encoded = base64.b64encode(buf.getvalue()).decode('ascii')
    return f"data:image/jpeg;base64,{encoded}", native


def figure(path: Path, role: str, wide: bool = False) -> str:
    uri, native = embed_image(path)
    return f"""      <figure class="shot{' shot--wide' if wide else ''}">
        <img src="{uri}" alt="{html.escape(path.stem)}">
        <figcaption><span class="role">{html.escape(role)}</span>
          <span class="meta">{html.escape(path.name)} · {native}</span></figcaption>
      </figure>"""


def field_rows(fields: dict) -> str:
    rows = []
    for key in ('MODEL NAME', 'LICENSE', 'CATEGORY', 'TAGS', 'SOURCE MODEL URLS'):
        value = fields.get(key)
        if not value:
            continue
        label = 'MODEL ORIGIN' if key == 'SOURCE MODEL URLS' else key
        rows.append(
            f'        <div class="row"><dt>{html.escape(label.title())}</dt>'
            f'<dd>{html.escape(value.strip())}</dd></div>'
        )
    return '\n'.join(rows)


def build_page(config: dict, fields: dict, covers: list[Path], photos: list[Path],
               config_path: Path) -> str:
    name = fields.get('MODEL NAME', config['project'].get('name', 'Untitled'))
    body = markdown_to_html(fields.get('DESCRIPTION', ''))
    profile_name = fields.get('PRINT PROFILE NAME', '')
    profile_desc = fields.get('PRINT PROFILE DESCRIPTION', '')

    gallery = [figure(c, COVER_ROLES[i] if i < len(COVER_ROLES) else 'Extra cover', wide=(i == 0))
               for i, c in enumerate(covers)]
    gallery += [figure(p, f'Model picture {i}') for i, p in enumerate(photos, start=1)]
    if not gallery:
        gallery = ['      <p class="empty">No photos passed. MakerWorld rejects a listing '
                   'with no real photo, so a publish with none can only reach draft.</p>']

    profile_block = ''
    if profile_name:
        lines = ''.join(
            f'<li>{html.escape(l.lstrip("· ").strip())}</li>'
            for l in profile_desc.splitlines() if l.strip().startswith('·')
        )
        notes = ' '.join(l.strip() for l in profile_desc.splitlines()
                         if l.strip() and not l.strip().startswith('·'))
        profile_block = f"""
    <section class="profile">
      <h2 class="eyebrow">Print profile</h2>
      <p class="profile-name">{html.escape(profile_name)}</p>
      <ul class="settings">{lines}</ul>
      {f'<p class="profile-note">{html.escape(notes)}</p>' if notes else ''}
    </section>"""

    return f"""<title>{html.escape(name)} Listing Preview</title>
<style>
  :root {{
    --ground: #faf9f7;
    --surface: #ffffff;
    --ink: #1b1f23;
    --muted: #5c6b6e;
    --rule: #e5e2dc;
    --accent: #0f7a63;
    --accent-soft: #e6f2ee;
    --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    --serif: "Iowan Old Style", Georgia, "Times New Roman", serif;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --ground: #101413;
      --surface: #171c1b;
      --ink: #e9edeb;
      --muted: #93a19e;
      --rule: #262e2c;
      --accent: #4fc3a5;
      --accent-soft: #14312b;
    }}
  }}
  :root[data-theme="dark"] {{
    --ground: #101413;
    --surface: #171c1b;
    --ink: #e9edeb;
    --muted: #93a19e;
    --rule: #262e2c;
    --accent: #4fc3a5;
    --accent-soft: #14312b;
  }}

  body {{
    margin: 0;
    background: var(--ground);
    color: var(--ink);
    font-family: var(--sans);
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{
    max-width: 1080px;
    margin: 0 auto;
    padding: 2rem 1.5rem 5rem;
    display: flex;
    flex-direction: column;
    gap: 2.5rem;
  }}
  .banner {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 1rem;
    align-items: baseline;
    padding: 0.75rem 1rem;
    border: 1px solid var(--rule);
    border-left: 3px solid var(--accent);
    background: var(--accent-soft);
    border-radius: 2px;
    font-size: 0.8125rem;
    color: var(--muted);
  }}
  .banner strong {{ color: var(--ink); font-weight: 600; }}
  .banner code {{ font-family: var(--mono); font-size: 0.9em; }}

  h1 {{
    font-family: var(--serif);
    font-size: clamp(1.9rem, 4vw, 2.6rem);
    line-height: 1.1;
    margin: 0;
    text-wrap: balance;
    letter-spacing: -0.01em;
  }}
  .eyebrow {{
    font-size: 0.6875rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 600;
    margin: 0 0 0.75rem;
  }}

  .split {{ display: grid; grid-template-columns: 1.35fr 1fr; gap: 2.5rem; align-items: start; }}
  @media (max-width: 860px) {{ .split {{ grid-template-columns: 1fr; }} }}

  .gallery {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
  .shot--wide {{ grid-column: 1 / -1; }}
  .shot {{ margin: 0; display: flex; flex-direction: column; gap: 0.5rem; }}
  .shot img {{
    width: 100%;
    display: block;
    border: 1px solid var(--rule);
    border-radius: 2px;
    background: var(--surface);
  }}
  figcaption {{ display: flex; flex-direction: column; gap: 0.125rem; font-size: 0.75rem; }}
  .role {{ color: var(--accent); font-weight: 600; }}
  .meta {{ color: var(--muted); font-family: var(--mono); font-size: 0.6875rem; }}

  .fields {{ margin: 0; display: flex; flex-direction: column; gap: 0; }}
  .row {{ display: flex; flex-direction: column; gap: 0.25rem; padding: 0.75rem 0; border-bottom: 1px solid var(--rule); }}
  .row dt {{ font-size: 0.6875rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); font-weight: 600; }}
  .row dd {{ margin: 0; font-family: var(--mono); font-size: 0.8125rem; overflow-wrap: anywhere; }}

  .body {{ max-width: 68ch; font-family: var(--serif); font-size: 1.0625rem; }}
  .body h2 {{
    font-family: var(--sans);
    font-size: 0.9375rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 2.25rem 0 0.5rem;
    padding-bottom: 0.375rem;
    border-bottom: 1px solid var(--rule);
  }}
  .body h2:first-child {{ margin-top: 0; }}
  .body p {{ margin: 0 0 1rem; }}
  .body ul {{ margin: 0 0 1rem; padding-left: 1.25rem; }}
  .body li {{ margin-bottom: 0.375rem; }}
  .body code {{ font-family: var(--mono); font-size: 0.875em; background: var(--accent-soft); padding: 0.1em 0.3em; border-radius: 2px; }}
  .body a {{ color: var(--accent); }}

  .profile {{ border: 1px solid var(--rule); background: var(--surface); border-radius: 2px; padding: 1.25rem 1.5rem; max-width: 68ch; }}
  .profile-name {{ font-family: var(--mono); font-size: 0.9375rem; margin: 0 0 0.75rem; }}
  .settings {{ margin: 0; padding-left: 1.1rem; font-size: 0.9375rem; }}
  .profile-note {{ color: var(--muted); font-size: 0.875rem; margin: 0.75rem 0 0; }}
  .empty {{ color: var(--muted); font-style: italic; }}
</style>

<div class="wrap">
  <div class="banner">
    <strong>Local preview.</strong>
    <span>Not MakerWorld, and nothing here is published. Copy rendered through
      <code>description_fields.markdown_to_html()</code> — the same conversion the publisher
      pastes into the editor — so what fails to format here fails there too.</span>
    <span><code>{html.escape(str(config_path.relative_to(ROOT_DIR)))}</code></span>
  </div>

  <div class="split">
    <div>
      <h2 class="eyebrow">Photos, in upload order</h2>
      <div class="gallery">
{chr(10).join(gallery)}
      </div>
    </div>
    <div>
      <h1>{html.escape(name)}</h1>
      <dl class="fields">
{field_rows(fields)}
      </dl>
    </div>
  </div>

  <section>
    <h2 class="eyebrow">Description</h2>
    <div class="body">
{body}
    </div>
  </section>
{profile_block}
</div>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('config', type=Path, help='model_pages/<model>/build_config.yaml')
    parser.add_argument('--cover', action='append', default=[], metavar='PATH',
                        help='Cover image; first is the 4:3 web cover, second the 3:4 app cover')
    parser.add_argument('--photo', action='append', default=[], metavar='PATH',
                        help='Model picture, repeatable, shown in the order given')
    parser.add_argument('-o', '--output', type=Path,
                        help='Where to write the HTML (default: dist/<slug>/listing_preview.html)')
    args = parser.parse_args()

    config_path = args.config.resolve()
    config, _ = load_merged_config(config_path)
    fields = parse_description_fields(resolve_description(config, config_path).read_text())

    covers = [Path(p).resolve() for p in args.cover]
    photos = [Path(p).resolve() for p in args.photo]
    for image in covers + photos:
        if not image.exists():
            raise SystemExit(f"Image not found: {image}")

    output = args.output or (
        ROOT_DIR / 'dist' / project_slug(config_path, ROOT_DIR) / 'listing_preview.html'
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_page(config, fields, covers, photos, config_path))
    print(f"Wrote {output} ({output.stat().st_size / 1024:.0f} KB, "
          f"{len(covers)} cover(s), {len(photos)} photo(s))")


if __name__ == '__main__':
    main()
