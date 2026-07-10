from pathlib import Path

import fitz
import pytesseract
from pdf2image import convert_from_path

from config import OCR_TEXT_DIR, TESSERACT_LANG


def extract_text_directly(pdf_path: Path) -> str:
    text_parts = []

    with fitz.open(pdf_path) as doc:
        for page in doc:
            text_parts.append(page.get_text())

    return "\n".join(text_parts).strip()


def extract_text_with_ocr(pdf_path: Path) -> str:
    pages = convert_from_path(str(pdf_path), dpi=300)

    text_parts = []

    for page in pages:
        text = pytesseract.image_to_string(page, lang=TESSERACT_LANG)
        text_parts.append(text)

    return "\n".join(text_parts).strip()


def calculate_quality(text: str) -> float:
    if not text:
        return 0.0

    clean_length = len(text.strip())
    alpha_count = sum(char.isalpha() for char in text)

    if clean_length == 0:
        return 0.0

    quality = alpha_count / clean_length
    return round(min(quality, 1.0), 2)


def save_extracted_text(pdf_path: Path, text: str) -> Path:
    OCR_TEXT_DIR.mkdir(parents=True, exist_ok=True)

    output_name = pdf_path.stem + ".txt"
    output_path = OCR_TEXT_DIR / output_name

    output_path.write_text(text, encoding="utf-8")
    return output_path


def extract_pdf_text(pdf_path: Path) -> dict:
    pdf_path = Path(pdf_path)

    direct_text = extract_text_directly(pdf_path)

    if len(direct_text.strip()) > 80:
        text_path = save_extracted_text(pdf_path, direct_text)

        return {
            "text": direct_text,
            "method": "direct_text",
            "ocr_quality": calculate_quality(direct_text),
            "text_path": str(text_path),
        }

    try:
        ocr_text = extract_text_with_ocr(pdf_path)
        text_path = save_extracted_text(pdf_path, ocr_text)

        return {
            "text": ocr_text,
            "method": "tesseract_ocr",
            "ocr_quality": calculate_quality(ocr_text),
            "text_path": str(text_path),
        }

    except Exception as e:
        text_path = save_extracted_text(pdf_path, direct_text)

        return {
            "text": direct_text,
            "method": "failed_ocr",
            "ocr_quality": calculate_quality(direct_text),
            "text_path": str(text_path),
            "error": str(e),
        }