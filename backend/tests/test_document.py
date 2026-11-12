import io

import cv2
import numpy as np
from PIL import Image

from smartclear.document import crop_card, prepare_document
from smartclear.extraction import Token, _layout_scale, extract, ocr_view
from smartclear import pipeline


def test_crops_dominant_card_but_not_adjacent_stamp():
    image = np.full((700, 950, 3), 220, dtype=np.uint8)
    cv2.rectangle(image, (260, 100), (850, 620), (70, 70, 70), 8)
    cv2.rectangle(image, (35, 250), (200, 390), (40, 40, 40), 5)

    cropped, did_crop = crop_card(image)

    assert did_crop
    assert cropped.shape[1] < image.shape[1] * 0.8
    assert cropped.shape[0] < image.shape[0] * 0.9


def test_perspective_corrects_a_skewed_card():
    image = np.full((700, 950, 3), 220, dtype=np.uint8)
    card = np.array([[230, 100], [800, 150], [760, 590], [160, 550]], dtype=np.int32)
    cv2.fillConvexPoly(image, card, (70, 70, 70))
    cv2.polylines(image, [card], True, (25, 25, 25), 8)

    corrected, did_crop = crop_card(image)

    assert did_crop
    assert corrected.shape[1] > corrected.shape[0]
    assert corrected.shape[1] < image.shape[1]


def test_leaves_ambiguous_two_card_page_intact():
    image = np.full((800, 1000, 3), 220, dtype=np.uint8)
    cv2.rectangle(image, (60, 220), (480, 570), (70, 70, 70), 8)
    cv2.rectangle(image, (520, 220), (940, 570), (70, 70, 70), 8)

    cropped, did_crop = crop_card(image)

    assert not did_crop
    assert cropped is image


def test_loads_all_pages_from_pdf_in_order():
    first = Image.new("RGB", (240, 160), (200, 60, 60))
    second = Image.new("RGB", (240, 160), (60, 60, 200))
    data = io.BytesIO()
    first.save(data, format="PDF", save_all=True, append_images=[second])

    image, metadata = prepare_document(data.getvalue(), "two-pages.pdf")

    assert metadata["page_count"] == 2
    assert image.shape[0] > image.shape[1]


def test_ocr_view_removes_color_without_changing_dimensions():
    image = np.zeros((32, 48, 3), dtype=np.uint8)
    image[:, :, 2] = 180

    view = ocr_view(image)

    assert view.shape == image.shape
    assert np.array_equal(view[:, :, 0], view[:, :, 1])
    assert np.array_equal(view[:, :, 1], view[:, :, 2])


def test_layout_scale_tracks_registration_title_width():
    quad = np.array([[0, 0], [195.1 * 1.5, 0], [195.1 * 1.5, 20], [0, 20]], dtype=float)
    title = Token("REGISTRATION CARD", 0.99, quad)

    assert _layout_scale(title) == 1.53


def test_registration_number_only_page_is_classified_as_back():
    image = np.full((300, 500, 3), 255, dtype=np.uint8)
    number = Token(
        "409324/32/1",
        0.95,
        np.array([[100, 80], [300, 80], [300, 110], [100, 110]], dtype=float),
    )

    result = extract(image, [number])

    assert result.side == "back"
    assert result.value("nrc_number") == "409324/32/1"
    assert result.value("full_name") is None
    assert result.value("date_of_birth") is None


def test_registration_card_title_classifies_front():
    image = np.full((400, 500, 3), 255, dtype=np.uint8)
    tokens = [
        Token(
            "Z19532924",
            0.95,
            np.array([[300, 80], [440, 80], [440, 105], [300, 105]], dtype=float),
        ),
        Token(
            "REGISTRATIONCARD",
            0.99,
            np.array([[70, 130], [340, 130], [340, 160], [70, 160]], dtype=float),
        ),
    ]

    result = extract(image, tokens)

    assert result.side == "front"
    assert result.value("card_number") == "Z19532924"


def test_process_pages_merges_front_and_back_fields(monkeypatch):
    def fake_process(image, record=None, tokens=None):
        side = "back" if image[0, 0, 0] == 10 else "front"
        fields = {
            "nrc_number": {"value": "409324/32/1" if side == "back" else None,
                           "confidence": 0.9 if side == "back" else 0, "bbox": [1, 2, 8, 6]},
            "full_name": {"value": "SAMPLE NAME" if side == "front" else None,
                          "confidence": 0.9 if side == "front" else 0, "bbox": [2, 3, 9, 7]},
            "date_of_birth": {"value": "01.01.90" if side == "front" else None,
                              "confidence": 0.9 if side == "front" else 0, "bbox": [3, 4, 10, 8]},
        }
        result = {
            "extraction": {"side": side, "fields": fields, "warnings": []},
            "forensic_boxes": {key: value["bbox"] for key, value in fields.items() if value["value"]},
            "tamper": {key: {"probability": None, "reasons": []}
                       for key in ("nrc_number", "full_name", "date_of_birth")},
            "timing_ms": {key: 1 for key in ("ocr", "extraction", "verification", "flagging", "total")},
        }
        return result, np.full((10, 20), 255 if side == "front" else 80, dtype=np.uint8)

    monkeypatch.setattr(pipeline, "process", fake_process)
    back = np.full((10, 20, 3), 10, dtype=np.uint8)
    front = np.full((10, 20, 3), 20, dtype=np.uint8)

    result, preview, pages = pipeline.process_pages([back, front])

    fields = result["extraction"]["fields"]
    assert [page["side"] for page in pages] == ["back", "front"]
    assert fields["nrc_number"]["value"] == "409324/32/1"
    assert fields["nrc_number"]["page_index"] == 0
    assert fields["full_name"]["value"] == "SAMPLE NAME"
    assert fields["full_name"]["page_index"] == 1
    assert fields["full_name"]["bbox"][1] >= 34
    assert preview.shape == (44, 20, 3)


def test_rotates_page_when_ocr_text_is_sideways(monkeypatch):
    image = np.zeros((220, 320, 3), dtype=np.uint8)
    image[0, 0] = (255, 0, 0)

    def fake_ocr(candidate):
        if candidate[-1, 0, 0] == 255:
            return [Token(
                "REGISTRATION CARD",
                0.99,
                np.array([[20, 30], [260, 30], [260, 55], [20, 55]], dtype=float),
            )]
        return [Token(
            "REGISTRATION CARD",
            0.99,
            np.array([[20, 30], [45, 30], [45, 260], [20, 260]], dtype=float),
        )]

    monkeypatch.setattr(pipeline, "run_ocr", fake_ocr)
    oriented, _, rotation = pipeline._orient_page(image)

    assert rotation == 270
    assert oriented.shape == (320, 220, 3)
