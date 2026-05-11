# SPDX-License-Identifier: AGPL-3.0-or-later

"""XML boundary marker assembly — spec 026 FR-012.

Compressed segments wrap their output in an XML boundary marker so
downstream consumers can see that the region is compressed-derived
and recover the compressor + version + source-trust-tier metadata
without round-tripping the per-dispatch compression_log row.

The 4-tier prompt text and tool definitions are priority tier 1
(FR-014, never compressed) and never appear inside these markers.
"""

from __future__ import annotations

from xml.sax.saxutils import quoteattr


def wrap(
    text: str,
    source_tier: str,
    compressor_id: str,
    compressor_version: str,
) -> str:
    """Return `text` wrapped in a `<compressed ...>...</compressed>` marker.

    Attributes are XML-quoted via `quoteattr` so the rendered marker
    is well-formed XML even if the inputs contain unusual characters.
    `text` is NOT escaped — compressors are responsible for their own
    output sanitisation per the spec 007 trust-tier model.
    """
    return (
        f"<compressed"
        f" source-tier={quoteattr(source_tier)}"
        f" compressor={quoteattr(compressor_id)}"
        f" version={quoteattr(compressor_version)}>"
        f"{text}"
        f"</compressed>"
    )
