# Quick Start — 15 Minutes

## Install

```bash
python -m venv .venv
pip install -r requirements.txt
```

## Local model

```bash
ollama pull qwen3:8b
ollama run qwen3:8b
```

## Run

```bash
streamlit run app.py
```

## First test

1. Put one legal announcement PDF in `data/pdf_raw/`.
2. Open the Streamlit URL.
3. Click `Analyser les PDFs`.
4. Click `Exporter vers Excel`.
5. Open the Excel output and simulate corrections.
6. Import the corrected Excel.
7. Check `data/feedback/feedback_memory.json`.
