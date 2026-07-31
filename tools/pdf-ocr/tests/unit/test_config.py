from pdfcover.config import OCR_CONFIG, DEFAULT_OUTPUT_SUFFIX


def test_ocr_config_is_immutable():
    """OCR_CONFIG should be a Final (constant) value."""
    assert OCR_CONFIG["language"] == "eng"
    assert OCR_CONFIG["image_dpi"] == 300
    assert OCR_CONFIG["oversample"] == 3
    assert OCR_CONFIG["force_ocr"] is True


def test_default_output_suffix():
    assert DEFAULT_OUTPUT_SUFFIX == "+OCR"  # 与实际输出文件名一致（如 19A+OCR.pdf）
