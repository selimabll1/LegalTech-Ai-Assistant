from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PDF_RAW_DIR = DATA_DIR / "pdf_raw"
OCR_TEXT_DIR = DATA_DIR / "ocr_text"
OUTPUT_EXCEL_DIR = DATA_DIR / "output_excel"
FEEDBACK_DIR = DATA_DIR / "feedback"
PROCESSED_EMAILS_DIR = DATA_DIR / "processed_emails"
REFERENCE_DIR = DATA_DIR / "reference"
MODELS_DIR = BASE_DIR / "models"
ASSETS_DIR = BASE_DIR / "assets"

for folder in [
    PDF_RAW_DIR,
    OCR_TEXT_DIR,
    OUTPUT_EXCEL_DIR,
    FEEDBACK_DIR,
    PROCESSED_EMAILS_DIR,
    REFERENCE_DIR,
    MODELS_DIR,
    ASSETS_DIR,
]:
    folder.mkdir(parents=True, exist_ok=True)

OUTPUT_EXCEL_PATH = OUTPUT_EXCEL_DIR / "legaltech_analysis_output.xlsx"
FEEDBACK_MEMORY_PATH = FEEDBACK_DIR / "feedback_memory.json"
TRAINING_DATASET_PATH = FEEDBACK_DIR / "training_dataset.xlsx"
PROCESSED_EMAILS_PATH = PROCESSED_EMAILS_DIR / "emails_traites.xlsx"

EVENT_TAXONOMY_PATH = REFERENCE_DIR / "event_taxonomy.json"
PORTFOLIO_TEMPLATE_PATH = REFERENCE_DIR / "portfolio_companies_template.csv"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
TESSERACT_LANG = os.getenv("TESSERACT_LANG", "fra+eng")
APP_MODE = os.getenv("APP_MODE", "manual_pdf")
