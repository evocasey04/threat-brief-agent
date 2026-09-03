"""Threat Brief Agent — a self-scheduling cybersecurity news digest."""

import sys

__version__ = "1.0.0"


def use_utf8_stdout() -> None:
    """Stop the CLI dying on a smart quote.

    Windows consoles still default to cp1252, so printing a brief that contains
    an em dash or a non-breaking hyphen -- both of which language models emit
    freely, and which real headlines contain -- raised UnicodeEncodeError and
    took the whole command down after the work was already done. Replacing the
    unmappable character is the right trade for a console: the archive file and
    the email are written as UTF-8 regardless.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
