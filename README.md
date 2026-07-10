# UGFS-NA LegalTech AI Assistant — Project Starter

This folder is a ready-to-run baseline for the internship project.

## Project objective

Build an internal Streamlit application that transforms LegalTech legal announcements into structured business, legal and risk intelligence:

`PDF / LegalTech Email → OCR → Local LLM via Ollama → Risk/Opportunity Scoring → Excel Review → Feedback Memory`

The MVP starts with manual PDF upload. Email automation is intentionally Phase 2 because mailbox authentication may require IT validation.

## Main technologies

- Frontend / app runner: Streamlit
- Backend logic: Python modules
- OCR: Tesseract + PyMuPDF direct text extraction
- Local LLM: Ollama + local model such as `qwen3:8b`
- Review loop: Excel export/import
- Feedback memory: JSON
- Future ML scoring: optional regressors trained from corrected Excel rows

## Folder structure

```text
legaltech_ai_assistant_project/
├── app.py
├── config.py
├── requirements.txt
├── .env.example
├── assets/
│   └── ugfs_logo.jfif
├── data/
│   ├── pdf_raw/
│   ├── ocr_text/
│   ├── output_excel/
│   ├── feedback/
│   ├── processed_emails/
│   └── reference/
├── modules/
│   ├── email_reader.py
│   ├── pdf_extractor.py
│   ├── ocr_engine.py
│   ├── llm_analyzer.py
│   ├── feature_extractor.py
│   ├── scoring_engine.py
│   ├── excel_manager.py
│   ├── feedback_manager.py
│   └── ml_trainer.py
├── docs/
├── scripts/
└── tests/
```

## Quick start

### 1. Create virtual environment

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\activate
```

macOS / Linux:

```bash
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Ollama and local model

```bash
ollama pull qwen3:8b
ollama run qwen3:8b
```

Keep Ollama running in the background.

### 4. Configure environment

Windows:

```powershell
copy .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

### 5. Run the app

```bash
streamlit run app.py
```

## MVP workflow

1. Upload PDF files in the sidebar or copy them into `data/pdf_raw/`.
2. Click `Analyser les PDFs`.
3. Review results in Streamlit.
4. Click `Exporter vers Excel`.
5. Human reviewer fills `Statut_Revue`, corrected fields and comments.
6. Import the corrected Excel file.
7. The app updates `data/feedback/feedback_memory.json`.
8. Future analyses include these feedback rules in the LLM prompt.

## Important

This assistant does not give final legal advice. It produces preliminary analysis that must be validated by UGFS human experts.
