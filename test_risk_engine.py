"""Focused tests for risk scoring, danger selection, and persistent queued voice."""

import unittest

from alerts import AlertLog
import risk_engine
from voice import VoiceAnnouncer


class RiskEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = risk_engine.RiskEngine()

    @staticmethod
    def detection(name="Person", box=(280, 120, 360, 360), confidence=0.9):
        return {"class": name, "confidence": confidence, "box": box}

    def evaluate(self, detections, distance, now):
        return self.engine.evaluate(
            detections, distance, frame_width=640, frame_height=480, now=now
        )

    def test_all_objects_scored_and_highest_score_selected(self):
        top, scored = self.evaluate([
            self.detection("Person", (270, 100, 370, 400)),
            self.detection("Chair", (250, 100, 390, 430)),
            self.detection("Table", (10, 200, 120, 400)),
        ], 90, 10.0)

        self.assertEqual(len(scored), 2)
        self.assertEqual(top, max(scored, key=lambda item: item["risk_score"]))
        self.assertNotIn("person", {item["object"].lower() for item in scored})
        self.assertEqual(top["object"], "Chair")
        self.assertEqual(top["distance_source"], "hc_sr04")
        self.assertTrue(all(item["object"] != "Person" for item in scored))
        self.assertIn(top["risk"], {"SAFE", "WATCH", "WARNING", "HIGH", "CRITICAL"})

    def test_distance_closer_increases_risk_and_ttc_falls_on_fast_approach(self):
        detection = self.detection("Car")
        first, _ = self.evaluate([detection], 120, 10.0)
        second, _ = self.evaluate([detection], 100, 11.0)
        third, _ = self.evaluate([detection], 40, 12.0)

        self.assertGreater(second["risk_score"], first["risk_score"])
        self.assertIsNotNone(third["approach_speed"])
        self.assertAlmostEqual(third["approach_speed"], 60.0)
        self.assertLess(third["ttc"], second["ttc"])
        self.assertFalse(third["blocking_path"])
        self.assertEqual(third["risk"], risk_engine.RISK_WATCH)

    def test_close_object_without_path_blockage_stays_silent_without_ttc(self):
        result, _ = self.evaluate([self.detection("Chair")], 20, 10.0)
        self.assertIsNone(result["ttc"])
        self.assertFalse(result["blocking_path"])
        self.assertEqual(result["risk"], risk_engine.RISK_WATCH)

    def test_close_path_blockage_alert_does_not_require_ttc(self):
        chair = self.detection("Chair", (250, 150, 390, 450))
        result, _ = self.evaluate([chair], 20, 10.0)
        self.assertIsNone(result["ttc"])
        self.assertTrue(result["blocking_path"])
        self.assertEqual(result["risk"], risk_engine.RISK_CRITICAL)

    def test_legacy_single_object_risk_api_remains_available(self):
        result = risk_engine.calculate_risk("Person", 0.9, 50)
        self.assertFalse(result["confirmed"])
        self.assertIsNone(result["object"])
        self.assertEqual(result["risk"], risk_engine.RISK_SAFE)

    def test_position_area_growth_and_distance_change_are_reported(self):
        first_box = (30, 100, 120, 280)
        larger_box = (20, 80, 140, 320)
        self.evaluate([self.detection("Chair", first_box)], None, 10.0)
        result, _ = self.evaluate(
            [self.detection("Chair", larger_box)], None, 11.0
        )
        self.assertEqual(result["direction"], "left")
        self.assertGreater(result["box_area"], 0)
        self.assertGreater(result["box_growth"], 0)
        self.assertIsNotNone(result["distance_change"])

    def test_all_person_case_variants_are_excluded_before_scoring(self):
        for index, name in enumerate(("person", "Person", "PERSON")):
            top, scored = self.evaluate(
                [self.detection(name, (250, 100, 390, 450))],
                20,
                10.0 + index,
            )
            self.assertIsNone(top)
            self.assertEqual(scored, [])
            self.assertEqual(self.engine._tracks, {})

    def test_person_is_excluded_but_other_objects_are_scored(self):
        top, scored = self.evaluate([
            self.detection("PERSON", (250, 100, 390, 450)),
            self.detection("Chair", (250, 150, 390, 450)),
            self.detection("Car", (250, 120, 400, 430)),
        ], 45, 10.0)
        labels = {item["object"].lower() for item in scored}
        self.assertEqual(labels, {"chair", "car"})
        self.assertIsNotNone(top)
        self.assertNotEqual(top["object"].lower(), "person")

    def test_legacy_api_excludes_person_case_variants(self):
        for class_name in ("person", "Person", "PERSON"):
            result = risk_engine.calculate_risk(class_name, 1.0, 1)
            self.assertFalse(result["confirmed"])
            self.assertIsNone(result["object"])
            self.assertEqual(result["risk"], risk_engine.RISK_SAFE)

    def test_off_path_approaching_vehicle_is_not_classified_as_danger(self):
        farther = self.detection("Car", (0, 180, 120, 350))
        closer = self.detection("Car", (0, 70, 120, 430))
        self.evaluate([farther], 250, 10.0)
        result, _ = self.evaluate([closer], 200, 10.5)
        self.assertFalse(result["path_overlap"])
        self.assertGreater(result["approach_speed"], 0)
        self.assertIn(result["risk"], (risk_engine.RISK_SAFE, risk_engine.RISK_WATCH))

    def test_entering_corridor_and_approaching_without_blockage_stays_watch(self):
        self.evaluate(
            [self.detection("Car", (100, 100, 180, 300))],
            200,
            10.0,
        )
        result, _ = self.evaluate(
            [self.detection("Car", (170, 100, 250, 300))],
            150,
            10.5,
        )
        self.assertTrue(result["entered_path"])
        self.assertGreater(result["approach_speed"], 0)
        self.assertFalse(result["blocking_path"])
        self.assertEqual(result["risk"], risk_engine.RISK_WATCH)

    def test_far_vehicle_moving_away_stays_low_risk(self):
        detection = self.detection("Car")
        first, _ = self.evaluate([detection], 400, 10.0)
        second, _ = self.evaluate([detection], 420, 10.5)
        self.assertLess(second["approach_speed"], 0)
        self.assertIsNone(second["ttc"])
        self.assertEqual(second["risk"], risk_engine.RISK_WATCH)

    def test_blocking_chair_is_a_path_warning(self):
        chair = self.detection("Chair", (250, 150, 390, 450))
        result, _ = self.evaluate([chair], 90, 10.0)
        self.assertTrue(result["path_overlap"])
        self.assertTrue(result["blocking_path"])
        self.assertIn(result["risk"], (
            risk_engine.RISK_WARNING, risk_engine.RISK_HIGH
        ))


