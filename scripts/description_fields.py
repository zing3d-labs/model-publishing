#!/usr/bin/env python3
"""Reading the generated site-description files.

`scad_builder.py` renders each site's description from templates/<site>_base.md
into a flat "=== FIELD ===" document, e.g.

    === MODEL NAME ===
    openGrid Facade

    === CATEGORY ===
    Organizers

    === DESCRIPTION ===
    ...markdown body...

Every consumer of a built description goes through here, so the format is
parsed in exactly one place: `copy_description.py` (clipboard, for a by-hand
publish) and `makerworld_update.py new-model` (fills the publish form with the
same values).
"""

import re

FIELD_HEADING_RE = re.compile(r'^=== (?P<name>[A-Z0-9 ]+) ===[ \t]*$', re.MULTILINE)


def parse_description_fields(text: str) -> dict[str, str]:
    """Split a generated description into {FIELD NAME: body} pairs."""
    matches = list(FIELD_HEADING_RE.finditer(text))
    fields = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        fields[match.group('name')] = text[match.end():end].strip()
    return fields


def description_body(text: str) -> str:
    """The DESCRIPTION field's markdown, or the whole document for a site
    template that doesn't use field markers (e.g. printables)."""
    return parse_description_fields(text).get('DESCRIPTION', text).strip()


def markdown_to_html(md_text: str) -> str:
    """Render description markdown to the HTML that gets pasted into
    MakerWorld's rich-text editor. Imported lazily so the parsing helpers stay
    usable without the optional `markdown` package installed."""
    try:
        import markdown
    except ImportError:
        raise RuntimeError(
            "The 'markdown' package is required to render a description as rich text. "
            "Install it with: pip install markdown"
        )
    return markdown.markdown(md_text, extensions=['sane_lists'])
