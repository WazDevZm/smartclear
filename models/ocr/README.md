# Text-recognition model (fine-tuned PP-OCRv4, English)

- `nrc_rec.onnx`: PP-OCRv4 English recognizer fine-tuned on the synthetic NRC field crops
  (`ocr_training/` on the `ocr-text-extraction` branch). Exported with PaddleOCR and paddle2onnx.
- `nrc_rec_keys.txt`: character dictionary (PaddleOCR `en_dict.txt`). The model outputs
  blank + these characters + space, 97 classes in total.
- Scores (exact match per field crop, synthetic data only): validation 91.5% (294 crops),
  test 97.1% (277 crops, 12 identities). Not yet measured on real NRC scans.
- Detection still uses the stock PP-OCR detector (RapidOCR default).
