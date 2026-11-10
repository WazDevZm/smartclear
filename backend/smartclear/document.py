"""Load a submitted NRC document (PDF or image) into a BGR numpy image."""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image


def _pil_to_bgr(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def load_document(data: bytes, filename: str = "") -> np.ndarray:
    """Return the first page of a scanned NRC as a BGR image.

    Scanned PDFs normally wrap a single raster image; we take that image at full
    native resolution (no resampling loss). Vector/mixed PDFs are rendered at 200 dpi.
    """
    name = filename.lower()
    if data[:4] == b"%PDF" or name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        page = reader.pages[0]
        try:
            images = list(page.images)
        except Exception:
            images = []
        if len(images) == 1 and not (page.extract_text() or "").strip():
            return _pil_to_bgr(images[0].image)
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        return _pil_to_bgr(pdf[0].render(scale=200 / 72).to_pil())
    return _pil_to_bgr(Image.open(io.BytesIO(data)))
