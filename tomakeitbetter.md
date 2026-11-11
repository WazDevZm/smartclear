# SmartClear: problems and next steps

## What is causing the mistakes

1. **The extractor expects one card layout.** It uses printed anchors and fixed field zones based on synthetic cards. Different card versions, sizes, or field positions can put text in the wrong zone or leave fields blank.
2. **Side routing is heuristic.** Pages are now OCR'd separately and routed as front or back, but the routing and field zones have only been tested on a small sample. An unfamiliar layout can still be misclassified or left unread.
3. **Stamps and handwriting can still compete with card text.** A clear card boundary is now cropped and perspective-corrected, and pages warn when no boundary is found. On an uncropped page, current field zones can still include nearby marks.
4. **The OCR model is pretrained, not tuned for these original cards.** Grayscale helps with color variation, but it does not fix a wrong crop, layout, or unreadable scan.
5. **Tamper flags are not proof.** The tamper model was trained on synthetic cards and may mistake genuine differences in ink, print, or scan quality for alterations.

## What SmartClear uses

- **Text reading:** RapidOCR's pretrained PaddleOCR models, running locally with ONNX Runtime.
- **Image handling:** OpenCV for grayscale contrast enhancement, quadrilateral card cropping/perspective correction, quarter-turn orientation checks, and deskewing.
- **Field extraction:** anchor detection and card-relative zones calibrated on the synthetic layout.
- **Tamper detection:** a separate scikit-learn Random Forest using image features; it does not read the card.
- There is no LLM or cloud OCR service in this pipeline.

## What to do next

1. **Build version-specific field maps.** The current extractor still has one synthetic-calibrated map; it cannot safely infer new card versions' field positions. Identify each version from printed anchors and validate its field zones using representative, labelled examples.
2. **Validate boundary and stamp handling** on representative scans. The card crop helps exclude marks outside a clearly detected boundary, but handwriting within a field and ambiguous/no-boundary pages still need review.
3. **Measure per-field accuracy** on labelled examples, including unreadable fields. This shows whether remaining errors come from layout, OCR, or field assignment.
4. **Improve OCR only after measuring it:** if the card and field are located correctly but characters are wrong, compare OCR models or fine-tune on approved labelled examples. Fine-tuning cannot fix incorrect page selection or field placement.
5. **Recheck tamper flags separately** on genuine original cards. Poor image quality or unusual ink should prompt review, not be treated as evidence of fraud.

**Highest-value next change:** collect version-labelled examples and correct field locations for each version, then measure per-field accuracy. Fine-tune OCR only if the fields are correctly located but the characters are still misread.

## What would make it perform really well

The biggest gains will come from representative labelled cards, reliable card/side/layout detection, and correct field localization. Better OCR or fine-tuning can then improve character reading. Keep a human review path for uncertain fields, and evaluate on cards that were not used to tune the system.
