"""Verify that the openWakeWord package and Hey Jarvis model can load."""

print("Testing openWakeWord...")
from openwakeword.model import Model

model = Model(wakeword_models=["hey_jarvis"])
print("Wake-word model loaded successfully.")
print("Say: Hey Jarvis")
