from datetime import datetime
from pathlib import Path
import time

import cv2

from .config import AppConfig
from .media import AudioImpactDetector, CameraCapture, CapturedSwing, load_video, save_video
from .models import AppState, DEFAULT_CLUBS, SavedSwing, Session, User, new_id
from .replay import ReplayPlayer
from .state import StateController
from .storage import LocalStore
from .ui import OpenCVUI, action_for_key, Action


class GolfReplayApplication:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parent.parent
        self.config_path = self.root / "data" / "settings.json"
        self.config = AppConfig.load(self.config_path)
        self.store = LocalStore(self.root)
        self.state = StateController()
        self.ui: OpenCVUI | None = None
        self.player: ReplayPlayer | None = None

    def run(self) -> None:
        self.ui = OpenCVUI(self.config)
        self.player = ReplayPlayer(self.ui, self.config)
        try:
            self._main_menu()
        finally:
            self.state.transition(AppState.EXITING)
            self.ui.close()

    @property
    def screen(self) -> OpenCVUI:
        assert self.ui is not None
        return self.ui

    @property
    def replay_player(self) -> ReplayPlayer:
        assert self.player is not None
        return self.player

    def _main_menu(self) -> None:
        options = ["START SESSION", "QUICK PRACTICE", "SWING HISTORY", "USERS", "SETTINGS", "EXIT"]
        while True:
            self.state.transition(AppState.MENU)
            choice = self.screen.menu("GOLF SWING REPLAY", options, "LOCAL AUTOMATIC SWING CAPTURE")
            if choice is None or choice == 5:
                return
            if choice == 0:
                user = self._select_user()
                if user is None:
                    continue
                club = self._select_club()
                if club:
                    self._practice_session(user, club)
            elif choice == 1:
                self._practice_session(None, "UNSPECIFIED")
            elif choice == 2:
                self._swing_history()
            elif choice == 3:
                self._users_screen()
            elif choice == 4:
                self._settings_screen()

    def _select_user(self) -> User | None:
        while True:
            options = [user.name for user in self.store.users] + ["CREATE USER", "GUEST", "BACK"]
            choice = self.screen.menu("SELECT GOLFER", options)
            if choice is None or choice == len(options) - 1:
                return None
            if choice < len(self.store.users):
                return self.store.users[choice]
            if choice == len(self.store.users):
                name = self.screen.prompt_text("CREATE USER", "Golfer name")
                if name:
                    try:
                        return self.store.add_user(name)
                    except (OSError, ValueError) as error:
                        self.screen.message("USER NOT SAVED", [str(error)])
            else:
                return User(id="guest", name="Guest")

    def _select_club(self, current: str | None = None) -> str | None:
        subtitle = f"CURRENT: {current}" if current else ""
        choice = self.screen.menu("SELECT CLUB", DEFAULT_CLUBS + ["BACK"], subtitle)
        if choice is None or choice == len(DEFAULT_CLUBS):
            return None
        return DEFAULT_CLUBS[choice]

    def _elapsed(self, started: float) -> str:
        total = int(time.monotonic() - started)
        return f"{total // 60:02d}:{total % 60:02d}"

    def _practice_session(self, user: User | None, club: str) -> None:
        session = Session.create(user)
        camera = CameraCapture(self.config)
        if not camera.open():
            self.screen.message("CAMERA UNAVAILABLE", [camera.last_error or "Unknown camera error"])
            return
        detector = AudioImpactDetector(self.config, self.state)
        detector.start()
        started = time.monotonic()
        user_name = user.name if user else "Quick Practice"
        last_swing: CapturedSwing | None = None
        try:
            self.state.transition(AppState.READY)
            while True:
                ok, frame, _ = camera.read(buffer_frame=True)
                if not ok or frame is None:
                    placeholder = self.screen.canvas()
                    self.screen.text(placeholder, "CAMERA FRAME LOST - RETRYING", (300, 360), 0.9, self.screen.theme.warning)
                    key = self.screen.show(placeholder, 30)
                    if key in (27, ord("e"), ord("E")):
                        break
                    continue
                display = self.screen.practice_frame(
                    frame, user_name, club, session.shot_count,
                    self._elapsed(started), detector.level, detector.healthy,
                    "READY - HIT WHEN READY",
                )
                key = self.screen.show(display, 1)
                if key in (27, ord("e"), ord("E")):
                    break
                if key in (ord("c"), ord("C")):
                    self.state.transition(AppState.MENU)
                    changed = self._select_club(club)
                    if changed:
                        club = changed
                    camera.clear_buffer()
                    self.state.transition(AppState.READY)
                    continue
                if key in (ord("p"), ord("P")) and last_swing is not None:
                    self.state.transition(AppState.REPLAYING)
                    self.replay_player.play(
                        last_swing.frames, last_swing.impact_index, last_swing.fps, replay_count=1
                    )
                    camera.clear_buffer()
                    self.state.transition(AppState.READY)
                    continue
                if key == 32:
                    self.state.request_impact(self.config.trigger_cooldown_seconds)
                impact_at = self.state.consume_impact()
                if impact_at is not None:
                    self.state.transition(AppState.CAPTURING)
                    swing = camera.capture_after_impact(
                        impact_at,
                        lambda captured: self.screen.show(
                            self.screen.practice_frame(
                                captured, user_name, club, session.shot_count + 1,
                                self._elapsed(started), detector.level, detector.healthy,
                                "IMPACT DETECTED - CAPTURING",
                            ), 1
                        ),
                    )
                    if not swing.frames:
                        self.screen.message("CAPTURE FAILED", ["No camera frames were captured."])
                        camera.clear_buffer()
                        self.state.transition(AppState.READY)
                        continue
                    shot_number = session.record_shot(club)
                    last_swing = swing
                    self.state.transition(AppState.REPLAYING)
                    self.replay_player.play(swing.frames, swing.impact_index, swing.fps)
                    self.state.transition(AppState.POST_REPLAY)
                    if self.screen.save_prompt(swing.frames[swing.impact_index], self.config.save_prompt_seconds):
                        self._save_swing(swing, session, user, club, shot_number)
                    camera.clear_buffer()
                    self.state.transition(AppState.READY)
        finally:
            self.state.transition(AppState.MENU)
            detector.close()
            camera.close()
            session.finish()
            try:
                self.store.save_session(session)
            except OSError as error:
                self.screen.message("SESSION NOT SAVED", [str(error)])
            self._session_summary(session)

    def _save_swing(self, swing: CapturedSwing, session: Session, user: User | None,
                    club: str, shot_number: int) -> None:
        swing_id = new_id()
        date_folder = datetime.now().strftime("%Y-%m-%d")
        path = self.store.saved_swings_dir / date_folder / f"swing_{swing_id[:12]}.mp4"
        try:
            path = save_video(swing.frames, path, swing.fps)
            record = SavedSwing(
                id=swing_id,
                session_id=session.id,
                user_id=user.id if user else None,
                user_name=user.name if user else "Quick Practice",
                club=club,
                shot_number=shot_number,
                captured_at=swing.captured_at,
                video_path=str(path.relative_to(self.root)),
                impact_frame=swing.impact_index,
                fps=swing.fps,
            )
            self.store.add_saved_swing(record)
            session.saved_count += 1
            self.screen.message("SWING SAVED", [f"{record.user_name} | {club} | Shot {shot_number}"], wait=False)
        except (OSError, ValueError) as error:
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
            self.screen.message("SWING NOT SAVED", [str(error)])

    def _session_summary(self, session: Session) -> None:
        lines = [f"Golfer: {session.user_name}", f"Total shots: {session.shot_count}"]
        lines.extend(f"{club}: {count}" for club, count in sorted(session.shots_by_club.items()))
        lines.append(f"Saved swings: {session.saved_count}")
        duration = session.duration_seconds()
        lines.append(f"Session time: {duration // 60}m {duration % 60}s")
        self.state.transition(AppState.SESSION_SUMMARY)
        self.screen.message("SESSION COMPLETE", lines)
        self.state.transition(AppState.MENU)

    def _swing_history(self) -> None:
        while True:
            choice = self.screen.menu(
                "SWING HISTORY",
                ["ALL SAVED SWINGS", "FILTER BY USER", "FILTER BY CLUB", "BACK"],
                "ONLY EXPLICITLY SAVED SWINGS",
            )
            if choice is None or choice == 3:
                return
            swings = self.store.saved_swings
            title = "ALL SAVED SWINGS"
            if choice == 1:
                names = sorted({swing.user_name for swing in swings})
                selected = self.screen.menu("FILTER BY USER", names + ["BACK"])
                if selected is None or selected == len(names):
                    continue
                title = names[selected]
                swings = [swing for swing in swings if swing.user_name == title]
            elif choice == 2:
                clubs = sorted({swing.club for swing in swings})
                selected = self.screen.menu("FILTER BY CLUB", clubs + ["BACK"])
                if selected is None or selected == len(clubs):
                    continue
                title = clubs[selected]
                swings = [swing for swing in swings if swing.club == title]
            self._browse_swings(list(reversed(swings)), title)

    def _browse_swings(self, swings: list[SavedSwing], title: str) -> None:
        while True:
            options = [
                f"{swing.captured_at[:10]}  {swing.user_name}  {swing.club}  SHOT {swing.shot_number}"
                for swing in swings
            ] + ["BACK"]
            choice = self.screen.menu(title, options)
            if choice is None or choice == len(swings):
                return
            swing = swings[choice]
            path = self.root / swing.video_path
            try:
                frames, fps = load_video(path)
                self.state.transition(AppState.REPLAYING)
                self.replay_player.play(frames, swing.impact_frame, fps, replay_count=1)
                self.state.transition(AppState.MENU)
            except OSError as error:
                self.screen.message("VIDEO UNAVAILABLE", [str(error)])

    def _users_screen(self) -> None:
        while True:
            options = [user.name for user in self.store.users] + ["CREATE USER", "BACK"]
            choice = self.screen.menu("USERS", options)
            if choice is None or choice == len(options) - 1:
                return
            if choice == len(self.store.users):
                name = self.screen.prompt_text("CREATE USER", "Golfer name")
                if name:
                    try:
                        self.store.add_user(name)
                    except (OSError, ValueError) as error:
                        self.screen.message("USER NOT SAVED", [str(error)])
            else:
                user = self.store.users[choice]
                shots, sessions, clubs = self.store.user_totals(user.id)
                lines = [f"Total shots: {shots}", f"Sessions: {sessions}"]
                lines.extend(f"{club}: {count}" for club, count in sorted(clubs.items()))
                self.screen.message(user.name.upper(), lines)

    def _settings_screen(self) -> None:
        lines = [
            f"Camera: {self.config.camera_index} | {self.config.requested_width}x{self.config.requested_height} @ {self.config.requested_fps:g} FPS",
            f"Capture: {self.config.pre_impact_seconds:g}s before / {self.config.post_impact_seconds:g}s after impact",
            f"Impact threshold: {self.config.impact_threshold:.3f} (calibration deferred)",
            f"Replay: {self.config.replay_speed:g}x, {self.config.replay_count} times",
            f"Save prompt timeout: {self.config.save_prompt_seconds:g}s",
            "Edit data/settings.json to change these values.",
            "Interactive settings controls are deferred.",
        ]
        self.screen.message("SETTINGS", lines)
