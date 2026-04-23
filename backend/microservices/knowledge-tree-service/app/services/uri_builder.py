"""
URIBuilder — canonical URI generation for TrustGraph entities.

URI scheme:
  Entities:       nouxcube://entity/{collection}/{normalized-name}
  Documents:      nouxcube://document/{collection}/{document_id}
  Folders:        nouxcube://folder/{collection}/{path_hash_16chars}
  Predicates:     nouxcube://predicate/{ontology}/{predicate_name}
  Extractions:    nouxcube://extraction/{uuid}
  DB rows:        nouxcube://dbrow/{connector_id}/{table}/{pk}
  Contradictions: nouxcube://contradiction/{uuid}

No external dependencies — stdlib only.
"""

import hashlib
import re
import unicodedata
import uuid


class URIBuilder:
    """Stateless factory for canonical nouxcube:// URIs."""

    SCHEME = "nouxcube://"

    # ---------------------------------------------------------------------------
    # Public classmethods
    # ---------------------------------------------------------------------------

    @classmethod
    def entity(cls, collection: str, name: str) -> str:
        """Return a canonical entity URI.

        Raises ValueError if *name* is empty or whitespace-only after stripping.
        """
        normalized = cls.normalize_name(name)
        if not normalized:
            raise ValueError(
                f"entity name cannot be empty; got {name!r}"
            )
        return f"{cls.SCHEME}entity/{collection}/{normalized}"

    @classmethod
    def document(cls, collection: str, document_id: str) -> str:
        """Return a canonical document URI.  document_id case is preserved."""
        return f"{cls.SCHEME}document/{collection}/{document_id}"

    @classmethod
    def chunk(cls, collection: str, document_id: str, chunk_offset: int) -> str:
        """Return a canonical chunk URI.

        Chunks are first-class :Chunk nodes in FalkorDB; one URI per
        (document, offset) pair. The colon separator was chosen instead of
        the legacy '#offset=' fragment syntax so the URI is a clean
        hierarchical identifier — matches the document/{id} pattern so that
        chunks sort naturally alongside their parent.
        """
        return f"{cls.SCHEME}chunk/{collection}/{document_id}:{chunk_offset}"

    @classmethod
    def folder(cls, collection: str, path: str) -> str:
        """Return a canonical folder URI using the first 16 hex chars of SHA-256(path)."""
        path_hash = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
        return f"{cls.SCHEME}folder/{collection}/{path_hash}"

    @classmethod
    def predicate(cls, ontology: str, predicate_name: str) -> str:
        """Return a canonical predicate URI."""
        return f"{cls.SCHEME}predicate/{ontology}/{predicate_name}"

    @classmethod
    def extraction(cls) -> str:
        """Return a new, unique extraction URI backed by a random UUID."""
        return f"{cls.SCHEME}extraction/{uuid.uuid4()}"

    @classmethod
    def dbrow(cls, connector_id: str, table: str, pk: str) -> str:
        """Return a canonical DB-row URI."""
        return f"{cls.SCHEME}dbrow/{connector_id}/{table}/{pk}"

    @classmethod
    def contradiction(cls) -> str:
        """Return a new, unique contradiction URI backed by a random UUID."""
        return f"{cls.SCHEME}contradiction/{uuid.uuid4()}"

    # ---------------------------------------------------------------------------
    # Name normalization
    # ---------------------------------------------------------------------------

    # ---------------------------------------------------------------------------
    # Spanish name particles (prepositions kept but not reordered)
    # ---------------------------------------------------------------------------

    _COMMA_NAME_RE = re.compile(
        r"^([^,]+),\s*(.+)$"
    )

    # Honorific prefixes to strip (matched at start of name, case-insensitive).
    # Abbreviations (D., Dña., Dr., Dra., Sr., Sra.) require a trailing period.
    # Full words (Don, Doña) require a trailing space.
    _HONORIFIC_RE = re.compile(
        r"^(?:d(?:ña|ra|r)?|sra?)\.\s*|^(?:don|doña)\s+",
        re.IGNORECASE,
    )

    # Corporate suffixes to strip (matched at end of name, case-insensitive).
    # Requires word boundary before suffix to avoid false positives like "Basel".
    _CORPORATE_SUFFIX_RE = re.compile(
        r"\s*\b(?:s\.?l\.?u?\.?|s\.?a\.?|s\.?c\.?)\.?\s*$",
        re.IGNORECASE,
    )

    @classmethod
    def normalize_name(cls, name: str) -> str:
        """Normalize a human-readable name to a URI-safe slug.

        Steps:
        0. Reorder "Last, First" → "First Last" (comma-separated names).
        1. NFD decompose and strip combining marks (removes accents, ñ → n, etc.)
        2. Lowercase.
        3. Replace runs of non-alphanumeric characters with a single hyphen.
        4. Strip leading/trailing hyphens.

        Examples:
            "García, Juan"       → "juan-garcia"
            "Juan García"        → "juan-garcia"
            "De la Cruz, José"   → "jose-de-la-cruz"
            "Empresa ABC, S.L."  → "empresa-abc-s-l"  (comma in company name, no reorder)
        """
        stripped = name.strip()

        # 0. Detect and reorder "Last, First" patterns
        # Heuristic: if the part after the comma starts with a capitalized
        # word that looks like a first name (no digits, short enough), reorder.
        m = cls._COMMA_NAME_RE.match(stripped)
        if m:
            before_comma = m.group(1).strip()
            after_comma = m.group(2).strip()
            # Reorder if after-comma looks like a first name:
            # - no digits
            # - at most 4 words (e.g., "José María de la")
            # - not typical company suffixes
            _company_suffixes = {"s.l.", "s.a.", "s.l.u.", "inc", "ltd", "gmbh", "corp"}
            after_lower = after_comma.lower()
            if (
                not any(ch.isdigit() for ch in after_comma)
                and len(after_comma.split()) <= 4
                and after_lower not in _company_suffixes
            ):
                stripped = f"{after_comma} {before_comma}"

        # 0b. Strip honorific prefixes (D., Don, Dña., Dr., Dra., Sr., Sra.)
        stripped = cls._HONORIFIC_RE.sub("", stripped).strip()

        # 0c. Strip corporate suffixes (S.L., S.A., S.L.U., S.C.)
        stripped = cls._CORPORATE_SUFFIX_RE.sub("", stripped).strip()

        # 1. NFD + strip combining marks
        nfd = unicodedata.normalize("NFD", stripped)
        ascii_approx = "".join(
            ch for ch in nfd if unicodedata.category(ch) != "Mn"
        )
        # 2. Lowercase
        lowered = ascii_approx.lower()
        # 3. Replace non-alphanumeric runs with hyphen
        hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered)
        # 4. Strip leading/trailing hyphens
        return hyphenated.strip("-")
