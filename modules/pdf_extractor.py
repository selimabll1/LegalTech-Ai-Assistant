from pathlib import Path
from config import PDF_RAW_DIR


def save_uploaded_pdf(uploaded_file) -> Path:
    PDF_RAW_DIR.mkdir(parents=True, exist_ok=True)

    safe_name = uploaded_file.name.replace(" ", "_")
    output_path = PDF_RAW_DIR / safe_name

    counter = 1
    while output_path.exists():
        stem = Path(safe_name).stem
        suffix = Path(safe_name).suffix
        output_path = PDF_RAW_DIR / f"{stem}_{counter}{suffix}"
        counter += 1

    output_path.write_bytes(uploaded_file.getbuffer())
    return output_path


def list_pdf_files():
    PDF_RAW_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(PDF_RAW_DIR.glob("*.pdf"))


def delete_pdf_file(pdf_name: str):
    path = PDF_RAW_DIR / pdf_name
    if path.exists():
        path.unlink()
        return True
    return False