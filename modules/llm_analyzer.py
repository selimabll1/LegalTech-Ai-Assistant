def run_pdf_analysis():
    pdfs = list_pdf_files()

    if not pdfs:
        st.markdown(
            "<div class='status-banner'>No PDF found in data/pdf_raw. Upload a PDF first.</div>",
            unsafe_allow_html=True,
        )
        return

    rows = []
    progress = st.progress(0)
    global_index = 1

    for pdf_idx, pdf_path in enumerate(pdfs, start=1):
        with st.status(f"Reading {pdf_path.name}", expanded=False):
            try:
                ocr = extract_pdf_text(pdf_path)
                extracted_text = ocr.get("text", "")
                ocr_quality = ocr.get("ocr_quality", 0)

                if len(extracted_text.strip()) < 50:
                    st.warning(
                        f"{pdf_path.name}: extracted text is too short. "
                        "Check Tesseract/Poppler if this PDF is scanned."
                    )
                    progress.progress(pdf_idx / len(pdfs))
                    continue

                chunks = segment_legal_document(
                    extracted_text,
                    pdf_name=pdf_path.name,
                    max_chunks=25,
                    max_chars=6500,
                    min_relevance=10,
                )

                if not chunks:
                    st.warning(f"{pdf_path.name}: no relevant legal announcements detected.")
                    progress.progress(pdf_idx / len(pdfs))
                    continue

                st.write(f"{len(chunks)} relevant announcement chunk(s) detected.")

                for chunk in chunks:
                    with st.status(
                        f"Analyzing {pdf_path.name} · {chunk['chunk_id']}",
                        expanded=False,
                    ):
                        analysis = analyze_legal_text(
                            chunk["text"],
                            ocr_quality=ocr_quality,
                        )

                        analysis["source_pdf"] = pdf_path.name
                        analysis["source_chunk_id"] = chunk["chunk_id"]
                        analysis["source_chunk_title"] = chunk["title"]
                        analysis["relevance_score"] = chunk["relevance_score"]
                        analysis["relevance_reasons"] = "; ".join(chunk["relevance_reasons"])

                        analysis = score_analysis(analysis, chunk["text"])

                        row = analysis_to_row(
                            analysis,
                            f"{pdf_path.name} | {chunk['chunk_id']}",
                            global_index,
                        )

                        # Useful extra columns for app display
                        row["Source_Chunk"] = chunk["chunk_id"]
                        row["Source_Title"] = chunk["title"]
                        row["Relevance_Score"] = chunk["relevance_score"]
                        row["Relevance_Reasons"] = "; ".join(chunk["relevance_reasons"])

                        rows.append(row)
                        global_index += 1

            except Exception as e:
                st.error(f"{pdf_path.name}: analysis failed. Details: {e}")

        progress.progress(pdf_idx / len(pdfs))

    st.session_state.results = rows

    if rows:
        st.markdown(
            f"<div class='success-banner'>Analysis complete: {len(rows)} legal announcement(s).</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='status-banner'>No legal announcement could be analyzed. Check OCR/text extraction.</div>",
            unsafe_allow_html=True,
        )