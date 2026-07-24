# SPEC.md - SDD Specification for Intelligent FLAC Player

## 1. Overview
The goal is to enhance the Intelligent FLAC Player with a Spotify-style layout, dynamic window responsiveness, active playlist management, and a fix for the Previous/Rewind track button.

## 2. Backend Requirements (FastAPI in `main.py`)
1. **Playlist Song Management**:
   - `POST /api/playlists/{pid}/songs/{song_id}`: Add `song_id` to playlist `pid`'s `song_ids` array in SQLite if not already present.
   - `DELETE /api/playlists/{pid}/songs/{song_id}`: Remove `song_id` from playlist `pid`'s `song_ids` array in SQLite.
2. Maintain existing Bit-Perfect HiFi endpoints (`/api/hifi/*`), WebSocket stream, and transition endpoints intact.

## 3. Frontend Requirements (`index.html`)
1. **Responsive Layout**:
   - Change `.app-container` from fixed width/height limits to full viewport responsive layout (`width: 98vw; height: calc(100vh - 90px)`).
   - Ensure media queries allow scrolling and proper display without maximizing.
2. **Bottom Player Bar**:
   - Fixed bottom position (`position: fixed; bottom: 0; left: 0; width: 100vw; height: 80px`).
   - Contains: Track info & mini disc cover (left), Playback controls & progress slider (center), Transition selector & volume (right).
3. **Rewind Button Fix**:
   - Maintain `playedHistory` stack and `historyIndex`.
   - Clicking `⏪`: if `audio.currentTime > 3`, set `currentTime = 0`. Else if `historyIndex > 0`, play `playedHistory[--historyIndex]`.
4. **Active Playlist View & Song Controls**:
   - Center panel displays current playlist title, total tracks, `[+]` button to add song to another playlist, `[-]` button to remove song from active playlist.
   - Includes "Recomendaciones Inteligentes" button triggering `/api/songs/smart_next`.
