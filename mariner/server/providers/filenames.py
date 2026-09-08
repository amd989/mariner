"""Filename handling shared by the network print providers.

Providers receive a filename from a client, store a file under it, and are
later asked to print or delete it by that same name. Those names therefore
have to survive the round trip unchanged.
"""

from typing import Optional

# Characters that would let a name escape the files directory, or that the
# filesystem call itself cannot carry.
_FORBIDDEN = ("/", "\\", "\x00", "\r", "\n")


def safe_filename(filename: str) -> Optional[str]:
    """The client's filename, preserved, or None if it is not safe to use.

    Deliberately not ``werkzeug.secure_filename``. That rewrites the name:
    it strips parentheses, collapses spaces, and drops non-ASCII entirely.
    A client that uploads ``model_6(1).ctb`` and then asks to print it under
    that name finds nothing, because the stored file is ``model_61.ctb``.
    Validating and rejecting instead of rewriting keeps exactly one name in
    play across upload, listing, printing and deletion.

    This is not on its own sufficient to contain a path: callers must still
    confirm the resolved path stays inside the files directory.
    """
    name = (filename or "").strip()
    if not name or name in (".", ".."):
        return None
    if any(character in name for character in _FORBIDDEN):
        return None
    return name
