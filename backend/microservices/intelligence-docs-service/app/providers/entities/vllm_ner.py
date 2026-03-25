"""Backward-compatibility shim — use sglang_ner instead."""
from app.providers.entities.sglang_ner import SglangNerProvider

# Alias for existing imports
VllmNerProvider = SglangNerProvider
