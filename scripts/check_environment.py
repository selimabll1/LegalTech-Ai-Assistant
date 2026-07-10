
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DIRS = [
    "data/pdf_raw",
    "data/ocr_text",
    "data/output_excel",
    "data/feedback",
    "data/processed_emails",
    "data/reference",
    "assets",
]

PYTHON_IMPORTS = [
    ("streamlit", "streamlit"),
    ("pandas", "pandas"),
    ("openpyxl", "openpyxl"),
    ("fitz", "pymupdf"),
    ("pytesseract", "pytesseract"),
    ("pdf2image", "pdf2image"),
    ("PIL", "pillow"),
    ("requests", "requests"),
]


def print_status(label: str, ok: bool, detail: str = ""):
    icon = "OK" if ok else "FAIL"
    print(f"[{icon}] {label}")
    if detail:
        print(f"     {detail}")


def check_dirs():
    print("\n=== Project folders ===")
    for folder in REQUIRED_DIRS:
        path = PROJECT_ROOT / folder
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            print_status(folder, True, "Created")
        else:
            print_status(folder, True, "Exists")


def check_python_imports():
    print("\n=== Python packages ===")
    for import_name, package_name in PYTHON_IMPORTS:
        try:
            __import__(import_name)
            print_status(package_name, True)
        except Exception as e:
            print_status(package_name, False, str(e))


def run_command(command):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception as e:
        return str(e)


def check_command(command: str, version_args=None):
    if version_args is None:
        version_args = ["--version"]

    path = shutil.which(command)
    if not path:
        print_status(command, False, "Not found in PATH")
        return False

    output = run_command([command] + version_args)
    first_line = output.splitlines()[0] if output else "Found"
    print_status(command, True, first_line)
    return True


def check_ollama_model():
    print("\n=== Ollama ===")

    if not shutil.which("ollama"):
        print_status("ollama", False, "Install Ollama first")
        return

    output = run_command(["ollama", "list"])

    if "qwen3" in output:
        print_status("qwen3 model", True, "Model found in ollama list")
    else:
        print_status("qwen3 model", False, "Run: ollama pull qwen3:8b")


def check_system_tools():
    print("\n=== System tools ===")
    check_command("tesseract", ["--version"])
    check_command("pdftoppm", ["-h"])


def main():
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Python executable: {sys.executable}")

    check_dirs()
    check_python_imports()
    check_system_tools()
    check_ollama_model()

    print("\nDone.")


if __name__ == "__main__":
    main()