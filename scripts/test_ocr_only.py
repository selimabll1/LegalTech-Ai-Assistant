import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.ocr_engine import extract_pdf_text


PDF_DIR = PROJECT_ROOT / "data" / "pdf_raw"
pdfs = list(PDF_DIR.glob("*.pdf"))

if not pdfs:
    print("No PDF found in data/pdf_raw/")
    print("Put one PDF in data/pdf_raw first.")
    sys.exit()

pdf_path = pdfs[0]

print(f"Testing OCR on: {pdf_path.name}")
print("-" * 80)

try:
    result = extract_pdf_text(pdf_path)

    print("OCR RESULT:")
    print(f"Method: {result.get('method')}")
    print(f"OCR quality: {result.get('ocr_quality')}")
    print(f"Text path: {result.get('text_path')}")

    text = result.get("text", "")

    print("\nTEXT LENGTH:")
    print(len(text))

    print("\nTEXT PREVIEW:")
    print("-" * 80)
    print(text[:2000])
    print("-" * 80)

    if len(text.strip()) > 50:
        print("\nSUCCESS: PDF text was extracted.")
    else:
        print("\nWARNING: Text is too short. OCR may not have worked.")

except Exception as e:
    print("\nERROR while testing OCR:")
    print(e)