# Image adapter (JPEG, PNG, GIF, WebP)

A thinking-layer adapter (`docs/agency-spec.md` section 4): `GET /adapter`, `GET /health`, `POST /ingest` (raw body, `X-Filename`). It **describes the file; it does not look at what is in the picture.** It returns format, size, frame count, transparency, selected metadata (camera make and model, software, dates, and a GPS position if the file has one), up to five dominant colours, and a 192-pixel thumbnail that the adapter re-encodes itself (no metadata and none of the uploaded bytes pass through). Nothing is stored or sent anywhere; the layer drops the file after the call and keeps only this record (private to the uploader, expires after `AGENCY_UPLOAD_HOURS`).

```bash
AGENCY_ADAPTERS=http://image-adapter:8093 docker compose --project-directory . -f demos/treasury-pack/docker-compose.treasury.yml -f addons/thinking-layer/docker-compose.layer.yml -f addons/image-adapter/docker-compose.image.yml up --build
```

All adapters: `AGENCY_ADAPTERS=http://table-adapter:8091,http://document-adapter:8092,http://image-adapter:8093` and each compose file. The user also needs the Server's "upload files" grant. Tests: `python3 -m unittest discover -s addons/image-adapter/tests` (needs `pip install pillow`; skipped without it).

**Why no model.** The measured results (`demos/multimodal-poc`) were poor for the one image case we tried: CLIP vectors of spectrograms matched species 29% of the time, added nothing to audio, and told bird from fish by picture style alone. Nothing measured justifies a "what is this a picture of" claim, so the adapter makes none. A model-based adapter (captioning, OCR, object labels) can be added as another adapter behind the same contract once there is a model with a licence counsel accepts and a benchmark to show.

**Dependency.** `pillow` 13.0.0 (MIT-CMU per its package metadata). It belongs in the licence register for counsel.

**Limits and safety.** 15 MB, 50 million pixels (checked from the header before decoding). SVG, TIFF, BMP and other formats are refused (SVG can carry script). A GPS position is shown to the uploader with a warning; it is in the in-memory record until it expires. The container runs read-only as a non-root user. Colours come from a 64-pixel copy with a coverage quantiser and ignore shares under 2%: approximate, not a palette tool. EXIF dates are as written by the camera, with no time zone.

Tested with pictures generated in the unit tests (EXIF and GPS, transparency, animation, SVG and TIFF refused, size limit, colour regression), through the layer, and one canvas-made JPEG in the browser. Not tested with photos from a phone or camera, HEIC (not supported), or a real file picker.
