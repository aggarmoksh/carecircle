# Friction log

Entry format: `YYYY-MM-DD HH:MM [area] tried | expected | actual | impact | workaround`

2026-10-29 18:30 [whatsapp-test-number] tried to obtain/claim Meta test number sender | test number usable for up to 5 verified recipients, no business verification | error code 2655121 "Account restricted", is_transient false | blocks P4, P5 and WhatsApp-sourced P2 audio; channel choice pending with user | none yet; probe order changed to P1, P3 first
2026-10-30 [sam-3.1] decode one_bit mask from docs | byte-level format documented | not documented (base85 variant, header); no image usage field either | had to install meta_sam_parser from PyPI | used its decode_mask_to_raster
2026-10-30 [sam-3.1] P3-synthetic o4 (angled, dim) with prompt "pill organizer compartment" | 14 masks | 1 mask covering most of the photo | pipeline fails on o4 | Spark alone read o4 14/14
2026-10-31 [twilio-sandbox] free-form text to r1 via Messages API from the configured sender, inside 24h window | delivered | HTTP 400 "ContentSid Required" (twice) | blocks P4(b), P5, P6 outbound | stopped per rule; user to check the sender and sandbox mode
2026-10-31 [twilio-content-api] list templates (P4c) | list of approved sandbox templates | 401 code 20003, not available on Trial | P4(c) cannot be answered via API | report from Twilio docs instead
