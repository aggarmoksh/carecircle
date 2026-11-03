"""Filming steps for the two demo scenes (docs/VIDEO_SCRIPT.md), printed by tools/demo_reset.py. Phones are named by their role (r1 = Arjun's iPhone, r2 = Meena's CMF phone, r3 = Kabir's phone);
no numbers, keys or tokens appear here. The tool sends nothing: every message below is sent by a person on a phone, or by the system in reply."""

COMMON = """\
Before filming (once): the tunnel is running and is not restarted; from r1, r2 and r3 re-join the sandbox if it has expired, then send "hi" from each phone (this opens the 24 h window).
Sends are spaced: the sandbox accepts one message every 3 seconds, so the app waits between sends and a burst of relays takes a few seconds. Do not send from the phones faster than that.
Mode: the server must be LIVE (CARECIRCLE_DRY_RUN not set), otherwise nothing reaches the phones.
Board: your own link, 1440 wide, light mode, zoom 110%. Members Sunita and Sofía are simulated: nothing arrives on a phone for them; look for them in the Activity feed (details)."""

MONDAY = """\
SCENE monday: fresh circle, no schedule yet, every member's update choice set to "everything" for filming, patient clock Monday 07:55 (Kolkata).
Note: the real defaults differ. Outside this scene a remote member (Arjun, Kabir, Sofía) starts on "alerts and a daily summary", so these relays would wait for the 8 PM summary; a nearby member (Meena, Sunita) starts on "everything".
Beat 0:20-0:55 (the discharge sheet)
  1. r2 (Meena's phone): send the photo of the printed discharge sheet.
     Arrives on r2, in Hindi: "मैंने यह पढ़ा:", the medicine lines exactly as extracted, then "यह सूची शुरू करने के लिए 'हाँ' या YES लिखें, या बताएं क्या गलत है।"
  2. r2: reply YES (or हाँ).
     Arrives on r2: "Schedule started: 4 medicine(s) are now live. I'll check in on each dose."
     Arrives on r1 (Arjun, English) and r3 (Kabir, English): "Meena confirmed the schedule for Nanaji: 4 medicine(s) are now live."
     Board: the Today rail fills in; Activity shows the confirmation (Sofía's copy is in Spanish under "details").
Beat 0:55-1:15 (the Hindi voice note), between 08:00 and 08:15 on the board clock
  3. r2: record the Hindi voice note "Maine Nanaji ko subah ki metformin de di."
     Arrives on r2, in Hindi: "दर्ज हो गया: सुबह 8 बजे वाली metformin दवा दी गई (Meena)। धन्यवाद।"
     Arrives on r1 and r3 (English): "CareCircle: Meena gave metformin 08:00."
     Board: the metformin 08:00 marker turns given; Activity shows Sofía's copy in Spanish ("Meena le dio a Nanaji metformin de las 8 de la mañana (a las 8:0x de la mañana).").
     If you wait past 08:15, Meena first gets the grouped nudge for the two doses nobody has reported (amlodipine, aspirin): "नमस्ते Meena, क्या Nanaji ने सुबह 8 बजे वाली amlodipine और aspirin दवा ले ली? ..." Reply "done" to close both.
Beat 2:15-2:38 (the lab report), any time after the schedule is live
  4. r3 (Kabir's phone): send the photo of the printed lab report.
     Arrives on r3: the lab summary, ending "I can't interpret results. Reply YES if this matches the paper."
  5. r3: reply YES.
     Arrives on r3: "Saved. The lab report from 29 Oct is now in the care record."
     Arrives on r1 (English): "Kabir added a lab report from 29 Oct: 4 values are outside the lab's printed range. See the board. Board (optional): <Arjun's own link>"
     Arrives on r2 (Hindi): "Kabir ने 29 अक्टूबर की लैब रिपोर्ट जोड़ी: 4 नतीजे लैब की छपी हुई रेंज से बाहर हैं। बोर्ड पर देखें: <Meena's own link>"
     Board: the Lab values card shows "4 of 9 outside the lab's printed range".
  6. r3: send "is this bad?"
     Arrives on r3: "I can't give medical advice. I've noted this as a question for the doctor visit. Who will ask the doctor? Reply 'I will' to take it."
     Board: a task appears under Tasks.
  7. On the board tap "Doctor summary" (the one-page sheet)."""

THURSDAY = """\
SCENE thursday: Monday to Wednesday doses confirmed, Wednesday 20:00 recorded as missed, lab report L2 confirmed by Kabir, patient clock Thursday 07:55 (Kolkata), live mode.
Beat 1:15-1:55 (the ladder), the board's Now card
  1. Open the board's "Demo controls", type the admin token and "Set time" to {FILM_CLOCK} (Thursday 08:28:30 in Kolkata). At that moment it is 18:58 in Los Angeles, 02:58 in London and 03:58 in Madrid, so the numbers on screen match the script: about three minutes later Arjun's local time reads 19:01 and Kabir's 03:01. (Pressing "Jump to next due + grace" instead also works, but then London reads about 02:48.)
     Board: "Morning metformin, overdue", the three 08:00 doses as cards under it.
  2. Within a few seconds the scheduler catches up and runs the whole ladder, one step per second: Meena first, then Sunita, then Arjun, then Kabir and Sofía. Real sends are spaced 3 seconds apart, so Meena's message arrives first and Arjun's about 3 seconds later.
     Arrives on r2 (Meena), one private message, in Hindi: "नमस्ते Meena, क्या Nanaji ने सुबह 8 बजे वाली amlodipine, aspirin और metformin दवा ले ली? 'done' लिखें, या बताएं कौन सी ली।"  Do not answer.
     Sunita (simulated, nearby) is asked next; look for it in Activity. She has no phone.
     Arrives on r1 (Arjun, awake in Los Angeles, about 19:00 there): "CareCircle: Meena hasn't confirmed the 8 AM medicines for Nanaji yet (amlodipine, aspirin, metformin). Can you check and tell me?"
  3. The board timeline shows 08:28 for every step, because the clock was set to 08:28:30 and the scheduler caught up at once. Wait until the board clock reads 08:31 (about two and a half minutes), then film The Circle: Kabir reads "03:01 London" with "asleep, 02:58" under his name (the time he was skipped), Sofía "04:01 Madrid", "asleep, 03:58", Arjun "19:01 Los Angeles" with the orange arc to him. Kabir and Sofía are shown skipped while they sleep: nobody wakes them.
Beat 1:55-2:15 (the organiser photo)
  5. r2: send the photo of the ice-tray pill organiser (media/organiser_real/or1.jpeg).
     Arrives on r2, in Hindi: "दवा के डिब्बे में बुधवार शाम वाला हिस्सा अभी भरा है: वह दवा नहीं दी गई।"
     Board: the organiser grid outlines Wednesday PM.
Answer "done" from r2 at any time to close the three doses (the circle settles)."""


def steps(scene, film_clock_utc=None):
    """film_clock_utc: the UTC time that is 08:28:30 Kolkata on the scene's Thursday, as the demo clock field wants it."""
    text = {"monday": MONDAY, "thursday": THURSDAY}[scene]
    return COMMON + "\n\n" + text.replace("{FILM_CLOCK}", film_clock_utc or "<UTC time of 08:28:30 Kolkata on that Thursday>")
