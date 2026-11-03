# CareCircle demo video: script and shot list (3:00 max)

Advisor draft, 2026-11-03. Rule: real product footage carries the story. Royalty-free stock (Unsplash photos, credited in the README) only for the first 12 seconds of atmosphere, with no faces that could pass as patients. Captions on screen for every spoken line.

## Setup

- **Screen:** OBS, 1920x1080, 30 fps. Browser at 1440 wide on the board, light mode, zoom 110%.
- **Meena's phone (CMF, r2):** mirrored to the PC with scrcpy (`scrcpy --max-size 1080`), so it can sit beside the board in OBS.
- **Arjun's phone (iPhone, r1):** its built-in screen recording; import the clips afterwards.
- **Kabir (r3):** the third number, used for the lab-report beat.
- **Audio:** voiceover recorded separately in a quiet room, phone close to your mouth, normalised to -14 LUFS, true peak at or under -1 dBTP. Music only from the YouTube Audio Library, about 8 dB under the voice, ducked 6 dB under speech.
- **Before filming:** re-join the sandbox from all three phones and send "hi" from each. Start the tunnel once and don't restart it. Run `demo_reset --scene monday`.

## Beats

| Time | Screen | Voiceover (one take per line) |
|---|---|---|
| 0:00-0:12 | Two or three stock shots (hands on a phone at night, a pill organiser on a kitchen table, an airport window), then a WhatsApp group with "80 unread". | "When someone we love is ill, the people who care are scattered: a grandson in Los Angeles, a cousin in London, an aunt at home in Kolkata. One caregiver told us her sister wakes up to 80 messages and zero context." |
| 0:12-0:20 | Title card: "CareCircle", with the line "The care log that writes itself, in the chat you already use." | "CareCircle lives in WhatsApp. No app to install." |
| 0:20-0:55 | Monday scene. On Meena's phone she photographs the printed discharge sheet and sends it. CareCircle replies with the 4 medicines. She replies YES. Cut to Arjun's iPhone: "Meena confirmed the schedule." The board updates live beside it. | "Meena photographs the discharge sheet. Muse Spark reads every medicine, and nothing goes live until a family member says yes. Everyone else is told, and the board fills in by itself." |
| 0:55-1:15 | Meena records a Hindi voice note: "Maine Nanaji ko subah ki metformin de di." The log confirms it. Arjun gets the English relay; on the board, Sofía's Spanish copy appears under details. | "Meena speaks Hindi. Muse Voice Transcribe hears her, and every member reads the update in their own language." |
| 1:15-1:55 | Thursday scene (cut). The board's Now card: "Morning medicines, overdue." Meena gets one private message. Nobody answers. On The Circle, Kabir is skipped ("asleep, 03:01 London") and the arc moves to Arjun, who is awake at 19:01 in LA. His iPhone buzzes. | "When a dose isn't confirmed, CareCircle doesn't wake the whole group. It privately asks whoever is with him. Then the next person who's awake, wherever they are." |
| 1:55-2:15 | Meena photographs the ice-tray organiser. Reply: "Wednesday PM is still full in the organiser: that dose wasn't given." The board's organiser grid highlights Wednesday PM. | "One photo of the week's organiser shows what was actually taken, not just what someone remembers." |
| 2:15-2:38 | Kabir sends the printed lab report, then replies YES. The board's range bars show "4 of 9 outside the lab's printed range". Kabir asks "is this bad?" and the reply says no advice, task created. Tap "Doctor summary": the one-page sheet. | "Lab values are compared only with the range printed by the lab, and CareCircle never gives medical advice. Questions become tasks for the doctor's visit, and the doctor gets one clean page." |
| 2:38-2:50 | Simple numbers card: 78/78 fields read, 12/12 voice notes including Hindi and Punjabi, 14/14 organiser compartments on 8 real photos, 0 medicine names or doses outside the record. Small line: "We tested SAM 3.1 overlays and web search for medicine names; they missed our bar, so we didn't ship them." | "We pre-registered every test, and we left out what didn't pass." |
| 2:50-3:00 | The Circle full screen, then the closing card: "Built on Meta Muse Spark and Muse Voice Transcribe · WhatsApp prototype via the Twilio sandbox · Try the interactive replay: [replay URL]" | "Meta's assistant talks to one person. CareCircle coordinates everyone who cares." |

## Honesty lines (on screen, small, where they apply)

- At 0:20: "Fictional patient and data. Members Sunita and Sofía are simulated."
- At 1:15: "Demo clock: the board shows simulated time."

## Rehearsal checklist

Run the whole script once without recording. Time each beat, write down every glitch, and fix bugs only. Then record each beat separately, keeping the best take of each. The 9-second beats can be cut together in editing; never fake a reply that the system didn't send.
