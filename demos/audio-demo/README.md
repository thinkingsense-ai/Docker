# Audio demo: Name That Sound

Play a bird sound, or bring your own clip, and see what an audio model makes of it, which recordings sound alike, and what the curated record says. A small web page and service beside the Ask app, not inside it (Ask cannot yet play audio, take an audio upload or run a model: see Server#95).

**What it does**
- **Bring a clip:** a *mystery bird* or *mystery fish* picked from the collection (species hidden until you press Reveal), your own file (wav, mp3, flac, ogg; first minute), a file dropped on the page, or a recording from the microphone.
- **What BirdNET hears:** the top 3 species with confidence, choosing among the 8 species in the collection (a stand-in for "species expected for this place and season"), and the top 1 unaided among all 11,560. When the two differ the page says so: unaided answers can be confidently wrong.
- **Reveal:** for a mystery clip, the recordist's species next to BirdNET's, with the plain statement that the model's label never replaces the record.
- **Sounds alike:** the 5 nearest recordings by CLAP audio vector, each with its spectrogram, a play button, country, call type and licence.
- **What the record says:** for the species BirdNET picked: recordings, countries, call types, Smithsonian NMNH specimen count, licence ("not for commercial use"), and four ready questions to ask the data in Ask (copied to the clipboard, then Ask opens).
- **A fish clip** shows the limits honestly: BirdNET is built for birds, so it finds nothing or something weak, and the page says it is not confident.

**As a thinking-layer adapter.** The service also answers `GET /adapter` (manifest) and `POST /ingest` (raw file, `X-Filename`), so Agency's drop zone can use it: see [addons/thinking-layer](../../addons/thinking-layer/README.md). The record keeps top 3 among the collection's species, the unaided top 1, the 5 nearest recordings, notes, the licence and four questions for the data; with a best guess under 30% (a demo constant, not calibrated) it says so and offers no species questions. No audio file or spectrogram is returned to Agency yet.

**Run it** (needs the data from `../multimodal-poc`: `fetch_data.py`, then `embed_audio.py`; torch, transformers, birdnet, soundfile, scipy)

```bash
demos/audio-demo/run.sh            # http://localhost:8090
docker compose -f demos/audio-demo/docker-compose.yml up --build    # the same in a container (large: torch; the first start downloads about 0.6 GB of models into a volume)
```

Put Ask beside it for the second half of the demo: `demos/sounds-pack/up-with-vectors.sh` (http://localhost:8080, demo / demo); set `ASK_URL` if Ask runs elsewhere.
Microphone recording works on `localhost` (a secure context); the page writes WAV itself, so no ffmpeg is needed.

**Demo script**
1. *Mystery bird*: play it, say what you hear. Press nothing yet: read BirdNET's top 3.
2. *Reveal*: the recordist's identification, and whether the model agrees. Run a few until you hit one where the unaided answer is confident and wrong (Northern Cardinal, "White-crowned Sparrow 95%"): that is the governance point.
3. *Sounds alike*: play two neighbours; note a different species can sound alike (the nearest recording is the same species about half the time).
4. Click a question under *What the record says* and paste it into Ask: where, when, how many specimens, which licence.
5. *Mystery fish*: the model admits it does not know.
6. Your own clip: record something at a window, or drop in a file.

**Limits.** 72 recordings, 8 bird species, one region. The "expected species" list is the collection, not a real place-and-season prior (BirdNET also ships a location model; not used here). The recordings and BirdNET's models are non-commercial licences: demo and research use only. The bird-versus-fish hint from CLAP is weak and only appears when BirdNET is not confident.
