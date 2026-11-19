# Vision adapter (optional, experimental, off by default)

A thinking-layer adapter (`docs/agency-spec.md` section 4) that shows an uploaded picture to **Gemma 4 E4B running in a local container** and adds a short description and any text it can read. Everything the plain image adapter reports (size, EXIF, colours, thumbnail) is kept. The plain image adapter (`addons/image-adapter`) stays model-free and is the default.

**Why it is separate.** The image adapter's rule is: no model looks at a picture until a licence is accepted and a benchmark exists. Neither is true yet, so this one is opt-in, labelled *experimental* in the manifest and in the UI, and says so on every result.

```bash
AGENCY_ADAPTERS=http://table-adapter:8091,http://document-adapter:8092,http://vision-adapter:8095 docker compose --project-directory . \
  -f <pack compose> -f addons/thinking-layer/docker-compose.layer.yml -f addons/vision-adapter/docker-compose.vision.yml up --build
```

Use it **instead of** `image-adapter` in `AGENCY_ADAPTERS`: the layer picks the first adapter that accepts a file. The sidecar build downloads about 5 GB from Hugging Face at a pinned revision and **fails if either file's SHA-256 differs** (pins: `demos/benchmark/local-models/models.json`).

## What was checked (2026-11-19, laptop Docker, 8 GB)
- 9 unit tests (`python3 -m unittest discover -s addons/vision-adapter/tests`, needs Pillow): reply parsing, resize to 1024 px, metadata stripped from what the model sees, GPS never sent, model failure still returns the file details.
- Live: a generated picture with the words "WAREHOUSE 7" came back described, with the text read exactly, in 32 s on CPU. It missed the small red circle. One picture; nothing else tried.

## Limits and known problems
- **Not benchmarked.** No accuracy number exists for pictures. Treat the description as a hint.
- **Thinking must be off.** Gemma 4 thinks by default under llama.cpp's `--jinja`; the first live call spent all 400 output tokens thinking and returned an empty answer, after 4 minutes. The sidecar now starts with `--reasoning off`.
- **Memory.** The first try was killed for memory on an 8 GB Docker (exit 137) when a second request arrived; with `-c 4096` and reasoning off it ran. Plan for 6 GB or more for this container alone, and do not run it beside the full stack on an 8 GB laptop.
- **Speed.** Tens of seconds per picture on CPU; a GPU would be much faster. Requests are one at a time (`--parallel 1`).
- **Audio is not wired.** The server logs "audio input is in experimental stage" for this model, so speech may work, but no adapter, test or benchmark exists. BirdNET and CLAP stay the audio tools: Gemma's audio is speech, not bird identification.
- **Licence.** Gemma 4's model card says Apache-2.0 but links a separate licence page that counsel has not read. It is not in the licence register. Do not ship this beyond a demo until it is.
- Not tested through the layer or in the browser with a real session; the UI block type-checks but was not looked at.
