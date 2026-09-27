"""
Harmonoid Wrapped — Windows SMTC Tracker (winrt edition)
Install: pip install winrt-runtime winrt-Windows.Media.Control winrt-Windows.Foundation
Run:     python tracker.py
"""

import asyncio
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "harmonoid_stats.db"
NOW_PATH = Path(__file__).parent / "now_playing.json"
POLL_INTERVAL = 3
MIN_PLAY_SECONDS = 10

def write_now_playing(playing, title=None, artist=None, last_title=None, last_artist=None, position_s=0, duration_s=0):
    import json
    data = {
        "playing": playing,
        "title": title,
        "artist": artist,
        "last_title": last_title,
        "last_artist": last_artist,
        "position_s": round(position_s, 1),
        "duration_s": round(duration_s, 1),
        "updated_at": datetime.now().isoformat(),
    }
    try:
        with open(NOW_PATH, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plays (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            artist     TEXT,
            album      TEXT,
            started_at TEXT NOT NULL,
            ended_at   TEXT,
            duration_s INTEGER DEFAULT 0,
            source     TEXT DEFAULT 'harmonoid'
        )
    """)
    conn.commit()
    conn.close()
    print(f"[DB] Ready at {DB_PATH}")

def save_play(title, artist, album, started_at, ended_at, duration_s):
    if duration_s < MIN_PLAY_SECONDS:
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO plays (title,artist,album,started_at,ended_at,duration_s) VALUES (?,?,?,?,?,?)",
        (title, artist, album,
         started_at.isoformat(), ended_at.isoformat(), int(duration_s))
    )
    conn.commit()
    conn.close()
    mins, secs = divmod(int(duration_s), 60)
    print(f"[LOG] {artist} — {title}  ({mins}m {secs}s)")

async def run_tracker():
    try:
        from winrt.windows.media.control import \
            GlobalSystemMediaTransportControlsSessionManager as SessionManager
        from winrt.windows.media.control import \
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus
    except ImportError:
        print("[ERROR] winrt packages not found.")
        print("  Run: pip install winrt-runtime winrt-Windows.Media.Control winrt-Windows.Foundation")
        sys.exit(1)

    print("[TRACKER] Harmonoid Wrapped is running.")
    print(f"[TRACKER] Polling every {POLL_INTERVAL}s — play something in Harmonoid!")
    print("[TRACKER] Press Ctrl+C to stop.\n")

    manager = await SessionManager.request_async()

    current_title  = None
    current_artist = None
    current_album  = None
    play_start     = None
    last_title     = None
    last_artist    = None

    while True:
        try:
            sessions = manager.get_sessions()
            session  = None

            for s in sessions:
                src = (s.source_app_user_model_id or "").lower()
                if "harmonoid" in src:
                    session = s
                    break

            if session is None:
                write_now_playing(False, last_title=last_title, last_artist=last_artist)
                await asyncio.sleep(POLL_INTERVAL)
                continue

            info   = await session.try_get_media_properties_async()
            status = session.get_playback_info()

            if info is None:
                write_now_playing(False, last_title=last_title, last_artist=last_artist)
                await asyncio.sleep(POLL_INTERVAL)
                continue

            title  = info.title       or "Unknown"
            artist = info.artist      or "Unknown Artist"
            album  = info.album_title or ""

            playing = (
                status is not None and
                status.playback_status == PlaybackStatus.PLAYING
            )

            # Get playback position and duration from timeline
            position_s = 0.0
            duration_s = 0.0
            try:
                tl = session.get_timeline_properties()
                if tl:
                    # Try position
                    for attr in ('position', 'start_time', 'min_seek_time'):
                        v = getattr(tl, attr, None)
                        if v is not None:
                            try: position_s = v.total_seconds(); break
                            except:
                                try: position_s = float(v)/1e7; break
                                except: pass
                    # Try duration/end
                    for attr in ('end_time', 'max_seek_time', 'duration'):
                        v = getattr(tl, attr, None)
                        if v is not None:
                            try:
                                duration_s = v.total_seconds()
                                if duration_s > 0: break
                            except:
                                try:
                                    duration_s = float(v)/1e7
                                    if duration_s > 0: break
                                except: pass
                    # Debug: print attrs if still no duration
                    if duration_s == 0:
                        attrs = [a for a in dir(tl) if not a.startswith('_')]
                        print(f"[DEBUG] Timeline attrs: {attrs}")
                        for a in attrs:
                            try: print(f"[DEBUG]   {a} = {getattr(tl,a)}")
                            except: pass
            except Exception as e:
                print(f"[DEBUG] Timeline error: {e}")

            # Track changed — save previous
            if (title != current_title or artist != current_artist) and current_title:
                if play_start:
                    elapsed = (datetime.now() - play_start).total_seconds()
                    save_play(current_title, current_artist, current_album,
                              play_start, datetime.now(), elapsed)
                    last_title, last_artist = current_title, current_artist
                current_title = current_artist = current_album = play_start = None

            # New track playing
            if playing and title != current_title:
                current_title  = title
                current_artist = artist
                current_album  = album
                play_start     = datetime.now()
                print(f"[NOW]  {artist} — {title}")

            # Paused — save and reset
            elif not playing and current_title and play_start:
                elapsed = (datetime.now() - play_start).total_seconds()
                save_play(current_title, current_artist, current_album,
                          play_start, datetime.now(), elapsed)
                last_title, last_artist = current_title, current_artist
                current_title = current_artist = current_album = play_start = None

            write_now_playing(
                playing and bool(current_title),
                title=current_title, artist=current_artist,
                last_title=last_title, last_artist=last_artist,
                position_s=position_s, duration_s=duration_s
            )

        except Exception as e:
            print(f"[WARN] {e}")

        await asyncio.sleep(POLL_INTERVAL)

def main():
    init_db()
    try:
        asyncio.run(run_tracker())
    except KeyboardInterrupt:
        print("\n[TRACKER] Stopped. Stats saved.")

if __name__ == "__main__":
    main()
