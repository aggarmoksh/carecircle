# CareCircle design language

Advisor, 2026-11-02. For the web board, the doctor summary and the WhatsApp wording. Claude Code copies this file into the repo as docs/DESIGN.md.

## The idea in one line

A calm room where everyone who cares can see, at a glance, who is with the patient, who is awake, and what needs doing next. It feels warm and human, not clinical. It sits comfortably next to Meta's products without copying them.

## Who reads it, and where

- Judges watch it for about 60 seconds in a 1080p screen recording. Everything important must be readable at that size, with no hovering.
- Family members glance at it on a phone. The 390 px layout must work.
- A doctor gets the summary on paper. Print first.

## The signature element: The Circle

Top left of the board, an SVG ring:
- **The patient at the centre**, with their name and local time.
- **Members as round nodes on the ring.** Nearby members (hands_on) sit on the inner ring; members far away (remote) sit on the outer ring.
- **Each node shows** first name, relationship, local time and a small sun or moon for awake or asleep in their time zone. Simulated members get a dashed outline and a small "sim" tag.
- **During an escalation,** a thin arc runs from the centre to the member being nudged. Skipped members get a short label ("asleep, 04:07"). Members who chose "stop" are greyed. The arc animates once, over 600 ms, when a step happens; with prefers-reduced-motion it just appears.

This is the brand's DNA: the product name made visible, and the time-zone escalation explained without words.

## Layout (desktop, 1440 wide, 12 columns, 24 px gutters)

1. **Top bar:** "CareCircle" wordmark (text only), the patient's name, the patient's local time, and a "Doctor summary" button. The demo clock badge shows only when the admin token is present.
2. **Row 1:** The Circle (5 columns) and the **Now** card (7 columns). Now shows the single most important thing in large type, for example:
   "Evening metformin · due 20:00 · overdue 67 min"
   Its ladder follows as a short vertical timeline: "21:07 nudged Meena privately", "21:12 skipped Kabir (asleep, 05:12 London)", "21:12 asked Arjun". When nothing is open: "All caught up. Next: metformin at 08:00."
3. **Row 2: Today**, a horizontal 24-hour line in the patient's time with a now-marker. Each dose is a dot: filled with the giver's initial when confirmed, hollow amber when overdue, crossed when missed, outlined grey when upcoming.
4. **Row 3: Lab values** (details below), then the **organiser** (photo thumbnail plus a 7 x 2 mini-grid of compartments, with mismatches outlined) and **Tasks** side by side.
5. **Row 4: Activity**, the audit log written as plain sentences with a small icon each ("07:58 · Meena sent a photo of the pill organiser"). Raw JSON only behind a "details" toggle.
6. **Footer:** "Built on Meta Muse Spark and Muse Voice Transcribe · WhatsApp prototype via the Twilio sandbox · Simulated members are labelled · Not medical advice."

On a phone: The Circle shrinks to a horizontal strip of member chips; Now comes first; Today scrolls sideways; everything else stacks.

## Lab values

- **One row per test:** the name, the value with its unit (tabular numbers), and a 220 px range bar.
- **The bar:** the scale runs from the smaller of the low end and the value to the larger of the high end and the value, plus 10 % padding on each side. The printed range is a soft band. The value is a dot: a solid teal dot when within range, a hollow amber dot with ▲ or ▼ when outside. One-sided ranges get a band that fades to the open side. With no range printed, there is no bar, just the text "no range printed".
- **Sort order:** out-of-range tests first. Within-range tests collapse under "5 within the lab's printed range" (click to expand).
- **Header:** "29 Oct · Sunrise Diagnostics · 4 of 9 outside the lab's printed range", with a switcher between reports.
- **Trends:** when a test appears in 2 or more reports, a 120 px sparkline sits next to its bar, with the printed band behind it.
- **Never** use the words normal, abnormal, high risk, danger, good, bad or worsening, and never red. Amber means "outside the printed range", nothing more.

## Visual tokens

| Token | Value | Use |
|---|---|---|
| canvas | #FAF7F2 | page background (warm paper) |
| surface | #FFFFFF | cards |
| ink | #1C2733 | main text |
| ink-muted | #5B6672 | secondary text |
| line | #E7E1D8 | borders, dividers |
| accent (signature) | #E8833A | CareCircle marigold: The Circle's arcs, the wordmark dot, focus states |
| action | #2563EB | buttons and links (sits well beside Meta's blue without copying it) |
| within | #1F8A70 | within range, confirmed |
| outside | #B26B00 on #FFF4E0 | outside the printed range, overdue |
| missed | #6B5B95 | missed doses (not red) |
| sim | dashed #9AA3AD | simulated members |

- **Type:** Inter (Google Fonts) 400, 500 and 600, with tabular numbers on. Sizes: 32/40 for the Now headline, 20/28 for card titles, 15/22 for body, 13/18 for labels. Sentence case everywhere, never all caps.
- **Shape:** cards with a 16 px radius, 1 px border, no heavy shadows (at most 0 1 2 rgba(0,0,0,.04)). Pills with a 999 px radius. Spacing on an 8 px grid.
- **Icons:** simple 1.5 px line icons drawn inline as SVG. No emoji on the board.
- **Accessibility:** WCAG AA contrast. Status is always shown in words and with an icon, never colour alone. Keyboard focus is visible (2 px marigold outline). Respect prefers-reduced-motion.
- **Brand:** no Meta or WhatsApp logos or wordmarks anywhere. Meta is named in plain text only, in the footer and the submission.

## Doctor summary (print first)

- **One A4 or Letter page,** black and white safe. Patient, period and who prepared it at the top.
- **Adherence:** one row per medicine, with doses confirmed / due as a thin bar and the numbers.
- **Missed doses:** a list with the reason recorded and who reported it.
- **Lab values:** the same range bars in greyscale, with the printed ranges.
- **Questions for the doctor:** the open tasks.
- **Footer:** "Prepared by CareCircle from records kept by the family. Not medical advice."

## WhatsApp wording

- **Short:** at most 3 lines, the first one carrying the point. Use first names. No jargon (never "hands_on", "slot" or "ladder").
- **Templates:**
  - Nudge: "Hi Meena, has Nanaji had his 8 PM metformin? Reply done, or tell me what happened."
  - Relay: "Meena gave Nanaji his 8 AM metformin (07:58)."
  - Missed: "Wednesday PM is still full in the organiser: that dose wasn't given."
- **No AI talk.** Never say "AI", "model" or "I think". CareCircle speaks as a helpful coordinator, and the audit log shows exactly what it did.
