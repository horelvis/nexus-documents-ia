import logging
from typing import Optional

logger = logging.getLogger(__name__)

from app.data.labor_document_config import LABOR_DOCUMENT_TYPES

def classify_document_type(text: str) -> str:
    text_lower = text.lower()
    for item in LABOR_DOCUMENT_TYPES:
        doc_type = item['type']
        keywords = item['keywords']
        if any(keyword in text_lower for keyword in keywords):
            logger.info(f"Classified as {doc_type} based on keywords {keywords}")
            return doc_type
    logger.info("Classified as 'otro'")
    return 'otro'