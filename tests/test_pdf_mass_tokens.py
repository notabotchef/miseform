"""A PDF mass unit must not match the beginning of an ingredient word."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from filing import _mass_in_text


@pytest.mark.parametrize("text", ["2g", "2 g", "2\ng", "Salt: 2 g."])
def test_pdf_accepts_complete_gram_tokens(text):
    assert _mass_in_text("2 g", text)


@pytest.mark.parametrize("text", [
    "2 green apples, 10 g salt",
    "2 garlic cloves, 10 g salt",
    "2 gallons of water, 10 g salt",
    "12 g salt",
    "20 g salt",
    "2 kg salt",
])
def test_pdf_rejects_word_prefixes_and_other_masses(text):
    assert not _mass_in_text("2 g", text)
