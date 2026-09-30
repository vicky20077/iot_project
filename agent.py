"""
agent.py
Optional Gemini conversational layer added on top of the existing safety system.

Important:
- This module does NOT decide whether an obstacle is dangerous.
- risk_engine.py + the existing fusion loop remain the safety decision layer.
- Gemini is used for conversation and for explaining the current situation when
  the user asks about it.
"""

import logging
import threading

import config

logger = logging.getLogger("obstacle_assistance.agent")


class GeminiAgent:
    """Friendly conversational agent with optional current-scene context."""

    SAFETY_WORDS = {
        "danger", "dangerous", "safe", "safety", "obstacle", "obstacles",
        "ahead", "front", "behind", "left", "right", "near", "nearby",
        "around", "surrounding", "surroundings", "distance", "approaching",
        "approach", "coming", "car", "truck", "bus", "person", "chair",
        "table", "stairs", "object", "objects", "what do you see",
        "what is in front", "what's in front", "what is around", "what's around",
    }

    def __init__(self, api_key=None, model=None, history_limit=8):
        self.api_key = config.GEMINI_API_KEY if api_key is None else api_key
        self.model = config.GEMINI_MODEL if model is None else model
        self.history_limit = max(2, int(history_limit))
        self._client = None
        self._lock = threading.Lock()
        self._history = []
        self._last_error = None

        if self.api_key:
            self._init_client()

    @property
    def configured(self):
        return bool(self.api_key)

    @property
    def connected(self):
        return self._client is not None

    @property
    def last_error(self):
        with self._lock:
            return self._last_error

    def _init_client(self):
        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
            logger.info("Gemini agent initialized with model %s", self.model)
        except Exception as exc:
            self._client = None
            with self._lock:
                self._last_error = str(exc)
            logger.exception("Gemini initialization failed")

    @classmethod
    def is_scene_question(cls, text):
        value = (text or "").lower().strip()
        return any(term in value for term in cls.SAFETY_WORDS)

    @staticmethod
    def _scene_prompt(context):
        if not context:
            return "CURRENT SENSOR CONTEXT: unavailable"
        return "CURRENT SENSOR CONTEXT:\n" + context

    def ask(self, question, scene_context=""):
        question = (question or "").strip()
        if not question:
            return "Please tell me what you would like to know."

        if not self._client:
            if not self.api_key:
                return "Gemini is not configured yet. Add your Gemini API key to the .env file."
            return "I cannot reach Gemini right now. Please check the Gemini configuration."

        scene_question = self.is_scene_question(question)
        context_block = self._scene_prompt(scene_context) if scene_question else (
            "Do not invent current sensor information. No live sensor context is needed "
            "unless the user explicitly asks about the current surroundings."
        )

        system_instruction = (
            "You are AIRA, a friendly voice assistant added to an AI obstacle "
            "assistance project for a visually impaired user. Be warm, concise, "
            "and natural because your response may be spoken aloud. You can discuss "
            "general topics such as AI, study, technology, projects, daily questions, "
            "and casual conversation.\n\n"
            "When the user asks about the current surroundings, use ONLY the supplied "
            "sensor context. Never invent an object, distance, direction, or risk. "
            "The local safety/risk engine is the authoritative safety layer; you must "
            "not override it or claim to guarantee safety. If the context says risk is "
            "CRITICAL or HIGH, clearly mention that fact.\n\n"
            "Keep normal answers reasonably short, normally 1-5 sentences."
        )

        with self._lock:
            history = list(self._history)

        contents = []
        for item in history:
            contents.append({"role": item["role"], "parts": [{"text": item["text"]}]})
        contents.append({
            "role": "user",
            "parts": [{"text": f"{context_block}\n\nUSER:\n{question}"}],
        })

        try:
            from google.genai import types
            response = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.4,
                    max_output_tokens=220,
                ),
            )
            answer = (getattr(response, "text", None) or "").strip()
            if not answer:
                answer = "I could not generate a response right now."

            with self._lock:
                self._history.extend([
                    {"role": "user", "text": question},
                    {"role": "model", "text": answer},
                ])
                self._history = self._history[-self.history_limit:]
                self._last_error = None

            return answer
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            logger.exception("Gemini request failed")
            return "I couldn't reach Gemini right now. Please check the connection or API configuration."

    def reset_conversation(self):
        with self._lock:
            self._history.clear()
