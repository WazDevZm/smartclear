"""Choosing the text recognizer (SMARTCLEAR_OCR_READER)."""
import numpy as np
import pytest

from smartclear import cache
from smartclear.config import OCR_REC_KEYS_PATH, OCR_REC_MODEL_PATH, ocr_reader


def test_default_reader_is_stock(monkeypatch):
    monkeypatch.delenv("SMARTCLEAR_OCR_READER", raising=False)
    assert ocr_reader() == "stock"


def test_onnx_reader_selected(monkeypatch):
    monkeypatch.setenv("SMARTCLEAR_OCR_READER", " ONNX ")
    assert ocr_reader() == "onnx"


def test_unknown_reader_rejected(monkeypatch):
    monkeypatch.setenv("SMARTCLEAR_OCR_READER", "tesseract")
    with pytest.raises(ValueError):
        ocr_reader()


def test_fine_tuned_model_files_present():
    assert OCR_REC_MODEL_PATH.exists() and OCR_REC_MODEL_PATH.stat().st_size > 1_000_000
    assert OCR_REC_KEYS_PATH.exists()


def test_cache_keys_kept_apart_per_reader(monkeypatch):
    img = np.zeros((8, 8, 3), np.uint8)
    monkeypatch.delenv("SMARTCLEAR_OCR_READER", raising=False)
    stock = cache.key_for(img)
    monkeypatch.setenv("SMARTCLEAR_OCR_READER", "stock")
    assert cache.key_for(img) == stock          # explicit stock matches the default
    monkeypatch.setenv("SMARTCLEAR_OCR_READER", "onnx")
    assert cache.key_for(img) != stock          # onnx results never reuse stock entries