class VoiceWorkerTests(unittest.TestCase):
    def test_three_different_dangers_are_processed_by_one_worker(self):
        voice = VoiceAnnouncer(enabled=False, cooldown=0)
        try:
            self.assertFalse(voice.announce("Person", 50, "HIGH", track_id=1))
            self.assertTrue(voice.announce(
                "Chair", 25, "CRITICAL", track_id=2, blocking_path=True
            ))
            self.assertTrue(voice.announce(
                "Car", 45, "HIGH", track_id=3, blocking_path=True
            ))
            self.assertTrue(voice.speak_text("Conversation remains independent", wait=True))
            voice._queue.join()
            self.assertTrue(voice._worker.is_alive())
        finally:
            voice.shutdown()
            voice._worker.join(timeout=1)

    def test_alert_log_rejects_person_case_insensitively(self):
        alerts = AlertLog()
        for class_name in ("person", "Person", "PERSON"):
            alerts.add(class_name, 5, "CRITICAL")
        self.assertEqual(alerts.recent(), [])

    def test_voice_rejects_person_case_insensitively(self):
        voice = VoiceAnnouncer(enabled=False, cooldown=0)
        try:
            for name in ("person", "Person", "PERSON"):
                self.assertFalse(voice.announce(name, 10, "CRITICAL", track_id=name))
            self.assertTrue(voice._queue.empty())
        finally:
            voice.shutdown()
            voice._worker.join(timeout=1)

    def test_tts_error_does_not_kill_worker(self):
        voice = VoiceAnnouncer(enabled=True, cooldown=3)
        attempts = []
        completed = []

        class FakeEngine:
            def say(self, text):
                attempts.append(text)
                if len(attempts) == 1:
                    raise RuntimeError("simulated TTS error")

            def runAndWait(self):
                completed.append(True)

        def initialize_engine():
            voice._engine = FakeEngine()

        voice._init_engine = initialize_engine
        try:
            self.assertTrue(voice.speak_text("first", wait=True))
            self.assertTrue(voice.speak_text("second", wait=True))
            voice._queue.join()
            self.assertEqual(len(attempts), 2)
            self.assertEqual(completed, [True])
            self.assertTrue(voice._worker.is_alive())
        finally:
            voice.shutdown()
            voice._worker.join(timeout=1)

    def test_alert_text_only_names_top_danger(self):
        text = VoiceAnnouncer.build_message(
            "Car", 200, "center", 40, 1.1, "HIGH"
        )
        self.assertEqual(text, "Warning. Car ahead.")

    def test_stationary_danger_does_not_repeat_each_frame(self):
        voice = VoiceAnnouncer(enabled=False, cooldown=0)
        try:
            self.assertTrue(voice.announce(
                "Car", 200, "HIGH", risk_score=0.72, track_id=1,
                blocking_path=True,
            ))
            self.assertFalse(voice.announce(
                "Car", 200, "HIGH", risk_score=0.72, track_id=1,
                blocking_path=True,
            ))
            voice._queue.join()
        finally:
            voice.shutdown()
            voice._worker.join(timeout=1)

    def test_safe_object_is_silent(self):
        voice = VoiceAnnouncer(enabled=False, cooldown=0)
        try:
            self.assertFalse(voice.announce(
                "Chair", 250, "SAFE", risk_score=0.1, track_id=1
            ))
            self.assertTrue(voice._queue.empty())
        finally:
            voice.shutdown()
            voice._worker.join(timeout=1)

    def test_new_danger_object_can_interrupt_cooldown(self):
        voice = VoiceAnnouncer(enabled=False, cooldown=30)
        try:
            self.assertTrue(voice.announce(
                "Chair", 70, "WARNING", risk_score=0.55, track_id=1,
                blocking_path=True,
            ))
            self.assertTrue(voice.announce(
                "Car", 70, "HIGH", risk_score=0.75, track_id=2,
                blocking_path=True,
            ))
            voice._queue.join()
        finally:
            voice.shutdown()
            voice._worker.join(timeout=1)

    def test_meaningful_increase_and_critical_transition_realert(self):
        voice = VoiceAnnouncer(enabled=False, cooldown=0)
        try:
            self.assertTrue(voice.announce(
                "Chair", 50, "HIGH", risk_score=0.72, track_id=1,
                blocking_path=True,
            ))
            self.assertFalse(voice.announce(
                "Chair", 45, "HIGH", risk_score=0.80, track_id=1,
                blocking_path=True,
            ))
            self.assertTrue(voice.announce(
                "Chair", 40, "HIGH", risk_score=0.90, track_id=1,
                blocking_path=True,
            ))
            self.assertTrue(voice.announce(
                "Chair", 20, "CRITICAL", risk_score=0.90, track_id=1,
                blocking_path=True,
            ))
            voice._queue.join()
        finally:
            voice.shutdown()
            voice._worker.join(timeout=1)

    def test_critical_alert_uses_stop_phrase(self):
        text = VoiceAnnouncer.build_message(
            "Car", 20, "center", None, None, "CRITICAL"
        )
        self.assertEqual(text, "Critical. Car ahead. Stop.")

    def test_auto_alert_does_not_include_distance_or_approach_details(self):
        text = VoiceAnnouncer.build_message(
            "Car", 200, "center", None, None, "HIGH"
        )
        self.assertEqual(text, "Warning. Car ahead.")

    def test_nonblocking_risk_is_rejected_even_if_caller_passes_high_level(self):
        voice = VoiceAnnouncer(enabled=False, cooldown=0)
        try:
            self.assertFalse(voice.announce(
                "Car", 20, "CRITICAL", track_id=1, blocking_path=False
            ))
            self.assertTrue(voice._queue.empty())
        finally:
            voice.shutdown()
            voice._worker.join(timeout=1)

    def test_camera_entry_or_motion_alone_does_not_queue_voice(self):
        voice = VoiceAnnouncer(enabled=False, cooldown=0)
        try:
            self.assertFalse(voice.announce(
                "Car", 150, "WATCH", track_id=1, blocking_path=False
            ))
            self.assertFalse(voice.announce(
                "Car", 100, "HIGH", track_id=1, blocking_path=False
            ))
            self.assertTrue(voice._queue.empty())
        finally:
            voice.shutdown()
            voice._worker.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
