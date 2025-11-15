"""
Utilities to ensure the NLTK data required by the unstructured pipeline is
available without hitting the network.
"""
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

import nltk
from loguru import logger


_RESOURCE_DIR = Path(__file__).resolve().parent.parent / "resources" / "nltk"
_REQUIRED_PACKAGES = {
    "tokenizers/punkt": "punkt.zip",
    "tokenizers/punkt_tab": "punkt_tab.zip",
    "taggers/averaged_perceptron_tagger": "averaged_perceptron_tagger.zip",
    "taggers/averaged_perceptron_tagger_eng": "averaged_perceptron_tagger_eng.zip",
}


def _target_ready(path: Path) -> bool:
    return path.exists() and any(path.iterdir())


def _extract_package(zip_filename: str, destination_root: Path) -> None:
    zip_path = _RESOURCE_DIR / zip_filename
    if not zip_path.exists():
        raise FileNotFoundError(f"Missing bundled NLTK resource: {zip_path}")

    logger.info("Installing NLTK resource from %s", zip_path.name)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(destination_root)


def _ensure_package(destination: Path, zip_filename: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    _extract_package(zip_filename, destination.parent)


def _resolve_data_dir(preferred_dir: str | None) -> Path:
    candidate = preferred_dir or os.environ.get("NLTK_DATA") or "/app/nltk_data"
    return Path(candidate).expanduser()


def prepare_nltk_data(target_dir: str | None = None) -> None:
    """
    Ensures the minimal tokenizer/tagger datasets needed by unstructured are present.
    """
    data_dir = _resolve_data_dir(target_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("NLTK_DATA", str(data_dir))
    if str(data_dir) not in nltk.data.path:
        nltk.data.path.insert(0, str(data_dir))

    for relative_path, zip_filename in _REQUIRED_PACKAGES.items():
        destination = data_dir / relative_path
        if _target_ready(destination):
            continue
        _ensure_package(destination, zip_filename)
