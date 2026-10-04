# Capture: from a tap to a saved memory

What happens when someone records a memory, and why a recording is never lost once Stop is tapped. Requirements
section 4.1 is the spec.

## In the browser

1. **One tap starts.** Record on the phone's home screen, Record in the wide header, "Add a memory to this event" on
   an event, "Record a memory about ..." on a person: all open `/record?start=1&...`, which starts recording at once.
   The address carries where it was started from (`event`, `period`, `person`, `question`, or `quick` from home),
   and the screen says it ("Adding to: The wedding").
2. **While recording:** the elapsed time, a level meter, a big **Stop** and a **Cancel**, always on screen in both
   postures. Cancel throws the recording away and says so.
3. **Stop:** the recording plays back at once (the player works out its length: Chrome's recordings do not carry
   one), and goes into the upload queue.
4. **The upload queue** (`web/src/features/record/uploads.ts`) first writes the recording's bytes to IndexedDB on this
   device, then sends them in 1 MB chunks. Its state shows under the player: Waiting to upload, Uploading 40%,
   Saved (preparing the audio), Saved, or Not uploaded yet with **Try again** and **Delete it**. Recordings still on
   the device are listed on the record screen and the phone's home.
5. **If the tab closes, the battery dies or the connection drops,** the next visit to Memoir resumes the upload: it
   asks the server how many bytes it has and continues from there. The bytes leave the device only once the server
   has made the recording a memory.

**Advanced** (folded away on the record screen) chooses the microphone and tests it with a level meter. The choice is
remembered on that device; if the remembered microphone is gone, the default is used.

Browsers: Chrome and Edge (desktop and Android) and Firefox record WebM with Opus; Safari (macOS and iOS) records
MP4. The page asks for the microphone the first time.

## On the server

| Step | Route or job | What happens |
|---|---|---|
| Open | `POST /api/capture/uploads` | An upload session with the content type and the context, checked against the archive. Only recordings are accepted (415 otherwise) |
| Send | `PUT /api/capture/uploads/{id}?offset=N` | Appends a chunk (up to 8 MB). A chunk already received is accepted and ignored; a gap is refused with `409 wrong_offset` and the offset the server has |
| Resume | `GET /api/capture/uploads/{id}` | How many bytes arrived |
| Finish | `POST /api/capture/uploads/{id}/finalize` | The bytes become the **original** blob (kept forever) and a memory: the uploader's own person as storyteller, the context's event (its storyteller and anyone named become participants), person (mentioned) and question. A question's own event, period or person is used when the recording was
started from nothing else, and the question becomes answered (`docs/INTERVIEWER.md`). Finishing twice returns the same memory |
| Abort | `DELETE /api/capture/uploads/{id}` | The partial file is removed |
| Normalise | job `capture.normalize_audio` | ffmpeg makes a mono MP3 at 44.1 kHz and 128 kbps, stored as a second blob, and measures the length. The memory's `audio_state` goes from `normalising` to `normalised`. If ffmpeg is missing or fails, it is `not_normalised` and the original remains the recording, still played and transcribed |
| Play | `GET /api/memories/{id}/audio` | The MP3 (or the original when not normalised; `?original=true` for the original). Range requests work, so players can seek |

A 45-minute recording (11.8 MB of Opus) uploads in 12 chunks and normalises in about 8 seconds to a 43 MB MP3.
