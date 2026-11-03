"""Tunable settings. Everything a demo might change lives here."""
import os
GRACE_MIN = float(os.environ.get("CC_GRACE_MIN", 15))            # past due + grace before the first nudge
STEP_SECONDS = float(os.environ.get("CC_STEP_SECONDS", 60))      # delay between escalation steps
WAKE_START, WAKE_END = 8, 22                                    # members' local waking hours
WINDOW_HOURS = 24                                               # WhatsApp free-form window
IMAGE_CONF_THRESHOLD = 0.7
PATIENT_NAME = "Nanaji"
PATIENT_TZ = "Asia/Kolkata"
PHASE1_MESSAGE_CAP = int(os.environ.get("CC_MESSAGE_CAP", 80))      # outbound WhatsApp messages: the filming cap, counted from 2026-11-03
SEND_SPACING_SECONDS = 3.0                                          # the Twilio sandbox sends at most one message every 3 seconds; sends are spaced, never burst
DRY_RUN = os.environ.get("CARECIRCLE_DRY_RUN", "0") == "1"
