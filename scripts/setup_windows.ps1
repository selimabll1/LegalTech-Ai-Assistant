python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env -ErrorAction SilentlyContinue
Write-Host "Next: install Ollama, then run: ollama pull qwen3:8b"
Write-Host "Run app: streamlit run app.py"
