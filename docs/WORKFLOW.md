# Workflow

## Final target workflow

1. User opens Streamlit app.
2. App connects to LegalTech mailbox.
3. App detects new LegalTech emails.
4. App extracts PDF attachments.
5. App avoids duplicate emails using `processed_emails` history.
6. App extracts text from PDFs or uses OCR.
7. App sends clean text to local Ollama LLM.
8. LLM returns structured JSON.
9. Scoring engine calculates risk/opportunity scores.
10. Results are displayed and exported to Excel.
11. Human team validates, corrects or rejects rows.
12. Corrected Excel is imported.
13. Feedback rules are created.
14. Future prompts include relevant feedback rules.

## Recommended development order

1. Manual PDF MVP.
2. OCR + LLM + Excel.
3. Human correction + feedback memory.
4. Pilot on 10 PDFs.
5. Email automation after IT confirms authentication method.
