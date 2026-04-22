import pytest
from app.pipeline.classifier import classify_document


@pytest.mark.asyncio
async def test_classify_by_filename_factura():
    result = await classify_document("contenido de la factura...", "factura_2024.pdf")
    assert result.document_type == "factura"


@pytest.mark.asyncio
async def test_classify_by_filename_contrato():
    result = await classify_document("contenido del contrato...", "contrato_laboral.pdf")
    assert result.document_type == "contrato"


@pytest.mark.asyncio
async def test_classify_by_filename_nomina():
    result = await classify_document("", "nomina_marzo.pdf")
    assert result.document_type == "nomina"


@pytest.mark.asyncio
async def test_classify_unknown():
    result = await classify_document("random text", "document.pdf")
    assert result.document_type == "general"


@pytest.mark.asyncio
async def test_classify_by_content():
    result = await classify_document("FACTURA num 2024-001 por servicios prestados", "doc.pdf")
    assert result.document_type == "factura"
