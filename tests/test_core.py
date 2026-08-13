import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from golf_replay.config import AppConfig
from golf_replay.media import load_video, save_video
from golf_replay.models import AppState, SavedSwing, Session
from golf_replay.state import StateController
from golf_replay.storage import LocalStore


class StateControllerTests(unittest.TestCase):
    def test_impacts_are_accepted_only_while_ready(self):
        state = StateController()
        self.assertFalse(state.request_impact(4.0, now=10.0))
        state.transition(AppState.READY)
        self.assertTrue(state.request_impact(4.0, now=10.0))
        self.assertEqual(state.consume_impact(), 10.0)
        state.transition(AppState.REPLAYING)
        self.assertFalse(state.request_impact(4.0, now=20.0))

    def test_cooldown_blocks_duplicate_impacts(self):
        state = StateController()
        state.transition(AppState.READY)
        self.assertTrue(state.request_impact(4.0, now=10.0))
        state.consume_impact()
        self.assertFalse(state.request_impact(4.0, now=12.0))
        self.assertTrue(state.request_impact(4.0, now=14.0))

    def test_transition_out_of_ready_clears_pending_impact(self):
        state = StateController()
        state.transition(AppState.READY)
        state.request_impact(0.0, now=10.0)
        state.transition(AppState.CAPTURING)
        self.assertIsNone(state.consume_impact())


class StorageTests(unittest.TestCase):
    def test_users_sessions_and_totals_round_trip(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            store = LocalStore(root)
            user = store.add_user("Matt")
            self.assertEqual(store.add_user("matt").id, user.id)
            session = Session.create(user)
            session.record_shot("7 IRON")
            session.record_shot("7 IRON")
            session.record_shot("PW")
            session.finish()
            self.assertGreaterEqual(session.duration_seconds(), 0)
            store.save_session(session)

            loaded = LocalStore(root)
            self.assertEqual(len(loaded.users), 1)
            self.assertEqual(loaded.user_totals(user.id), (3, 1, {"7 IRON": 2, "PW": 1}))

    def test_only_explicit_saved_swing_records_are_persisted(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            store = LocalStore(root)
            self.assertEqual(store.saved_swings, [])
            swing = SavedSwing(
                id="swing", session_id="session", user_id=None,
                user_name="Quick Practice", club="UNSPECIFIED", shot_number=1,
                captured_at="2026-08-11T12:00:00-04:00",
                video_path="saved_swings/swing.mp4", impact_frame=90, fps=30.0,
            )
            store.add_saved_swing(swing)
            self.assertEqual(LocalStore(root).saved_swings[0].id, "swing")


class ConfigTests(unittest.TestCase):
    def test_config_round_trip_and_ignores_future_fields(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            AppConfig(replay_speed=0.5).save(path)
            raw = json.loads(path.read_text())
            raw["future_setting"] = True
            path.write_text(json.dumps(raw))
            self.assertEqual(AppConfig.load(path).replay_speed, 0.5)


class VideoTests(unittest.TestCase):
    def test_selected_video_can_be_encoded_and_loaded(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "selected.mp4"
            frames = [np.full((72, 128, 3), index * 10, dtype=np.uint8) for index in range(6)]
            saved_path = save_video(frames, path, 30.0)
            loaded, fps = load_video(saved_path)
            self.assertTrue(saved_path.exists())
            self.assertEqual(len(loaded), len(frames))
            self.assertGreater(fps, 0)


if __name__ == "__main__":
    unittest.main()
