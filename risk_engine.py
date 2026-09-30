"""Risk scoring and lightweight frame-to-frame object tracking."""

import math
import time

import config

RISK_SAFE = "SAFE"
RISK_WATCH = "WATCH"
RISK_MEDIUM = RISK_WATCH
RISK_WARNING = "WARNING"
RISK_HIGH = "HIGH"
RISK_CRITICAL = "CRITICAL"
RISK_UNKNOWN = "UNKNOWN"

_DEFAULT_OBJECT_RISK = {
    "car": 0.95,
    "vehicle": 0.95,
    "truck": 1.0,
    "bus": 1.0,
    "van": 0.9,
    "motorcycle": 0.9,
    "bicycle": 0.75,
    "scooter": 0.75,
    "large vehicle": 1.0,
    "wall": 0.9,
    "barrier": 0.9,
    "hole": 0.95,
    "manhole": 0.9,
    "construction obstacle": 0.9,
    "stairs": 0.75,
    "chair": 0.3,
    "table": 0.35,
    "sofa": 0.4,
    "door": 0.25,
    "dustbin": 0.3,
    "box": 0.3,
    "trolley": 0.4,
    "animal": 0.35,
    "dog": 0.35,
    "cat": 0.25,
    "horse": 0.45,
    "bird": 0.2,
    "cow": 0.45,
    "sheep": 0.35,
}

_CONDITIONAL_HAZARDS = {
    "chair", "table", "sofa", "door", "dustbin", "box",
    "trolley", "animal",
    "dog", "cat", "horse", "bird", "cow", "sheep",
}

_HIGH_POTENTIAL_HAZARDS = {
    "car", "vehicle", "bus", "truck", "van", "motorcycle", "bicycle", "scooter",
    "large vehicle", "wall", "barrier", "hole", "manhole",
    "construction obstacle", "stairs",
}


def is_safety_excluded_class(class_name):
    return isinstance(class_name, str) and class_name.strip().casefold() == "person"


def is_confident(confidence: float, threshold: float = None) -> bool:
    if threshold is None:
        threshold = config.CONFIDENCE_THRESHOLD
    try:
        return float(confidence) >= float(threshold)
    except (TypeError, ValueError):
        return False


def risk_from_distance(distance: float) -> str:
    if distance is None or distance < 0:
        return RISK_UNKNOWN
    if distance <= config.DISTANCE_CRITICAL_MAX:
        return RISK_CRITICAL
    if distance <= config.DISTANCE_HIGH_MAX:
        return RISK_HIGH
    if distance <= config.DISTANCE_MEDIUM_MAX:
        return RISK_WATCH
    return RISK_SAFE


def calculate_risk(object_name, confidence, distance, confidence_threshold=None):
    """Backward-compatible single-object distance assessment."""
    if is_safety_excluded_class(object_name):
        return {
            "object": None,
            "confidence": 0.0,
            "distance": None,
            "risk": RISK_SAFE,
            "confirmed": False,
        }

    confirmed = (
        bool(object_name) and is_confident(confidence, confidence_threshold)
    )
    try:
        confidence_value = float(confidence) if confidence is not None else 0.0
    except (TypeError, ValueError):
        confidence_value = 0.0
    try:
        distance_value = (
            round(float(distance), 1)
            if distance is not None and float(distance) >= 0 else None
        )
    except (TypeError, ValueError):
        distance_value = None

    return {
        "object": object_name if confirmed else None,
        "confidence": round(confidence_value, 4),
        "distance": distance_value,
        "risk": risk_from_distance(distance_value) if confirmed else RISK_SAFE,
        "confirmed": confirmed,
    }


