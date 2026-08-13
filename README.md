# Golf Swing Replay

A local, full-screen golf swing capture appliance. It maintains a rolling camera
buffer, detects impact through the microphone, captures the follow-through,
replays the swing in slow motion, and saves a video only when requested.

## Run

```bash
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The application creates `data/settings.json` on first launch. User, session, and
saved-swing metadata is stored as local JSON. Selected videos are stored under
`saved_swings/YYYY-MM-DD/`. MP4 is preferred; if the installed OpenCV build has
no working MP4 encoder, the application safely falls back to MJPEG/AVI.

## Controls

Menus use the arrow keys or W/S, Enter to select, and Escape to return.

During practice:

- `Space`: manually trigger a swing
- `P`: replay the previous swing
- `C`: change club
- `E` or `Escape`: end the session

During replay:

- `Space`: pause/resume
- `,` / `.`: previous/next frame
- Left/Right: seek half a second
- `+` / `-`: change speed
- `Z`: cycle zoom
- `R`: restart replay
- `Escape`: skip the remaining replay

At the save prompt, press `S` or Enter to save. Press `D` or Escape to discard.
No file is written if the prompt times out.

## Current scope

Camera and microphone calibration remains hardware-specific and is deferred.
Xbox controller support, interactive settings, dual cameras, high-speed capture,
and automatic swing analysis are also deferred.
