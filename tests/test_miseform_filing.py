"""Focused checks for the Miseform filing adapter (scripts/filing.py).

Synthetic only: no library client, no credentials, no remote write, and no
recipe mutation. The adapter stages exports locally, verifies each artifact
by reading it back, and resumes a pending operation by its retry key.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from card_model import Card  # noqa: E402
from filing import content_digest, file_card, retry_key  # noqa: E402

EXAMPLE = ROOT / "examples" / "sesame-salt-garnish.card.json"


def _built_exports(tmp_path: Path) -> tuple[Card, Path]:
    """Build every edition of the example card into ``tmp_path``."""
    import build_card  # noqa: E402

    code = build_card.main(["--outdir", str(tmp_path), str(EXAMPLE)])
    # The example carries release blockers, so the build exits 1 while still
    # writing every edition it can produce.
    card = Card.load(EXAMPLE)
    stem = card.filename_stem
    for suffix in (".md", ".html", ".json", ".pdf", ".xlsx"):
        assert (tmp_path / f"{stem}{suffix}").exists(), f"missing {suffix}"
    return card, tmp_path


# ------------------------------------------------------------ retry key


def test_retry_key_is_deterministic_and_bound_to_content() -> None:
    card = Card.load(EXAMPLE)
    digest = content_digest(card)
    first = retry_key(card.recipe_id, card.version, digest)
    second = retry_key(card.recipe_id, card.version, digest)
    assert first == second
    assert len(first) == 64  # sha256 hex

    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["version"] = "v0.5"
    altered = Card(data)
    assert retry_key(altered.recipe_id, altered.version, content_digest(altered)) != first


# ------------------------------------------------------------ authorization


def test_unauthorized_filing_creates_nothing_and_stays_pending(tmp_path: Path) -> None:
    card = Card.load(EXAMPLE)
    result = file_card(card, tmp_path, authorized=False, destination=tmp_path / "library")
    assert result.status == "pending"
    assert result.retry_key == retry_key(card.recipe_id, card.version, content_digest(card))
    assert not (tmp_path / "library").exists()
    assert "stays local" in result.detail


# ------------------------------------------------------------ staging


def test_authorized_filing_stages_every_edition_into_a_dish_folder(
    tmp_path: Path,
) -> None:
    card, exports = _built_exports(tmp_path / "exports")
    destination = tmp_path / "library"
    result = file_card(card, exports, authorized=True, destination=destination)

    assert result.status == "verified", result.detail
    dish = destination / f"{card.recipe_id}__{card.title.lower().replace(' ', '-')}"
    assert result.dish_folder == dish
    assert dish.is_dir()

    stem = card.filename_stem
    for suffix in (".md", ".html", ".json", ".pdf", ".xlsx"):
        staged = dish / f"{stem}{suffix}"
        assert staged.exists(), f"staged {suffix} is missing"
    assert (dish / "receipt.json").exists()

    for artifact in result.artifacts:
        assert artifact.ok, f"{artifact.kind}: {artifact.detail}"
        assert artifact.verified
        assert artifact.path is not None

    receipt = json.loads((dish / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["recipe_id"] == card.recipe_id
    assert receipt["version"] == card.version
    assert receipt["remote"]["status"] == "pending"
    assert receipt["remote"]["drive_id"] is None


def test_filing_is_idempotent_and_resumes_the_pending_state(tmp_path: Path) -> None:
    card, exports = _built_exports(tmp_path / "exports")
    destination = tmp_path / "library"

    first = file_card(card, exports, authorized=True, destination=destination)
    assert first.status == "verified"

    before = sorted(p.name for p in destination.rglob("*") if p.is_file())
    second = file_card(card, exports, authorized=True, destination=destination)
    assert second.status == "verified"
    after = sorted(p.name for p in destination.rglob("*") if p.is_file())
    assert before == after, "a second run of the same card must not duplicate files"
    assert second.retry_key == first.retry_key
    assert len(list((destination / ".miseform-pending").glob("*.json"))) == 1


# ------------------------------------------------------------ readback


def test_corrupted_workbook_fails_readback(tmp_path: Path) -> None:
    card, exports = _built_exports(tmp_path / "exports")
    stem = card.filename_stem
    xlsx = exports / f"{stem}.xlsx"
    xlsx.write_bytes(b"not a workbook at all")

    result = file_card(card, exports, authorized=True, destination=tmp_path / "library")
    assert result.status == "failed"
    bad = [a for a in result.artifacts if a.kind == "xlsx"][0]
    assert not bad.ok
    assert bad.verified is False


# ------------------------------------------------------------ preserved IDs


def test_recorded_drive_ids_are_preserved_and_never_minted(tmp_path: Path) -> None:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["provenance"]["filing"] = (
        "Filed to library demo; Drive file Abcdefghijklmnopqrstuvwxyz1234567890, "
        "previous version retained."
    )
    card = Card(data)
    _, exports = _built_exports(tmp_path / "exports")
    result = file_card(card, exports, authorized=True, destination=tmp_path / "library")

    assert "Abcdefghijklmnopqrstuvwxyz1234567890" in result.preserved_ids
    receipt = json.loads(
        (result.dish_folder / "receipt.json").read_text(encoding="utf-8")
    )
    assert "Abcdefghijklmnopqrstuvwxyz1234567890" in receipt["preserved_ids"]
    # Remote filing stays pending: no new ID, no replacement.
    assert receipt["remote"]["status"] == "pending"
    assert receipt["remote"]["drive_id"] is None


# ------------------------------------------------------------ missing exports


def test_a_never_built_export_is_reported_honestly(tmp_path: Path) -> None:
    card = Card.load(EXAMPLE)
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / f"{card.filename_stem}.md").write_text("# card\n", encoding="utf-8")
    result = file_card(card, exports, authorized=True, destination=tmp_path / "library")
    assert result.status == "failed"
    kinds = {a.kind for a in result.artifacts if not a.ok}
    assert "xlsx" in kinds and "pdf" in kinds
    assert any("not built" in a.detail for a in result.artifacts if a.kind == "xlsx")


# ------------------------------------------------------------ retry: revalidate bytes, never trust stored flags


def test_deleted_staged_markdown_is_revalidated_and_recovered(tmp_path: Path) -> None:
    """After a verified filing, deleting a staged artifact must not stay verified."""
    card, exports = _built_exports(tmp_path / "exports")
    destination = tmp_path / "library"

    first = file_card(card, exports, authorized=True, destination=destination)
    assert first.status == "verified", first.detail

    staged_md = next(p for p in destination.rglob("*.md") if p.is_file())
    staged_md.unlink()

    second = file_card(card, exports, authorized=True, destination=destination)
    assert second.status == "verified", second.detail
    assert next(p for p in destination.rglob("*.md") if p.is_file()).exists()
    assert any(a.kind == "markdown" and a.ok and a.verified for a in second.artifacts)


def test_failed_filing_is_retried_when_the_source_is_restored(tmp_path: Path) -> None:
    """A corrupt first attempt must clear once the source export is restored."""
    card, exports = _built_exports(tmp_path / "exports")
    stem = card.filename_stem
    (exports / f"{stem}.xlsx").write_bytes(b"not a workbook at all")

    destination = tmp_path / "library"
    first = file_card(card, exports, authorized=True, destination=destination)
    assert first.status == "failed"
    assert any(a.kind == "xlsx" and not a.ok for a in first.artifacts)

    import build_card  # noqa: E402

    build_card.main(["--outdir", str(exports), str(EXAMPLE)])

    second = file_card(card, exports, authorized=True, destination=destination)
    assert second.status == "verified", second.detail
    xlsx = [a for a in second.artifacts if a.kind == "xlsx"][0]
    assert xlsx.ok and xlsx.verified


def test_stale_exports_for_altered_card_do_not_verify(tmp_path: Path) -> None:
    """Same id and version is not enough: stale content must fail verification."""
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["components"][0]["ingredients"][0]["weight_g"] = 999
    altered = Card(data)

    _, exports = _built_exports(tmp_path / "exports")  # original exports, untouched

    result = file_card(altered, exports, authorized=True, destination=tmp_path / "library")
    assert result.status != "verified", result.detail
    failed = [a for a in result.artifacts if not a.ok]
    assert failed, "at least one artifact must reject the stale content"
    assert any(a.kind in {"json", "xlsx"} and not a.ok for a in failed)


def test_stale_only_pdf_in_mixed_content_set_fails_verification(
    tmp_path: Path,
) -> None:
    """Same id/version with only the PDF stale must not verify. Fresh MD,
    HTML, JSON and XLSX cannot carry a stale PDF: the gate covers a mixed
    content set, not merely an entire old set failing because JSON differs."""
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["components"][0]["ingredients"][0]["weight_g"] = 999
    altered = Card(data)
    stem = altered.filename_stem

    # Fresh exports for the altered card: every edition carries 999 g.
    altered_path = tmp_path / "altered.card.json"
    altered_path.write_text(json.dumps(data), encoding="utf-8")
    altered_exports = tmp_path / "altered-exports"
    import build_card  # noqa: E402

    build_card.main(["--outdir", str(altered_exports), str(altered_path)])

    # The original (stale) PDF: same id/version/title, but 100 g.
    original_exports = tmp_path / "original-exports"
    build_card.main(["--outdir", str(original_exports), str(EXAMPLE)])
    stale_pdf = original_exports / f"{stem}.pdf"
    assert stale_pdf.exists()
    # Replace ONLY the pdf: a mixed content set.
    (altered_exports / f"{stem}.pdf").write_bytes(stale_pdf.read_bytes())

    destination = tmp_path / "library"
    result = file_card(altered, altered_exports, authorized=True, destination=destination)
    assert result.status != "verified", result.detail
    pdf = [a for a in result.artifacts if a.kind == "pdf"][0]
    assert not pdf.ok, f"stale-only PDF must fail verification: {pdf.detail}"
    # The fresh editions still pass on their own; the PDF alone drags the run down.
    others = [a for a in result.artifacts if a.kind != "pdf"]
    assert others, "expected the non-PDF editions to be staged"
    assert all(a.ok for a in others), [a.detail for a in others]


# ------------------------------------------------------------ 03R2: full-content binding


def test_stale_method_only_pdf_fails_verification(tmp_path: Path) -> None:
    """Same id/version/title/masses is not enough: a PDF whose method is
    stale must fail verification even when MD/HTML/JSON/XLSX are fresh.

    Change only the first method step, build fresh MD/HTML/JSON/XLSX for the
    altered card, then substitute a PDF freshly generated from the ORIGINAL
    card (same identity and masses, obsolete method). file_card must reject
    the stale-method PDF instead of reporting VERIFIED all five.
    """
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["stages"][0]["steps"][0]["text"] = (
        "Cook for 45 minutes. Chef has changed this method."
    )
    altered = Card(data)
    altered_path = tmp_path / "altered.card.json"
    altered_path.write_text(json.dumps(data), encoding="utf-8")

    # Fresh MD/HTML/JSON/XLSX for the altered card.
    altered_exports = tmp_path / "altered-exports"
    import build_card  # noqa: E402

    build_card.main(["--outdir", str(altered_exports), str(altered_path)])
    # The example carries release blockers, so the build exits 1 while still
    # writing every edition it can produce.
    stem = altered.filename_stem
    for suffix in (".md", ".html", ".json", ".xlsx"):
        assert (altered_exports / f"{stem}{suffix}").exists(), f"missing {suffix}"

    # Substitute the PDF: freshly generated from the ORIGINAL card, same
    # id/version/title/masses, but the obsolete method.
    original_exports = tmp_path / "original-exports"
    build_card.main(["--outdir", str(original_exports), str(EXAMPLE)])
    stale_pdf = original_exports / f"{stem}.pdf"
    assert stale_pdf.exists(), "original card did not produce a PDF"
    (altered_exports / f"{stem}.pdf").write_bytes(stale_pdf.read_bytes())

    destination = tmp_path / "library"
    result = file_card(altered, altered_exports, authorized=True, destination=destination)
    assert result.status != "verified", result.detail
    pdf = [a for a in result.artifacts if a.kind == "pdf"][0]
    assert not pdf.ok, f"stale-method PDF must fail verification: {pdf.detail}"


def test_fresh_consistent_set_verifies_all_five(tmp_path: Path) -> None:
    """A fresh, consistent build of every edition verifies all five."""
    card, exports = _built_exports(tmp_path / "exports")
    result = file_card(card, exports, authorized=True, destination=tmp_path / "library")
    assert result.status == "verified", result.detail
    assert all(a.ok and a.verified for a in result.artifacts), [
        a.detail for a in result.artifacts
    ]
    from build_manifest import digest, file_hash
    manifest = json.loads((exports / f"{card.filename_stem}.manifest.json").read_text())
    assert manifest["record_digest"] == digest(card.data)
    assert set(manifest["requested_editions"]) == {"markdown", "html", "json", "pdf", "xlsx"}
    for artifact in manifest["artifacts"].values():
        assert artifact["sha256"] == file_hash(exports / artifact["name"])


def test_post_build_single_artifact_mutation_is_detected(tmp_path: Path) -> None:
    """A source export mutated after the build must fail readback on filing."""
    card, exports = _built_exports(tmp_path / "exports")
    stem = card.filename_stem
    md = exports / f"{stem}.md"
    original_md = md.read_text(encoding="utf-8")
    md.write_text(original_md + "\nTAMPERED\n", encoding="utf-8")

    result = file_card(card, exports, authorized=True, destination=tmp_path / "library")
    assert result.status != "verified", result.detail
    md_art = [a for a in result.artifacts if a.kind == "markdown"][0]
    assert not md_art.ok, f"mutated markdown must fail: {md_art.detail}"


def test_stale_volume_only_pdf_is_rejected(tmp_path: Path) -> None:
    import build_card
    data = json.loads(EXAMPLE.read_text())
    data['components'][0]['ingredients'][0]['volume'] = '999 tbsp (US) — corrected recorded volume'
    source = tmp_path / 'changed.json'
    source.write_text(json.dumps(data))
    build_card.main([str(source), '--outdir', str(tmp_path / 'fresh')])
    _, old = _built_exports(tmp_path / 'old')
    card = Card.load(source)
    pdf = f'{card.filename_stem}.pdf'
    (tmp_path / 'fresh' / pdf).write_bytes((old / pdf).read_bytes())
    result = file_card(card, tmp_path / 'fresh', authorized=True)
    assert not result.ok
    assert not next(a for a in result.artifacts if a.kind == 'pdf').ok


def test_missing_manifest_rejects_complete_exports(tmp_path: Path) -> None:
    card, exports = _built_exports(tmp_path / 'exports')
    manifest = exports / f'{card.filename_stem}.manifest.json'
    assert manifest.exists()
    manifest.unlink()
    assert not file_card(card, exports, authorized=True).ok


@pytest.mark.parametrize('field,value', [('theme', 'paper'), ('language', 'es')])
def test_changed_render_settings_reject_previous_build(tmp_path: Path, field: str, value: str) -> None:
    card, exports = _built_exports(tmp_path / 'exports')
    altered = Card({**card.data, field: value})
    assert not file_card(altered, exports, authorized=True).ok


def test_scoped_build_needs_only_requested_editions(tmp_path: Path) -> None:
    import build_card
    build_card.main([str(EXAMPLE), '--outdir', str(tmp_path / 'exports'), '--skip-pdf'])
    result = file_card(Card.load(EXAMPLE), tmp_path / 'exports', authorized=True)
    assert result.ok, result.detail
    assert 'pdf' not in {a.kind for a in result.artifacts}


DEMO_003 = ROOT / "examples" / "DEMO-003__multi-allergen-demonstration-dish__v0.1__2026-11-02.json"


def test_pdf_readback_accepts_wrapped_names_and_narrow_masses(tmp_path: Path) -> None:
    """A fresh export of a card with long ingredient names and single-digit
    masses must verify.

    The PDF text layer wraps a long ingredient name across the table row,
    so the other columns' values arrive between the name's words, and a
    narrow mass can lose the space before its unit ("2 g" extracted as
    "2g"). Both are extraction artifacts, not missing content, so the
    readback must not reject a correct export over them.
    """
    import build_card

    exports = tmp_path / "exports"
    build_card.main([str(DEMO_003), "--outdir", str(exports)])
    card = Card.load(DEMO_003)
    result = file_card(card, exports, authorized=True, destination=tmp_path / "library")
    assert result.ok, [a.detail for a in result.artifacts]


def test_retry_rejects_changed_source_even_with_good_staged_copy(tmp_path: Path) -> None:
    card, exports = _built_exports(tmp_path / 'exports')
    assert file_card(card, exports, authorized=True).ok
    (exports / f'{card.filename_stem}.pdf').write_bytes(b'changed after filing')
    assert not file_card(card, exports, authorized=True).ok


def test_external_translation_change_is_rejected_and_embedded_for_rebuild(tmp_path: Path) -> None:
    import build_card
    source = tmp_path / 'recipe.json'
    source.write_text(EXAMPLE.read_text())
    sidecar = tmp_path / 'recipe.lang-es.json'
    sidecar.write_text(json.dumps({'title': 'Sal de sesamo'}))
    exports = tmp_path / 'exports'
    build_card.main([str(source), '--lang', 'es', '--outdir', str(exports)])
    stem = Card.load(source).filename_stem
    canonical = Card.load(exports / f'{stem}.json')
    assert canonical.data['render_translation'] == {'title': 'Sal de sesamo'}
    assert file_card(canonical, exports, authorized=True).ok
    # Reload original location with emitted record: sidecar edits must invalidate.
    source.write_text(json.dumps(canonical.data))
    sidecar.write_text(json.dumps({'title': 'Texto cambiado'}))
    assert not file_card(Card.load(source), exports, authorized=True).ok
    rebuilt = tmp_path / 'rebuilt'
    build_card.main([str(exports / f'{stem}.json'), '--outdir', str(rebuilt)])
    assert 'Sal de sesamo' in (rebuilt / f'{stem}.html').read_text()
    assert file_card(Card.load(rebuilt / f'{stem}.json'), rebuilt, authorized=True).ok


def test_missing_staged_artifact_cannot_recover_from_altered_source(tmp_path: Path) -> None:
    card, exports = _built_exports(tmp_path / 'exports')
    first = file_card(card, exports, authorized=True)
    assert first.ok
    next(a.path for a in first.artifacts if a.kind == 'pdf').unlink()
    (exports / f'{card.filename_stem}.pdf').write_bytes(b'wrong source')
    second = file_card(card, exports, authorized=True)
    assert not second.ok
    assert not next(a.path for a in second.artifacts if a.kind == 'pdf').exists()


@pytest.mark.parametrize('next_language', ['en', 'es'])
def test_embedded_translation_does_not_cross_languages(tmp_path: Path, next_language: str) -> None:
    import build_card
    source = tmp_path / 'recipe.json'
    source.write_text(EXAMPLE.read_text())
    source.with_name('recipe.lang-fr.json').write_text(json.dumps({'title': 'Titre francais unique'}))
    french = tmp_path / 'french'
    build_card.main([str(source), '--lang', 'fr', '--outdir', str(french)])
    stem = Card.load(source).filename_stem
    copied = tmp_path / 'copied' / 'recipe.json'
    copied.parent.mkdir()
    copied.write_bytes((french / f'{stem}.json').read_bytes())
    target = tmp_path / next_language
    build_card.main([str(copied), '--lang', next_language, '--outdir', str(target)])
    assert 'Titre francais unique' not in (target / f'{stem}.html').read_text()
    record = Card.load(target / f'{stem}.json')
    assert 'render_translation' not in record.data
    assert file_card(record, target, authorized=True).ok
