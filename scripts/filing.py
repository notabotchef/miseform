"""Idempotent authorized filing adapter for Miseform recipe cards.

Stages reviewed card exports into a dish folder beside the same recipe and
version, persists a deterministic retry key so an interrupted run can resume,
and verifies every artifact by reading it back before reporting it filed.

Remote library/Drive writes stay pending in this release: the package ships
no library client and no credentials, so no remote write is attempted, no
existing Drive ID is replaced or regenerated, and no recipe is mutated.
Nothing is filed without explicit authorization.

Usage:

    python3 scripts/filing.py <card.json> <exports-dir> [--authorize] [--destination DIR]

``exports-dir`` is the folder ``build_card.py`` wrote into; the adapter finds
the edition files by the card's shared versioned stem.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_manifest import verify_manifest, file_hash
from card_model import Card, format_weight  # noqa: E402
from render_html import render_html  # noqa: E402
from render_markdown import render_markdown  # noqa: E402

PENDING_DIR_NAME = ".miseform-pending"
RECEIPT_NAME = "receipt.json"

# A Drive-style file identifier as it might already be recorded on a card:
# a long opaque alphanumeric token with dashes and underscores. The adapter
# preserves identifiers it finds; it never creates one.
_DRIVE_ID_RE = re.compile(r"\b[A-Za-z0-9._-]{28,}\b")

# Statuses a filing run can report.
PENDING = "pending"
VERIFIED = "verified"
FAILED = "failed"


@dataclass
class StagedArtifact:
    """One staged export and the result of reading it back."""

    kind: str
    path: Path | None = None
    ok: bool = False
    verified: bool = False
    detail: str = ""
    content_hash: str = ""


@dataclass
class FilingResult:
    """Outcome of one authorized filing attempt."""

    status: str
    retry_key: str
    dish_folder: Path | None = None
    artifacts: list[StagedArtifact] = field(default_factory=list)
    preserved_ids: list[str] = field(default_factory=list)
    remote_status: str = PENDING
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == VERIFIED


# ---------------------------------------------------------------- identity keys


def content_digest(card: Card) -> str:
    """Digest of the canonical card record: recipe identity plus content.

    Remote IDs, timestamps and receipt fields are never part of the key, so
    a re-filing of the same reviewed card reproduces the same key and the
    same pending operation is resumed instead of duplicated.
    """
    record = json.dumps(card.data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(record).hexdigest()


def retry_key(recipe_id: str, version: str, digest: str) -> str:
    """Deterministic retry key from recipe identity, version and content."""
    material = f"{recipe_id}\n{version}\n{digest}\n".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


# ---------------------------------------------------------------- layout


def _slugify(text: str) -> str:
    out: list[str] = []
    for ch in str(text).strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "-", "_", "/"}:
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "recipe"


def dish_folder(card: Card, destination: Path) -> Path:
    """The folder one dish's exports live under: ``RECIPE-ID__dish-slug``."""
    return destination / f"{card.recipe_id}__{_slugify(card.title)}"


def edition_paths(card: Card, exports_dir: Path) -> dict[str, Path]:
    """Locate the built editions by their shared versioned stem."""
    stem = card.filename_stem
    return {
        "markdown": exports_dir / f"{stem}.md",
        "html": exports_dir / f"{stem}.html",
        "json": exports_dir / f"{stem}.json",
        "pdf": exports_dir / f"{stem}.pdf",
        "xlsx": exports_dir / f"{stem}.xlsx",
    }


# ---------------------------------------------------------------- readback


def _pdf_text(path: Path) -> str:
    """Extract the PDF's text layer, best effort. Returns ``''`` when no
    extractor is available or the file is not a readable PDF.
    """
    if shutil.which("pdftotext"):
        try:
            out = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if out.returncode == 0:
                return out.stdout
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def _subsequence(phrase: str, text: str) -> bool:
    """True when every whitespace-separated word of ``phrase`` appears in
    ``text`` in the same relative order.

    PDF text extraction interleaves list-item number spans and wraps long
    paragraphs, so a step's words can arrive with extra tokens between them.
    Subsequence matching still binds the full step wording while tolerating
    that interleaving; a stale method with different wording will not match.
    """
    words = phrase.split()
    if not words:
        return True
    tokens = text.split()
    i = 0
    for tok in tokens:
        if tok == words[i]:
            i += 1
            if i == len(words):
                return True
    return False


