import sys
import traceback
from pathlib import Path


# ============================================================
# Project root setup
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))


# ============================================================
# Imports from project modules
# ============================================================

try:
    from modules.ocr_engine import extract_pdf_text
    from modules.llm_analyzer import analyze_legal_text
    from modules.scoring_engine import score_analysis
    from modules.excel_manager import analysis_to_row
except Exception as e:
    print("ERROR: Could not import project modules.")
    print("Make sure you run this script from the project root:")
    print("python scripts\\test_one_pdf_pipeline.py")
    print("\nDetails:")
    print(e)
    sys.exit(1)


# ============================================================
# Locate PDF
# ============================================================

PDF_DIR = PROJECT_ROOT / "data" / "pdf_raw"

if not PDF_DIR.exists():
    print("ERROR: data/pdf_raw folder does not exist.")
    print("Create it and put one PDF inside.")
    sys.exit(1)

pdfs = sorted(PDF_DIR.glob("*.pdf"))

if not pdfs:
    print("ERROR: No PDF found in data/pdf_raw.")
    print("Put one PDF inside this folder:")
    print(PDF_DIR)
    sys.exit(1)

pdf_path = pdfs[0]


# ============================================================
# Test full pipeline
# ============================================================

print("=" * 90)
print("LEGALTECH AI ASSISTANT - ONE PDF PIPELINE TEST")
print("=" * 90)
print(f"Project root: {PROJECT_ROOT}")
print(f"PDF selected: {pdf_path.name}")
print("=" * 90)


try:
    # --------------------------------------------------------
    # 1. OCR / text extraction
    # --------------------------------------------------------

    print("\n[1/4] Extracting text from PDF...")
    ocr = extract_pdf_text(pdf_path)

    extracted_text = ocr.get("text", "")
    method = ocr.get("method", "unknown")
    quality = ocr.get("ocr_quality", 0)
    text_path = ocr.get("text_path", "-")
    error = ocr.get("error")

    print(f"Method used: {method}")
    print(f"OCR quality: {quality}")
    print(f"Text saved in: {text_path}")
    print(f"Extracted text length: {len(extracted_text)}")

    if error:
        print("\nOCR warning/error:")
        print(error)

    print("\nText preview:")
    print("-" * 90)
    print(extracted_text[:1500])
    print("-" * 90)

    if len(extracted_text.strip()) < 50:
        print("\nERROR: Extracted text is too short.")
        print("If this is a scanned PDF, check:")
        print("- tesseract --version")
        print("- pdftoppm -h")
        sys.exit(1)

    # --------------------------------------------------------
    # 2. AI analysis with Ollama
    # --------------------------------------------------------

    

    analysis = analyze_legal_text(
        extracted_text,
        ocr_quality=quality,
    )

    print("\nRaw AI analysis:")
    print("-" * 90)
    print(analysis)
    print("-" * 90)

    # --------------------------------------------------------
    # 3. Scoring
    # --------------------------------------------------------

    print("\n[3/4] Calculating risk/opportunity scores...")

    analysis = score_analysis(analysis, extracted_text)

    print("\nScored analysis:")
    print("-" * 90)
    print(analysis)
    print("-" * 90)

    # --------------------------------------------------------
    # 4. Convert to Excel row format
    # --------------------------------------------------------

    print("\n[4/4] Converting analysis to Excel row format...")

    row = analysis_to_row(
        analysis,
        pdf_path.name,
        1,
    )

    print("\nFinal row:")
    print("=" * 90)

    for key, value in row.items():
        print(f"{key}: {value}")

    print("=" * 90)
    print("\nSUCCESS: Full PDF pipeline works.")
    print("Next step: run Streamlit app:")
    print("streamlit run app.py")

except Exception as e:
    print("\nERROR: Full pipeline failed.")
    print("Details:")
    print(e)

    print("\nFull traceback:")
    traceback.print_exc()

    print("\nPossible fixes:")
    print("1. Make sure Ollama is running.")
    print("2. Run: ollama list")
    print("3. If qwen3:8b is missing, run: ollama pull qwen3:8b")
    print("4. Test: ollama run qwen3:8b")
    print("5. Make sure your PDF text extraction worked with scripts/test_ocr_only.py")

    sys.exit(1)