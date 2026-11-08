"""Focused tests for the Miseform translation catalog (release ticket 05).

Five cook languages ship with the toolchain: English (default), Spanish,
French, Italian, Portuguese. Only rendered text is localized; the canonical
card JSON stays locale-neutral.

Run with:

    python3 -m pytest tests/test_miseform_locales.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from locales import (  # noqa: E402
    DEFAULT_LANGUAGE,
    LANGUAGE_CODES,
    MESSAGES,
    UNTRANSLATED,
    detect_language,
    format_number,
    localize_decimals,
    note_text,
    normalize_language,
    recipe_text,
    resolve_language,
    translate,
    load_translation_bundle,
)

ALL_LANGUAGES = ("en", "es", "fr", "it", "pt")


# --------------------------------------------------------------- catalog

def test_language_codes_are_exactly_the_five_shipped():
    assert LANGUAGE_CODES == ("en", "es", "fr", "it", "pt")


def test_default_language_is_english():
    assert DEFAULT_LANGUAGE == "en"


def test_every_message_key_covers_all_five_languages():
    """No missing keys: a render must never invent text or fall back silently."""
    for message_id, table in MESSAGES.items():
        assert isinstance(table, dict), message_id
        for language in ALL_LANGUAGES:
            assert language in table, f"{message_id} missing {language}"
            value = table[language]
            assert isinstance(value, str) and value.strip(), f"{message_id} empty for {language}"


def test_no_message_is_just_whitespace():
    for table in MESSAGES.values():
        for value in table.values():
            assert value.strip()


# --------------------------------------------------------------- translate

def test_translate_returns_each_language():
    assert translate("heading.ingredients", "en") == "Ingredients"
    assert translate("heading.ingredients", "es") == "Ingredientes"
    assert translate("heading.ingredients", "fr") == "Ingrédients"
    assert translate("heading.ingredients", "it") == "Ingredienti"
    assert translate("heading.ingredients", "pt") == "Ingredientes"


def test_translate_uses_decimal_comma_languages_consistently():
    for language in ("es", "fr", "it", "pt"):
        assert translate("xlsx.table.weight", language).endswith("(g)")
    assert translate("xlsx.table.weight", "en") == "Weight (g)"


def test_translate_falls_back_to_english_for_a_gap():
    table = dict(MESSAGES["heading.ingredients"])
    del table["es"]
    MESSAGES["heading.ingredients"] = table
    try:
        assert translate("heading.ingredients", "es") == "Ingredients"
    finally:
        MESSAGES["heading.ingredients"]["es"] = "Ingredientes"


def test_translate_unknown_message_id_returns_itself():
    assert translate("no.such.key", "es") == "no.such.key"
    assert translate("no.such.key", "en") == "no.such.key"


def test_translate_never_crashes_on_a_missing_table():
    # A message missing everywhere is returned as-is: no invented text, no
    # crash. A missing language inside an existing table falls back to English.
    assert translate("no.such.key", "xx") == "no.such.key"
    assert translate("no.such.key", "en") == "no.such.key"


# --------------------------------------------------------------- language resolution

@pytest.mark.parametrize(
    "value,expected",
    [
        ("es", "es"),
        ("ES", "es"),
        ("es_ES", "es"),
        ("es-ES", "es"),
        ("es_ES.UTF-8", "es"),
        ("fr_FR", "fr"),
        ("it_IT.UTF-8", "it"),
        ("pt_BR", "pt"),
        ("xx", None),
        ("en_US", "en"),
        (None, None),
        ("", None),
        ("   ", None),
    ],
)
def test_normalize_language(value, expected):
    assert normalize_language(value) == expected


def test_resolve_language_cli_flag_wins(monkeypatch):
    monkeypatch.setenv("MISEFORM_LANGUAGE", "fr")
    card = {"language": "es"}
    assert resolve_language("pt", card) == "pt"


def test_resolve_language_card_field_next(monkeypatch):
    monkeypatch.delenv("MISEFORM_LANGUAGE", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LANG", raising=False)
    card = {"language": "it"}
    assert resolve_language(None, card) == "it"


def test_resolve_language_unsupported_card_field_falls_through(monkeypatch):
    monkeypatch.delenv("MISEFORM_LANGUAGE", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LANG", raising=False)
    card = {"language": "xx"}
    assert resolve_language(None, card) == DEFAULT_LANGUAGE


def test_resolve_language_host_environment(monkeypatch):
    monkeypatch.delenv("MISEFORM_LANGUAGE", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.setenv("LANG", "pt_PT.UTF-8")
    card = {}
    assert resolve_language(None, card) == "pt"


def test_resolve_language_defaults_to_english(monkeypatch):
    for var in ("MISEFORM_LANGUAGE", "LC_ALL", "LANG"):
        monkeypatch.delenv(var, raising=False)
    assert resolve_language(None, {}) == DEFAULT_LANGUAGE


def test_detect_language_order(monkeypatch):
    monkeypatch.setenv("MISEFORM_LANGUAGE", "es")
    monkeypatch.setenv("LC_ALL", "fr_FR")
    monkeypatch.setenv("LANG", "pt_PT")
    assert detect_language() == "es"
    monkeypatch.delenv("MISEFORM_LANGUAGE", raising=False)
    assert detect_language() == "fr"


# --------------------------------------------------------------- decimals

@pytest.mark.parametrize(
    "text,language,expected",
    [
        ("2.5", "en", "2.5"),
        ("2.5", "es", "2,5"),
        ("2.5", "fr", "2,5"),
        ("2.5", "it", "2,5"),
        ("2.5", "pt", "2,5"),
        ("1000", "es", "1000"),
        ("1000", "pt", "1000"),
        ("v0.1", "es", "v0.1"),
        ("v0.1", "fr", "v0.1"),
        ("https://example.com/card.v1.json", "es", "https://example.com/card.v1.json"),
        ("420 g", "es", "420 g"),
    ],
)
def test_localize_decimals_switches_only_the_decimal_mark(text, language, expected):
    assert localize_decimals(text, language) == expected


def test_localize_decimals_never_adds_a_thousands_separator():
    assert localize_decimals("1000", "es") == "1000"
    assert localize_decimals("1000000", "fr") == "1000000"


@pytest.mark.parametrize(
    "value,language,expected",
    [
        (420.0, "en", "420"),
        (420.0, "es", "420"),
        (10.5, "en", "10.5"),
        (10.5, "es", "10,5"),
        (10.5, "fr", "10,5"),
        (0.25, "pt", "0,2"),
    ],
)
def test_formatter_keeps_the_amount_and_switches_the_mark(value, language, expected):
    assert format_number(value, language) == expected


# --------------------------------------------------------------- recipe text bundles

def test_recipe_text_uses_bundle_override():
    texts = {"title": "Título de prueba", "intro": "Una sopa."}
    assert recipe_text(texts, "title", "Default title") == "Título de prueba"


def test_recipe_text_falls_back_to_card_default():
    assert recipe_text({"title": "   "}, "title", "Default title") == "Default title"
    assert recipe_text({}, "title", "Default title") == "Default title"
    assert recipe_text(None, "title", "Default title") == "Default title"


def test_note_text_uses_bundle_override():
    texts = {"notes": [{"heading": "Nota", "text": "Un detalle."}]}
    heading, text = note_text(texts, 0, "Heading", "Default text")
    assert heading == "Nota"
    assert text == "Un detalle."


def test_note_text_falls_back_to_defaults():
    heading, text = note_text(None, 0, "Heading", "Default text")
    assert heading == "Heading"
    assert text == "Default text"
    heading, text = note_text({"notes": []}, 5, "Heading", "Default text")
    assert heading == "Heading"
    assert text == "Default text"


# --------------------------------------------------------------- proper names stay verbatim

def test_untranslated_holds_proper_product_names():
    for name in ("tahini", "maldon", "hickory", "japanese eggplant", "usda",
                 "fooddata central", "king arthur"):
        assert name in UNTRANSLATED


# --------------------------------------------------------------- rendering integration

def test_html_is_localized_end_to_end():
    import json
    from card_model import load_card
    from render_html import render_html

    card = load_card(ROOT / "examples" / "DEMO-002__smoked-eggplant-tahini-drizzle__v0.1__2026-11-02.json")
    markup = render_html(card, language="es")
    assert '<html lang="es"' in markup
    assert "Ingredientes" in markup
    assert "Tiempo total" in markup
    assert "NO LIBERADO PARA PRODUCCIÓN" in markup
    # Proper product names are never translated.
    assert "tahini" in markup.lower()
    assert "hickory" in markup.lower()
    # Numbers keep their amounts; es renders the decimal comma.
    assert "420 g" in markup


def test_markdown_localizes_numbers_and_status():
    import json
    from card_model import load_card
    from render_markdown import render_markdown

    card = load_card(ROOT / "examples" / "DEMO-002__smoked-eggplant-tahini-drizzle__v0.1__2026-11-02.json")
    markdown = render_markdown(card, language="pt")
    assert "NÃO LIBERADO PARA PRODUÇÃO" in markdown
    # Editable master uses the same localized section labels as readers.
    assert "## INGREDIENTES" in markdown
    assert "420 g" in markdown


# --------------------------------------------------------------- translated recipe text reaches every edition

def _first_step_number(card) -> int:
    for stage in card.stages:
        for step in stage.get("steps", []) or []:
            return int(step.get("number", 1))
    return 1


def test_translated_method_reaches_html_markdown_and_xlsx():
    """CLI language labels are not recipe translation: a translated step
    text must reach the HTML master, the Markdown master and the XLSX
    workbook alike, keyed by canonical step number."""
    import openpyxl  # type: ignore
    from card_model import load_card
    from exporter import export_xlsx
    from render_html import render_html
    from render_markdown import render_markdown

    card = load_card(ROOT / "examples" / "DEMO-002__smoked-eggplant-tahini-drizzle__v0.1__2026-11-02.json")
    step_no = _first_step_number(card)
    marker = "TRADUCTION_TEST_ÉTAPE"
    texts = {
        "stages": [
            {"steps": [{"number": step_no, "text": marker}]}
        ]
    }

    html = render_html(card, language="fr", texts=texts)
    assert marker in html, "HTML must carry the translated step text"

    md = render_markdown(card, language="fr", texts=texts)
    assert marker in md, "Markdown must carry the translated step text"

    out = ROOT / ".theme-parity-scratch" / "translated-method.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    result = export_xlsx(card, out, theme="original", language="fr", texts=texts)
    assert result.ok, result.detail
    wb = openpyxl.load_workbook(out)
    sheet_text = "\n".join(
        str(c.value) for row in wb.worksheets[0].iter_rows()
        for c in row if c.value is not None
    )
    assert marker in sheet_text, "XLSX must carry the translated step text"


# ------------------------------------------------- persisted translation bundle ---------

DEMO_002 = ROOT / "examples" / "DEMO-002__smoked-eggplant-tahini-drizzle__v0.1__2026-11-02.json"


def test_load_translation_bundle_none_for_english_and_missing():
    """English is the card's native language: no bundle is loaded. A card
    without a bundle returns None, so every edition still renders from the
    card record."""
    from locales import load_translation_bundle

    assert load_translation_bundle("en", DEMO_002) is None
    assert load_translation_bundle("fr", ROOT / "examples" / "DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.json") is None


def test_load_translation_bundle_loads_french_bundle():
    """A persisted per-language bundle is loaded and its fields override the
    card record; proper product names stay verbatim."""
    from locales import load_translation_bundle

    bundle = load_translation_bundle("fr", DEMO_002)
    assert isinstance(bundle, dict)
    assert bundle["title"] == "AUBERGINE FUMÉE AVEC FILET DE TAHINI ET FLEUR DE SEL"
    # Proper product names are never translated.
    assert "hickory" in bundle["components"][0]["ingredients"][0]["name"].lower()
    assert "tahini" in bundle["components"][1]["ingredients"][0]["name"].lower()
    # Step text keyed by canonical step number.
    steps = bundle["stages"][0]["steps"]
    assert steps[0]["number"] == 1
    assert "Allumez le fumoir" in steps[0]["text"]


def test_build_card_carries_translation_into_all_editions(tmp_path):
    """CLI regression: a resolved cook language carries translated title,
    ingredient names and method into Markdown, HTML, PDF and XLSX alike,
    while canonical numbers and source facts stay unchanged."""
    import build_card
    from card_model import load_card
    from exporter import extract_pdf_text
    import openpyxl  # type: ignore

    code = build_card.main(
        ["--outdir", str(tmp_path), "--lang", "fr", str(DEMO_002)]
    )
    assert code == 0

    stem = load_card(DEMO_002).filename_stem
    md = (tmp_path / f"{stem}.md").read_text(encoding="utf-8")
    html = (tmp_path / f"{stem}.html").read_text(encoding="utf-8")
    xlsx_path = tmp_path / f"{stem}.xlsx"
    pdf_path = tmp_path / f"{stem}.pdf"

    # Translated title and method reach every edition.
    assert "# AUBERGINE FUMÉE" in md
    assert "AUBERGINE FUMÉE" in html
    assert "FUMAGE" in md
    assert "FUMAGE" in html

    wb = openpyxl.load_workbook(xlsx_path)
    sheet_text = "\n".join(
        str(c.value) for row in wb.worksheets[0].iter_rows()
        for c in row if c.value is not None
    )
    assert "AUBERGINE FUMÉE" in sheet_text
    assert "FUMAGE" in sheet_text

    pdf_text = extract_pdf_text(pdf_path)
    assert "AUBERGINE FUMÉE" in pdf_text
    assert "FUMAGE" in pdf_text

    # Canonical numbers and source facts are unchanged by translation.
    data = json.loads((tmp_path / f"{stem}.json").read_text(encoding="utf-8"))
    assert data["title"] == "SMOKED EGGPLANT WITH TAHINI DRIZZLE AND FLAKE SALT"
    assert data["input_total_g"] == 611
    assert data["usable_yield_g"] == 598
    assert data["language"] == "fr"

    # Proper product names stay verbatim across editions.
    for text in (md, html, sheet_text, pdf_text):
        assert "hickory" in text.lower()
        assert "tahini" in text.lower()


# ------------------------------------------------- numeric parity guard ----------------

def test_normalize_number_rejects_unparseable_when_reference_is_numeric():
    """A rendered weight that is missing or unparseable fails parity when the
    reference is numeric, while unknown-vs-unknown stays silent."""
    from locale_parity_proof import normalize_number  # noqa: E402

    assert normalize_number("420") == 420.0
    assert normalize_number("420,5") == 420.5
    assert normalize_number("—") is None
    assert normalize_number("") is None
    assert normalize_number("invalid") is None


def test_parity_rejects_real_pdf_mass_drift(tmp_path, monkeypatch, capsys):
    """A PDF-only mass error must fail even when source and other editions agree."""
    import copy

    import locale_parity_proof as proof

    original_export = proof.export_pdf
    corrupted_pdfs = []

    def export_wrong_mass(card, path, **kwargs):
        changed = copy.deepcopy(card)
        changed.data["components"][0]["ingredients"][0]["weight_g"] = 987654.0
        result = original_export(changed, path, **kwargs)
        assert result.ok, result.detail
        assert "987654" in proof.extract_pdf_text(path).replace(" ", "")
        assert card.data["components"][0]["ingredients"][0]["weight_g"] != 987654.0
        corrupted_pdfs.append(path)
        return result

    monkeypatch.setattr(proof, "THEME_IDS", ("original",))
    monkeypatch.setattr(proof, "LANGUAGE_CODES", ("en",))
    monkeypatch.setattr(proof, "export_pdf", export_wrong_mass)
    assert proof.main(["--out", str(tmp_path)]) == 1
    assert corrupted_pdfs
    assert "PDF weight for row E1" in capsys.readouterr().out


@pytest.mark.parametrize("decimal", [".", ","])
def test_pdf_weight_readback_preserves_row_identity_and_wrapping(decimal):
    from locale_parity_proof import pdf_row_weights

    text = (
        f"E1 · Eggplant cut into 6 cm pieces       420{decimal}5 g    —\n"
        "continued ingredient name\n"
        "E2 · A wrapped ingredient\n"
        f"                 18{decimal}5 g     —\n"
        "T1 · Missing weight                 —      —\n"
        "METHOD\nWeigh T1 at 90 g, then add E1 at 420 g.\n"
    )
    assert pdf_row_weights(text) == {"E1": 420.5, "E2": 18.5}


# ------------------------------------------- canonical JSON selection ----------------

def test_canonical_json_record_is_selected_by_manifest_not_by_listing_order(tmp_path):
    """The canonical JSON edition is chosen by the name the build manifest
    declares, never by position in the directory listing.

    A build output directory holds several *.json files: the canonical
    record, the build manifest and (with a workflow ledger) the receipt.
    The manifest carries no top-level language or theme, so a positional
    pick can read it instead of the record and fail a clean parity proof.
    """
    import build_card
    from locale_parity_proof import canonical_json_record

    code = build_card.main(
        ["--outdir", str(tmp_path), "--lang", "fr", "--theme", "atelier",
         "--skip-pdf", "--skip-xlsx", str(DEMO_002)]
    )
    assert code == 0

    written = sorted(tmp_path.glob("*.json"))
    assert len(written) == 2, "expected the canonical record and the manifest"

    manifest_path = next(p for p in written if p.name.endswith(".manifest.json"))
    record_path = canonical_json_record(tmp_path)

    # The manifest declares the record by name; that is what we select.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert record_path.name == manifest["artifacts"]["json"]["name"]
    assert record_path.is_file()

    # The manifest must not be selectable as the record: it has no
    # top-level language or theme, so picking it fails a clean build.
    assert "language" not in manifest
    assert "theme" not in manifest

    # The selection is independent of listing order: reading the directory
    # forward and backward yields the same record.
    forward = sorted(tmp_path.glob("*.json"))
    backward = sorted(tmp_path.glob("*.json"), reverse=True)
    assert forward != backward, "expected the two orderings to differ"
    assert canonical_json_record(tmp_path) == record_path


def test_canonical_json_record_rejects_an_output_directory_without_a_manifest(tmp_path):
    """A directory with no build manifest cannot name the canonical record,
    so the selection fails loudly instead of guessing."""
    from locale_parity_proof import canonical_json_record

    (tmp_path / "card.json").write_text(json.dumps({"language": "fr"}), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one build manifest"):
        canonical_json_record(tmp_path)


def test_canonical_json_record_rejects_a_manifest_that_declares_no_json(tmp_path):
    """A manifest without a declared JSON artifact cannot name the record."""
    from locale_parity_proof import canonical_json_record

    (tmp_path / "card.manifest.json").write_text(
        json.dumps({"artifacts": {"pdf": {"name": "card.pdf"}}}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="declares no JSON artifact"):
        canonical_json_record(tmp_path)


def test_parity_proof_reports_the_cli_spot_check_on_a_clean_build(tmp_path, monkeypatch, capsys):
    """A clean parity proof still reports that the CLI persisted the resolved
    language and theme on the canonical JSON record, and still exits 0."""
    import locale_parity_proof as proof

    monkeypatch.setattr(proof, "THEME_IDS", ("original",))
    monkeypatch.setattr(proof, "LANGUAGE_CODES", ("en",))

    assert proof.main(["--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "CLI persists resolved language and theme on the canonical JSON record" in out
    assert "PARITY FAILURES" not in out

