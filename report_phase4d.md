# Phase 4d report

Last feature block. Synthetic data only. No remote, no push, nothing published. Items 1 to 5 are done; item 6 (the live send to r1) waits for your "ready".

## Acceptance
| Check | Result |
|---|---|
| All tests pass | 202 passed (151 at the end of 4c, 51 new or updated; tests/test_phase4d.py has the new ones) |
| New tests for 1-3 | theme: no `prefers-color-scheme` anywhere (board, replay, card), light meta, dark only under `data-theme`, localStorage always in try/catch, and a headless-Chrome check that the replay stays light when the system asks for dark and goes dark only with the toggle; Spanish: every wording rule; templates: help, draft header and footer, medicine lines unchanged, YES words, skipped and unsure relays in three languages through the dose handler |
| Screenshots | outputs/board_p4d_1440x900_light.png (board top), outputs/board_p4d_390x844_light.png (phone), outputs/board_p4d_full_light.png |
| Updated language samples | outputs/p4c_language_samples.txt (now with skipped, unsure, help, draft and the Spanish fixes) |
| Both scenes reset cleanly | yes: a test runs each reset twice on one database and checks members, choices, schedule, events, labs, clock (Monday 07:55 and Thursday 07:55 Kolkata); another runs the command and checks that it prints the steps, shows no number or token, and sends nothing |
| Outbound scan | 60 saved texts: 0 medicine names, doses or lab values outside the record |

## 1. Theme
Light always; the system setting is ignored everywhere. Dark only through the toggle in the header, remembered in localStorage (read and written inside try/catch). The replay page and the board both do this; the Today card was already light only. `?theme=dark` still works for screenshots.

## 2. Spanish fixes (all four, and the replay page is rebuilt from them)
00:00-05:59 reads "de la madrugada" ("las 3 de la madrugada"; 06:00-11:59 is "de la mañana", 12:00-19:59 "de la tarde", 20:00-23:59 "de la noche"). The escalation message says "que {patient} haya tomado". The given-at time reads "(a las 8:07 de la noche)", and "(a la 1:05 de la tarde)" at one o'clock, which is the correct Spanish. The organiser message reads "el compartimento del jueves por la noche" (AM = mañana, PM = noche).

## 3. Remaining English-only messages
Fixed templates in Hindi and Spanish for help (your text), the draft header, the draft footer (your text), a header for the corrected draft ("अपडेट किया:" / "Actualizado:"), and the skipped and unsure relays. The medicine lines in the draft are inserted exactly as extracted. My wording, for you to read, is in outputs/p4c_language_samples.txt:
- skipped: hi "{giver} ने {patient} की {time_hi} वाली {meds} दवा छोड़ दी।"; es "{giver} se saltó {meds} de {time_es} de {patient}."
- unsure: hi "{giver} को पक्का नहीं है कि {patient} ने {time_hi} वाली {meds} दवा ली या नहीं।"; es "Hay dudas sobre si {patient} tomó {meds} de {time_es} ({giver})."
YES is accepted as "sí", "si", "haan", "हाँ" and "हां" as well as the English words. When the member says it to a lab-report draft it works the same way. The "Saved." prefix on the help text for an unrecognised photo is "सहेज लिया।" / "Guardado.".
Still English by design (not on your list): the lab-draft summary ("I can't interpret results. Reply YES if this matches the paper."), the "line N is marked ?" notes, the sender's own "Schedule started" and "Logged: skipped" replies, and relays about Nanaji taking a dose himself.

## 4. Now card
When the ladder has fewer than 4 steps, the open doses appear as cards under the timeline (as on the replay page); when nothing is open, today's doses. The 1440 screenshot shows it.

## 5. Demo scenes
`python tools/demo_reset.py --scene monday` and `--scene thursday` reset the database, move a running server's clock if ADMIN_TOKEN is set, and print: the mode (LIVE), how many of the 40 outbound messages are used, then the filming steps from docs/VIDEO_SCRIPT.md with which phone does what and what should arrive where (tools/scene_steps.py; phones are named r1, r2, r3, no numbers). Nothing is sent by the tool.
- **monday:** fresh circle, no schedule, clock Monday 07:55, every member's update choice set to "everything".
- **thursday:** as before (Monday to Wednesday confirmed, Wednesday 20:00 missed, lab report confirmed, clock Thursday 07:55).
- **Live mode:** the tool cannot start your server; it prints that CARECIRCLE_DRY_RUN must not be set and warns if it is set in the shell. The Thursday board I run for you on port 8000 stays dry-run, so it cannot message anybody.

### Where the script and the product differ (decide before filming)
1. **Monday choices.** With the Phase 4 defaults, remote members (Arjun, Kabir, Sofía) get only alerts and a daily summary, so "Meena confirmed the schedule" would not reach Arjun's iPhone until 8 PM. For filming I set all five members to "everything" in the monday scene. Say if you would rather keep the defaults and show the daily summary instead.
2. **Thursday ladder order.** Script: "Kabir is skipped, then the arc moves to Arjun". Product: after Meena, Sunita (simulated, nearby) is asked, then Arjun (the first remote member in the list). Kabir and Sofía show up as skipped (asleep) one or two minutes after Arjun is asked, not before. Sunita is asked in between and shows only in Activity. The steps printed for the scene say this. If you want Kabir to be seen first, the ladder order for remote members would have to change; that is a feature change, so I left it.
3. **Outbound cap.** 4 of 40 used. Each scene sends roughly 15 to 20 messages, so the cap will need a fresh counter file or a higher value before both are filmed.

## 6. Live send of the Today card to r1
Not sent. Ready when you say "ready": the server must be running and reachable at the public address with the same database, then `python tools/send_card_live.py --yes` sends one message (the card with the caption and Arjun's own link) and counts toward the cap. Without `--yes` it only says what it would do.

## Spend, commits
No model calls this phase; logged total $6.29 of $8.00. Commits: see git log (Phase 4d).

## Freeze
From here only fixes for bugs found in rehearsal, each with a test.
