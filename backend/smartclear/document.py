"""Load and prepare submitted NRC pages for OCR."""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image


def _pil_to_bgr(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def _order_quad(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).ravel()
    return np.array(
        [
            points[np.argmin(sums)],
            points[np.argmin(differences)],
            points[np.argmax(sums)],
            points[np.argmax(differences)],
        ],
        dtype=np.float32,
    )


def _rectify_quad(image: np.ndarray, quad: np.ndarray) -> np.ndarray:
    top_left, top_right, bottom_right, bottom_left = _order_quad(quad)
    width = max(
        np.linalg.norm(bottom_right - bottom_left),
        np.linalg.norm(top_right - top_left),
    )
    height = max(
        np.linalg.norm(top_right - bottom_right),
        np.linalg.norm(top_left - bottom_left),
    )
    if width < 100 or height < 100:
        return image

    pad_x, pad_y = max(4, round(width * 0.015)), max(4, round(height * 0.015))
    out_width, out_height = round(width) + 2 * pad_x, round(height) + 2 * pad_y
    target = np.array(
        [
            [pad_x, pad_y],
            [out_width - pad_x - 1, pad_y],
            [out_width - pad_x - 1, out_height - pad_y - 1],
            [pad_x, out_height - pad_y - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(_order_quad(quad), target)
    return cv2.warpPerspective(
        image, transform, (out_width, out_height),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )


def crop_card(image: np.ndarray) -> tuple[np.ndarray, bool]:
    """Crop and perspective-correct a clearly dominant card."""
    height, width = image.shape[:2]
    if min(height, width) < 160:
        return image, False

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    kernel_size = max(3, round(min(height, width) / 150) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    quadrilaterals = []
    rectangles = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if min(w, h) >= 100:
            area_ratio = cv2.contourArea(contour) / (width * height)
            aspect = max(w / h, h / w)
            if 0.16 <= area_ratio <= 0.85 and 1.0 <= aspect <= 2.0:
                rectangles.append((area_ratio, (x, y, w, h), None))

        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        quad = polygon.reshape(4, 2).astype(np.float32)
        rect = cv2.minAreaRect(quad)
        rect_width, rect_height = rect[1]
        if min(rect_width, rect_height) < 100:
            continue
        area_ratio = cv2.contourArea(polygon) / (width * height)
        aspect = max(rect_width / rect_height, rect_height / rect_width)
        if 0.16 <= area_ratio <= 0.85 and 1.0 <= aspect <= 2.0:
            x, y, w, h = cv2.boundingRect(polygon)
            quadrilaterals.append((area_ratio, (x, y, w, h), quad))

    # Collapse nested outlines of the same card before checking for ambiguity.
    candidates = quadrilaterals or rectangles
    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    distinct = []
    for area, box, quad in candidates:
        x, y, w, h = box
        overlaps_existing = False
        for _, (ox, oy, ow, oh), _ in distinct:
            intersection = max(0, min(x + w, ox + ow) - max(x, ox)) * \
                max(0, min(y + h, oy + oh) - max(y, oy))
            if intersection / min(w * h, ow * oh) >= 0.65:
                overlaps_existing = True
                break
        if not overlaps_existing:
            distinct.append((area, box, quad))

    if not distinct:
        return image, False

    largest_area, _, quad = distinct[0]
    if len(distinct) > 1 and distinct[1][0] >= largest_area * 0.45:
        return image, False

    if quad is not None:
        rectified = _rectify_quad(image, quad)
        if rectified is not image:
            return rectified, True
    x, y, w, h = distinct[0][1]
    pad_x, pad_y = max(4, round(w * 0.015)), max(4, round(h * 0.015))
    x0, y0 = max(0, x - pad_x), max(0, y - pad_y)
    x1, y1 = min(width, x + w + pad_x), min(height, y + h + pad_y)
    rectified = image[y0:y1, x0:x1]
    return rectified, True


def _stack_pages(pages: list[np.ndarray]) -> np.ndarray:
    if len(pages) == 1:
        return pages[0]
    width = max(page.shape[1] for page in pages)
    gap = 24
    canvas = np.full((sum(page.shape[0] for page in pages) + gap * (len(pages) - 1), width, 3),
                     255, dtype=np.uint8)
    y = 0
    for page in pages:
        height, page_width = page.shape[:2]
        canvas[y:y + height, :page_width] = page
        y += height + gap
    return canvas


def prepare_document_pages(
    data: bytes,
    filename: str = "",
) -> tuple[list[np.ndarray], dict[str, int | bool | list[bool]]]:
    """Load and crop pages independently, preserving their original order.

    Scanned PDFs normally wrap a single raster image; we take that image at full
    native resolution (no resampling loss). Vector/mixed PDFs are rendered at 200 dpi.
    The original upload is not modified.
    """
    name = filename.lower()
    if data[:4] == b"%PDF" or name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        pages = []
        crop_status = []
        for index, page in enumerate(reader.pages):
            try:
                images = list(page.images)
            except Exception:
                images = []
            if len(images) == 1 and not (page.extract_text() or "").strip():
                image = _pil_to_bgr(images[0].image)
            else:
                image = _pil_to_bgr(pdf[index].render(scale=200 / 72).to_pil())
            image, was_cropped = crop_card(image)
            pages.append(image)
            crop_status.append(was_cropped)
    else:
        image, was_cropped = crop_card(_pil_to_bgr(Image.open(io.BytesIO(data))))
        pages = [image]
        crop_status = [was_cropped]

    if not pages:
        raise ValueError("Document contains no pages")

    cropped = sum(crop_status)
    return pages, {
        "page_count": len(pages),
        "cropped_page_count": cropped,
        "card_cropped": cropped > 0,
        "page_cropped": crop_status,
    }


def prepare_document(data: bytes, filename: str = "") -> tuple[np.ndarray, dict[str, int | bool | list[bool]]]:
    """Load, crop, and stack all pages for callers that require one image."""
    pages, metadata = prepare_document_pages(data, filename)
    return _stack_pages(pages), metadata


def load_document(data: bytes, filename: str = "") -> np.ndarray:
    """Load all document pages and prepare clear card crops for OCR."""
    return prepare_document(data, filename)[0]