class RiskEngine:
    """Score every detection, associating HC-SR04 data only with a central box."""

    def __init__(self):
        self._tracks = {}
        self._next_track_id = 1

    @staticmethod
    def _clamp(value, low=0.0, high=1.0):
        return max(low, min(high, value))

    @staticmethod
    def _object_risk(class_name):
        if is_safety_excluded_class(class_name):
            raise ValueError("Person detections are excluded from safety scoring")
        configured = getattr(config, "OBJECT_RISK_SCORES", {})
        scores = dict(_DEFAULT_OBJECT_RISK)
        scores.update(configured)
        return float(scores.get((class_name or "").strip().lower(), 0.5))

    @staticmethod
    def _is_excluded_from_safety(detection):
        return is_safety_excluded_class(detection.get("class"))

    def _find_track(self, detection, used_track_ids, now):
        class_name = detection["class"].strip().lower()
        x1, _, x2, _ = detection["box"]
        center_x = (x1 + x2) / 2.0
        width = max(float(detection.get("frame_width", 1)), 1.0)

        candidates = []
        for track_id, track in self._tracks.items():
            if track_id in used_track_ids or track["class"] != class_name:
                continue
            if now - track["updated_at"] > config.TRACK_MAX_GAP_SEC:
                continue
            delta = abs(center_x / width - track["center_x"])
            if delta <= config.TRACK_CENTER_TOLERANCE:
                candidates.append((delta, track_id))

        if candidates:
            return min(candidates)[1]

        track_id = self._next_track_id
        self._next_track_id += 1
        self._tracks[track_id] = {
            "class": class_name,
            "center_x": center_x / width,
            "updated_at": now,
            "distance": None,
            "distance_source": None,
            "area_ratio": None,
            "bottom_ratio": None,
            "path_overlap": None,
        }
        return track_id

    def evaluate(self, detections, ultrasonic_distance, frame_width, frame_height,
                 now=None):
        """Return all scored detections, highest-risk first, and the top result."""
        now = now if now is not None else time.monotonic()
        frame_width = max(float(frame_width or 0), 1.0)
        frame_height = max(float(frame_height or 0), 1.0)
        detections = [
            item for item in detections
            if not self._is_excluded_from_safety(item) and
            item.get("class") and item.get("box") and
            is_confident(item.get("confidence", 0))
        ]

        central_candidates = []
        tolerance = config.ULTRASONIC_CENTER_TOLERANCE
        for index, detection in enumerate(detections):
            x1, _, x2, _ = detection["box"]
            center_ratio = ((x1 + x2) / 2.0) / frame_width
            offset = abs(center_ratio - 0.5)
            if offset <= tolerance:
                central_candidates.append((offset, index))
        sensor_index = min(central_candidates)[1] if (
            central_candidates and ultrasonic_distance is not None and
            2 <= ultrasonic_distance <= 500
        ) else None

        used_track_ids = set()
        scored = []
        for index, detection in enumerate(detections):
            x1, y1, x2, y2 = detection["box"]
            box_width = max(0.0, float(x2 - x1))
            box_height = max(0.0, float(y2 - y1))
            area_ratio = self._clamp(
                (box_width * box_height) / (frame_width * frame_height)
            )
            height_ratio = box_height / frame_height
            center_x = (x1 + x2) / 2.0
            center_ratio = center_x / frame_width
            bottom_ratio = y2 / frame_height
            direction = (
                "left" if center_ratio < 0.4 else
                "right" if center_ratio > 0.6 else "center"
            )

            track_id = self._find_track(
                {**detection, "frame_width": frame_width},
                used_track_ids,
                now,
            )
            used_track_ids.add(track_id)
            track = self._tracks[track_id]
            previous_center_ratio = track["center_x"]
            previous_bottom_ratio = track["bottom_ratio"]
            center_delta = center_ratio - previous_center_ratio
            lateral_motion = (
                "right" if center_delta >= config.PATH_LATERAL_MOTION_DELTA
                else "left" if center_delta <= -config.PATH_LATERAL_MOTION_DELTA
                else "stationary"
            )
            corridor_min = 0.5 - config.PATH_CORRIDOR_HALF_WIDTH
            corridor_max = 0.5 + config.PATH_CORRIDOR_HALF_WIDTH
            path_overlap = (
                x2 / frame_width >= corridor_min and
                x1 / frame_width <= corridor_max
            )
            corridor_width = max(corridor_max - corridor_min, 0.01)
            corridor_coverage = self._clamp(
                (
                    min(x2 / frame_width, corridor_max) -
                    max(x1 / frame_width, corridor_min)
                ) / corridor_width
            )
            previous_path_overlap = track["path_overlap"]
            entered_path = (
                previous_path_overlap is False and path_overlap
            )
            lateral_speed = abs(center_delta) / max(
                now - track["updated_at"], 0.001
            )
            sudden_entry = (
                entered_path and
                lateral_speed >= config.PATH_SUDDEN_ENTRY_SPEED
            )
            crossing_path = (
                path_overlap and lateral_motion != "stationary"
            )
            movement_direction = (
                "crossing" if crossing_path else
                "approaching" if (
                    previous_bottom_ratio is not None and
                    bottom_ratio - previous_bottom_ratio >= config.VERTICAL_GROWTH_MOTION_DELTA
                ) else
                "moving away" if (
                    previous_bottom_ratio is not None and
                    previous_bottom_ratio - bottom_ratio >= config.VERTICAL_GROWTH_MOTION_DELTA
                ) else lateral_motion
            )

            if index == sensor_index:
                distance = float(ultrasonic_distance)
                distance_source = "hc_sr04"
            else:
                # Relative apparent-height estimate, not an independent sensor reading.
                reference_ratio = max(config.CAMERA_REFERENCE_HEIGHT_RATIO, 0.01)
                distance = self._clamp(
                    (config.CAMERA_REFERENCE_DISTANCE_CM * reference_ratio) /
                    max(height_ratio, 0.01),
                    config.CAMERA_DISTANCE_MIN_CM,
                    config.CAMERA_DISTANCE_MAX_CM,
                )
                distance_source = "camera_estimate"

            previous_at = track["updated_at"]
            elapsed = max(now - previous_at, 0.001)
            same_distance_source = track["distance_source"] == distance_source
            previous_distance = track["distance"] if same_distance_source else None
            previous_area = track["area_ratio"]

            distance_change = (
                previous_distance - distance
                if previous_distance is not None else None
            )
            approach_speed = (
                distance_change / elapsed if distance_change is not None else None
            )
            ttc = (
                distance / approach_speed
                if approach_speed is not None and approach_speed > 0 else None
            )
            box_growth = (
                (area_ratio - previous_area) / elapsed
                if previous_area is not None else None
            )

            class_key = detection["class"].strip().lower()
            object_risk = self._clamp(self._object_risk(class_key))
            distance_risk = self._clamp(
                (config.DISTANCE_RISK_RANGE_CM - distance) /
                config.DISTANCE_RISK_RANGE_CM
            )
            ttc_risk = (
                self._clamp(
                    (config.TTC_RISK_HORIZON_SEC - ttc) /
                    config.TTC_RISK_HORIZON_SEC
                )
                if ttc is not None else 0.0
            )
            speed_risk = self._clamp(
                (approach_speed or 0.0) / max(config.MAX_APPROACH_RISK_CM_PER_SEC, 1.0)
            )
            size_risk = self._clamp(
                area_ratio / max(config.BOX_AREA_RISK_MAX, 0.01)
            )
            growth_risk = self._clamp(
                max(box_growth or 0.0, 0.0) / max(config.BOX_GROWTH_RISK_PER_SEC, 0.01)
            )
            size_risk = max(size_risk, growth_risk)
            path_risk = float(path_overlap)
            ground_proximity = self._clamp(
                (bottom_ratio - config.GROUND_CONTACT_START_RATIO) /
                max(1.0 - config.GROUND_CONTACT_START_RATIO, 0.01)
            )
            obstruction_risk = self._clamp(
                path_risk * (
                    config.OBSTRUCTION_SIZE_WEIGHT * size_risk +
                    config.OBSTRUCTION_GROUND_WEIGHT * ground_proximity +
                    config.OBSTRUCTION_ENTRY_WEIGHT * float(entered_path)
                )
            )
            position_risk = path_risk
            blocking_path = bool(
                path_overlap and distance <= config.BLOCKING_DISTANCE_CM and
                bottom_ratio >= config.GROUND_CONTACT_START_RATIO and
                (size_risk >= config.BLOCKING_SIZE_RISK_MIN or
                 corridor_coverage >= config.BLOCKING_CORRIDOR_COVERAGE_MIN)
            )
            weights = config.RISK_WEIGHTS
            score = (
                weights["object"] * object_risk +
                weights["distance"] * distance_risk +
                weights["path"] * path_risk +
                weights["obstruction"] * obstruction_risk +
                weights["speed"] * (speed_risk if path_overlap else 0.0) +
                weights["ttc"] * (ttc_risk if path_overlap else 0.0) +
                weights["size"] * size_risk
            )
            physically_relevant = path_overlap

            if score >= config.RISK_CRITICAL_THRESHOLD:
                risk = RISK_CRITICAL
            elif score >= config.RISK_HIGH_THRESHOLD:
                risk = RISK_HIGH
            elif score >= config.RISK_WARNING_THRESHOLD:
                risk = RISK_WARNING
            elif score >= config.RISK_WATCH_THRESHOLD:
                risk = RISK_WATCH
            else:
                risk = RISK_SAFE

            if class_key in _CONDITIONAL_HAZARDS and not path_overlap:
                # A conditional object beside the route is not an obstacle merely
                # because it is large, close, or moving.
                score = min(score, config.RISK_NON_PATH_MAX_SCORE)
                risk = RISK_SAFE if score < config.RISK_WATCH_THRESHOLD else RISK_WATCH
            elif not path_overlap:
                score = min(score, config.RISK_NON_PATH_MAX_SCORE)
                risk = RISK_SAFE if score < config.RISK_WATCH_THRESHOLD else RISK_WATCH
            elif (
                class_key in _HIGH_POTENTIAL_HAZARDS and
                distance > config.HIGH_HAZARD_RELEVANCE_DISTANCE_CM and
                (ttc is None or ttc > config.TTC_RISK_HORIZON_SEC) and
                not blocking_path
            ):
                score = min(score, config.RISK_WATCH_THRESHOLD)
                risk = RISK_WATCH
            elif (
                class_key != "person" and
                class_key in _CONDITIONAL_HAZARDS and
                not blocking_path and not entered_path and
                distance > config.DISTANCE_HIGH_MAX
            ):
                score = min(score, config.RISK_WATCH_THRESHOLD)
                risk = RISK_WATCH
            elif physically_relevant and distance <= config.DISTANCE_CRITICAL_MAX:
                # Close path hazards alert without requiring TTC.
                risk = RISK_CRITICAL
                score = max(score, config.RISK_CRITICAL_THRESHOLD)
            elif physically_relevant and distance <= config.DISTANCE_HIGH_MAX:
                risk = RISK_HIGH
                score = max(score, config.RISK_HIGH_THRESHOLD)
            elif (
                physically_relevant and crossing_path and
                risk in (RISK_SAFE, RISK_WATCH)
            ):
                risk = RISK_WATCH
                score = max(score, config.RISK_WATCH_THRESHOLD)
            elif blocking_path and risk in (RISK_SAFE, RISK_WATCH):
                risk = RISK_WARNING
                score = max(score, config.RISK_WARNING_THRESHOLD)

            if not blocking_path:
                risk = (
                    RISK_WATCH
                    if score >= config.RISK_WATCH_THRESHOLD
                    else RISK_SAFE
                )

            track.update({
                "center_x": center_ratio,
                "updated_at": now,
                "distance": distance,
                "distance_source": distance_source,
                "area_ratio": area_ratio,
                "bottom_ratio": bottom_ratio,
                "path_overlap": path_overlap,
            })

            scored.append({
                "object": detection["class"],
                "confidence": round(float(detection.get("confidence", 0)), 4),
                "distance": round(distance, 1),
                "distance_source": distance_source,
                "box": [int(x1), int(y1), int(x2), int(y2)],
                "box_area": round(area_ratio, 4),
                "box_growth": round(box_growth, 4) if box_growth is not None else None,
                "distance_change": round(distance_change, 2) if distance_change is not None else None,
                "approach_speed": round(approach_speed, 2) if approach_speed is not None else None,
                "ttc": round(ttc, 2) if ttc is not None and math.isfinite(ttc) else None,
                "direction": direction,
                "movement_direction": movement_direction,
                "path_overlap": path_overlap,
                "entered_path": entered_path,
                "sudden_entry": sudden_entry,
                "crossing_path": crossing_path,
                "blocking_path": blocking_path,
                "physically_relevant": physically_relevant,
                "risk_score": round(score, 4),
                "risk": risk,
                "risk_components": {
                    "object": round(object_risk, 4),
                    "distance": round(distance_risk, 4),
                    "path": round(path_risk, 4),
                    "corridor_coverage": round(corridor_coverage, 4),
                    "obstruction": round(obstruction_risk, 4),
                    "speed": round(speed_risk, 4),
                    "ttc": round(ttc_risk, 4),
                    "size": round(size_risk, 4),
                    "position": round(position_risk, 4),
                },
                "track_id": track_id,
                "confirmed": True,
            })

        live_ids = {item["track_id"] for item in scored}
        self._tracks = {
            track_id: track for track_id, track in self._tracks.items()
            if track_id in live_ids and now - track["updated_at"] <= config.TRACK_MAX_GAP_SEC
        }
        risk_priority = {
            RISK_SAFE: 0,
            RISK_WATCH: 1,
            RISK_WARNING: 2,
            RISK_HIGH: 3,
            RISK_CRITICAL: 4,
        }
        scored.sort(
            key=lambda item: (
                risk_priority.get(item["risk"], 0),
                item["physically_relevant"],
                item["risk_score"],
            ),
            reverse=True,
        )
        return scored[0] if scored else None, scored
