# Document adapter (PDF, DOCX, Markdown, text)

A thinking-layer adapter (`docs/agency-spec.md` section 4): `GET /adapter`, `GET /health`, `POST /ingest` (raw body, `X-Filename`). It reads the text and returns a description: pages and words, headings (DOCX heading styles and Markdown `#` lines; PDFs have none), the ten most frequent words, how many roughly 800-character passages the text splits into, and the first 1,200 characters. It stores nothing and sends nothing anywhere; the layer drops the file after the call and keeps only this record (private to the uploader, expires after `AGENCY_UPLOAD_HOURS`).

```bash
AGENCY_ADAPTERS=http://document-adapter:8092 docker compose --project-directory . -f demos/treasury-pack/docker-compose.treasury.yml -f addons/thinking-layer/docker-compose.layer.yml -f addons/document-adapter/docker-compose.document.yml up --build
```

Both adapters together: `AGENCY_ADAPTERS=http://table-adapter:8091,http://document-adapter:8092` and both compose files. The user also needs the Server's "upload files" grant. Tests: `python3 -m unittest discover -s addons/document-adapter/tests` (the PDF tests need `pip install pypdf` and are skipped without it).

**Dependency.** `pypdf` 7.1.0 (BSD-3-Clause per its package metadata, no dependencies) for PDFs; everything else is the standard library. It belongs in the licence register for counsel.

**What it does not do.** The document is not loaded into any data source or search index, so the Server cannot answer questions about its text yet (the record offers no "ask about this" prompts). No OCR: a scanned PDF has no text layer and is reported as having little or no text. PDF text comes out in reading order as best pypdf can; columns and tables are not reconstructed and there are no headings. First 300 PDF pages, 2,000,000 characters, 25 MB. Password-protected PDFs and DOCX files with a DTD are refused. Top words assume English. Legacy `.doc`, `.odt`, `.pptx` and HTML are not read. The container runs read-only as a non-root user.

Tested with minimal hand-built PDFs and DOCX files in the unit tests, one PDF made with reportlab, and a Markdown file through the layer and the browser. Not tested with PDFs from Word, Google Docs or a scanner, DOCX files saved by Word, or a real file picker.
