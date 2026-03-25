from app.pipeline.quality import compute_quality_score
from app.pipeline.language import detect_language


def test_quality_good_text():
    score = compute_quality_score("Este es un documento de buena calidad con texto legible y contenido suficiente.")
    assert score >= 0.8


def test_quality_empty():
    assert compute_quality_score("") == 0.0


def test_quality_garbled():
    score = compute_quality_score("a" * 200)
    assert score <= 0.8


def test_detect_spanish():
    lang = detect_language("Este es un documento en espanol sobre contratos laborales y legislacion vigente")
    assert lang == "es"


def test_detect_empty():
    assert detect_language("") == ""