def _mass_in_text(label: str, text: str) -> bool:
    """True when the PDF text layer carries this mass.

    PDF text extraction wraps a table row across columns and can drop the
    space between a number and its unit ("2 g" arrives as "2 g" with the
    space collapsed). The number is matched on its own boundary so a longer
    number cannot satisfy a shorter row's mass.
    """
    number, _, unit = label.rpartition(" ")
    if not number:
        return label in text
    pattern = rf"(?<![\d.]){re.escape(number)}\s*{re.escape(unit)}(?!\w)"
    return re.search(pattern, text) is not None


def _verify_pdf(path: Path, card: Card) -> tuple[bool, str]:
    """Re-read the PDF and confirm it carries this card's full canonical
    content, not just its identity and established ingredient masses. A stale
    PDF (obsolete method, same id/version/title/masses) must fail even when
    every other edition matches the current card, so a mixed content set
    never reports verified.
    """
    text = " ".join(_pdf_text(path).split())
    if not text:
        return False, "PDF text layer could not be read"
    if not (
        card.recipe_id in text
        and card.version in text
        and card.title in text
    ):
        return False, "PDF text layer lacks the recipe identity"
    resolved = card.resolved_weights()
    missing: list[str] = []
    for row_id, weight in resolved.items():
        if isinstance(weight, (int, float)):
            label = format_weight(weight)
            if not _mass_in_text(label, text):
                missing.append(f"{row_id} {label}")
    if missing:
        return (
            False,
            "PDF text layer does not carry the established masses: "
            + ", ".join(missing),
        )
    for step in card.steps:
        step_text = str(step.get("text", "")).strip()
        if step_text and not _subsequence(step_text, text):
            return (
                False,
                f"PDF text layer does not carry method step {step.get('number')}",
            )
    for ing in card.ingredients:
        name = str(ing.get("name", "")).strip()
        # A long name wraps across the table row, so the other columns'
        # values arrive between the name's words. The name is matched as an
        # ordered word sequence, the same tolerance the method steps use.
        if name and not _subsequence(name, text):
            return False, f"PDF text layer does not carry ingredient {ing.get('row_id')}"
    allergens = str(card.data.get("allergens", "")).strip()
    if allergens and allergens not in text:
        return False, "PDF text layer does not carry the allergen declaration"
    status = card.status
    if status and status not in text:
        return False, "PDF text layer does not carry the card status"
    return True, "PDF text-layer sanity checks passed"


def _verify_json(path: Path, card: Card) -> tuple[bool, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"JSON edition could not be read back: {exc}"
    if data == card.data:
        return True, "card record read back and content matches exactly"
    return False, "JSON edition does not match the current card record"


def _verify_rendered(path: Path, card: Card, expected: str, kind: str) -> tuple[bool, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"{kind} edition could not be read back: {exc}"
    if text == expected:
        return True, f"{kind} edition read back and content matches the card"
    return False, f"{kind} edition does not match the current card content"


def _verify_workbook(path: Path, card: Card) -> tuple[bool, str]:
    """Re-read the workbook and confirm it carries this card's established
    ingredient masses plus its canonical content (method steps, allergens,
    status), not just the recipe identity.
    """
    import openpyxl  # type: ignore

    try:
        wb = openpyxl.load_workbook(path)
    except Exception as exc:
        return False, f"workbook could not be read back: {exc}"
    sheet_text = "\n".join(
        str(c.value)
        for ws in wb.worksheets
        for row in ws.iter_rows()
        for c in row
        if c.value is not None
    )
    if card.recipe_id not in sheet_text or card.version not in sheet_text:
        return False, "workbook lacks the recipe identity"
    resolved = card.resolved_weights()
    sheet = wb["Recipe Card"]
    for row in sheet.iter_rows(min_col=2, max_col=2):
        value = row[0].value
        if not isinstance(value, str) or " · " not in value:
            continue
        row_id = value.split(" · ", 1)[0]
        if row_id not in resolved:
            continue
        weight = resolved[row_id]
        if weight is None:
            continue
        weight_cell = sheet.cell(row=row[0].row, column=3)
        cell_value = weight_cell.value
        if not isinstance(cell_value, (int, float)) or not math.isclose(
            float(cell_value), float(weight), abs_tol=1e-6
        ):
            return False, f"workbook weight for row {row_id} does not match the card"
    for step in card.steps:
        step_text = str(step.get("text", "")).strip()
        if step_text and step_text not in sheet_text:
            return (
                False,
                f"workbook does not carry method step {step.get('number')}",
            )
    allergens = str(card.data.get("allergens", "")).strip()
    if allergens and allergens not in sheet_text:
        return False, "workbook does not carry the allergen declaration"
    status = card.status
    if status and status not in sheet_text:
        return False, "workbook does not carry the card status"
    return True, "workbook content sanity checks passed"


def readback_verify(path: Path, card: Card) -> tuple[bool, str]:
    """Perform format and rendered-content sanity readback.

    This standalone helper does not establish full-record integrity. Authorized
    filing also requires build_manifest verification and staged byte hashes;
    PDF/workbook text checks alone cannot cover every canonical field.
    """
    try:
        if not path.exists():
            return False, "staged artifact is missing"
        if path.stat().st_size == 0:
            return False, "staged artifact is empty"
        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            return _verify_workbook(path, card)
        if suffix == ".pdf":
            return _verify_pdf(path, card)
        if suffix == ".json":
            return _verify_json(path, card)
        if suffix == ".md":
            return _verify_rendered(path, card, render_markdown(card), "Markdown")
        if suffix == ".html":
            return _verify_rendered(
                path,
                card,
                render_html(card, theme=card.data.get("theme")),
                "HTML",
            )
        text = path.read_text(encoding="utf-8", errors="replace")
        if card.recipe_id in text and card.version in text:
            return True, "artifact read back and identity confirmed"
        return False, "artifact lacks the recipe identity"
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, f"readback failed: {exc}"


# ---------------------------------------------------------------- pending state


def _pending_dir(destination: Path) -> Path:
    return destination / PENDING_DIR_NAME


def _state_path(pending_dir: Path, retry_key_value: str) -> Path:
    return pending_dir / f"{retry_key_value}.json"


def _load_state(pending_dir: Path, retry_key_value: str) -> dict[str, Any] | None:
    path = _state_path(pending_dir, retry_key_value)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_state(pending_dir: Path, state: dict[str, Any]) -> None:
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = _state_path(pending_dir, str(state["retry_key"]))
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- filing


def _preserved_ids(card: Card) -> list[str]:
    """Drive-style identifiers already recorded on the card, carried forward.

    The adapter preserves them verbatim and never mints a replacement.
    """
    found: list[str] = []
    note = str((card.data.get("provenance") or {}).get("filing", ""))
    for match in _DRIVE_ID_RE.findall(note):
        if match not in found:
            found.append(match)
    return found


def _stage_artifact(
    kind: str, source: Path, dish: Path, card: Card
) -> StagedArtifact:
    if not source.exists():
        return StagedArtifact(kind=kind, ok=False, detail="built export is missing")
    target = dish / source.name
    try:
        shutil.copy2(source, target)
    except OSError as exc:
        return StagedArtifact(kind=kind, ok=False, detail=f"could not stage {kind}: {exc}")
    ok, reason = readback_verify(target, card)
    content_hash = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else ""
    return StagedArtifact(
        kind=kind,
        path=target,
        ok=ok,
        verified=ok,
        detail=reason,
        content_hash=content_hash,
    )


def _bound_readback(path: Path, card: Card, manifest: dict, expected_hash: str) -> tuple[bool, str]:
    """Byte agreement supplies content binding; format readback supplies sanity."""
    try:
        if file_hash(path) != expected_hash:
            return False, "staged artifact differs from build manifest"
        settings = manifest["settings"]
        texts = manifest["translation"]
        if path.suffix == ".md":
            return _verify_rendered(path, card, render_markdown(
                card, language=settings["language"], texts=texts), "Markdown")
        if path.suffix == ".html":
            return _verify_rendered(path, card, render_html(
                card, theme=settings["theme"], language=settings["language"], texts=texts), "HTML")
        if texts and path.suffix == ".pdf":
            text = _pdf_text(path)
            return (bool(text and card.recipe_id in text and card.version in text),
                    "PDF text-layer identity sanity check; content bound by build hash")
        if texts and path.suffix == ".xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(path)
            text = " ".join(str(cell.value) for ws in wb for row in ws for cell in row)
            wb.close()
            return (card.recipe_id in text and card.version in text,
                    "workbook identity sanity check; content bound by build hash")
        return readback_verify(path, card)
    except Exception as exc:
        return False, f"bound readback failed: {exc}"


def file_card(
    card: Card,
    exports_dir: Path | str,
    *,
    authorized: bool = False,
    destination: Path | str | None = None,
) -> FilingResult:
    """File ``card``'s exports from ``exports_dir`` into ``destination``.

    ``authorized`` must be True for anything to be written. Without it the
    run reports pending and creates nothing — a draft stays local until the
    cook authorizes filing.

    Remote filing (Drive/library) is not implemented in this release: no
    client and no credentials ship here. Any Drive-like identifier already
    recorded on the card is preserved verbatim, and the remote operation is
    reported pending with its reason instead of fabricated.
    """
    exports_dir = Path(exports_dir)
    destination = Path(destination) if destination else exports_dir / "staging"
    paths = edition_paths(card, exports_dir)
    digest = content_digest(card)
    key = retry_key(card.recipe_id, card.version, digest)
    pending_dir = _pending_dir(destination)
    existing = _load_state(pending_dir, key)

    if not authorized:
        return FilingResult(
            status=PENDING,
            retry_key=key,
            detail=(
                "no filing authorization; the artifact stays local and no "
                "remote write is attempted"
            ),
            remote_status=PENDING,
            preserved_ids=_preserved_ids(card),
        )

    manifest, integrity_errors = verify_manifest(card, exports_dir, paths)
    requested = manifest["requested_editions"] if manifest else list(paths)
    dish = dish_folder(card, destination)
    dish.mkdir(parents=True, exist_ok=True)

    # Every run revalidates the actual destination bytes of every artifact;
    # persisted verified flags are never trusted on resume. A missing or
    # stale artifact is recovered from the exports-dir source whenever that
    # source still exists: a failed run clears once the source is restored,
    # and a deleted staged file is replaced instead of believed.
    artifacts: list[StagedArtifact] = []
    all_verified = True
    for kind in requested:
        source = paths[kind]
        target = dish / source.name
        if kind in integrity_errors:
            artifacts.append(StagedArtifact(kind=kind, path=target,
                                            detail=integrity_errors[kind]))
            continue
        expected_hash = manifest["artifacts"][kind]["sha256"]
        persisted = None
        if existing is not None:
            persisted = next(
                (a for a in existing.get("artifacts", []) if a.get("kind") == kind),
                None,
            )

        if target.exists() and persisted is not None:
            ok, reason = _bound_readback(target, card, manifest, expected_hash)
            current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            binding_ok = (
                ok
                and persisted.get("content_hash") == current_hash
                and existing.get("content_digest") == digest
            )
            if binding_ok:
                artifacts.append(
                    StagedArtifact(
                        kind=kind,
                        path=target,
                        ok=True,
                        verified=True,
                        detail=reason,
                        content_hash=current_hash,
                    )
                )
                continue
            # The bytes changed or the binding is stale: recover from source.

        if source.exists():
            shutil.copy2(source, target)
            ok, reason = _bound_readback(target, card, manifest, expected_hash)
            content_hash = (
                hashlib.sha256(target.read_bytes()).hexdigest()
                if target.exists()
                else ""
            )
        else:
            ok, reason = (
                False,
                f"{kind} export was not built and no source export exists to recover from",
            )
            content_hash = ""
        artifacts.append(
            StagedArtifact(
                kind=kind,
                path=target,
                ok=ok,
                verified=ok,
                detail=reason,
                content_hash=content_hash,
            )
        )
        if not ok:
            all_verified = False

    all_verified = all(a.verified for a in artifacts) and bool(artifacts)
    state = {
        "retry_key": key,
        "recipe_id": card.recipe_id,
        "version": card.version,
        "content_digest": digest,
        "build_manifest": manifest,
        "status": VERIFIED if all_verified else FAILED,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": [
            {
                "kind": a.kind,
                "path": str(a.path) if a.path else None,
                "ok": a.ok,
                "verified": a.verified,
                "detail": a.detail,
                "content_hash": a.content_hash,
            }
            for a in artifacts
        ],
        "preserved_ids": _preserved_ids(card),
        "remote_status": PENDING,
        "remote_note": (
            "no authenticated library client in this package; remote filing "
            "stays pending and no Drive ID is minted or replaced"
        ),
    }
    _save_state(pending_dir, state)

    receipt = {
        "retry_key": key,
        "recipe_id": card.recipe_id,
        "version": card.version,
        "status": state["status"],
        "dish_folder": str(dish),
        "artifacts": state["artifacts"],
        "preserved_ids": state["preserved_ids"],
        "remote": {"status": PENDING, "drive_id": None, "note": state["remote_note"]},
    }
    (dish / RECEIPT_NAME).write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    status = VERIFIED if all_verified else FAILED
    detail = (
        "all staged artifacts read back and verified"
        if all_verified
        else "one or more staged artifacts did not read back"
    )
    return FilingResult(
        status=status,
        retry_key=key,
        dish_folder=dish,
        artifacts=artifacts,
        preserved_ids=state["preserved_ids"],
        remote_status=PENDING,
        detail=detail,
    )


# ---------------------------------------------------------------- CLI


def _print_result(result: FilingResult) -> None:
    print(f"filing: {result.status}  retry key {result.retry_key}")
    if result.dish_folder:
        print(f"    dish folder: {result.dish_folder}")
    for a in result.artifacts:
        mark = "ok" if a.ok else "miss"
        print(f"    {mark:4} {a.kind:<9} {a.detail}")
    if result.preserved_ids:
        print(f"    preserved Drive IDs: {', '.join(result.preserved_ids)}")
    print(f"    remote: {result.remote_status}")
    if result.detail:
        print(f"    {result.detail}")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="filing.py",
        description="Stage and verify a Miseform card's exports idempotently.",
    )
    parser.add_argument("card", help="Path to the validated card JSON document")
    parser.add_argument(
        "exports_dir",
        help="Folder build_card.py wrote the editions into",
    )
    parser.add_argument(
        "--authorize",
        action="store_true",
        help="Authorize filing; without it nothing is written.",
    )
    parser.add_argument(
        "--destination",
        default=None,
        help="Folder that receives the dish staging folder (default: exports_dir/staging)",
    )
    args = parser.parse_args(argv)

    try:
        card = Card.load(args.card)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"CARD ERROR: {exc}", file=sys.stderr)
        return 2

    result = file_card(
        card,
        Path(args.exports_dir),
        authorized=args.authorize,
        destination=Path(args.destination) if args.destination else None,
    )
    _print_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

__all__ = [
    "Card",
    "content_digest",
    "retry_key",
    "dish_folder",
    "edition_paths",
    "readback_verify",
    "file_card",
    "FilingResult",
    "StagedArtifact",
    "PENDING",
    "VERIFIED",
    "FAILED",
]
