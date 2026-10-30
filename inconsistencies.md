# Inconsistencies (logged, not fixed)

- Brief names media/discharge/d1.jpg..d3.jpg; the files are d1.jpeg..d3.jpeg. Runner globs by stem.
- Docs say SAM image responses carry no usage field; the response has usage.images_processed (1 per image) and input_tokens 0. Cost computed per image at $2.50/1,000.
- Docs do not specify the one_bit mask byte format (base85 variant, leading "!!!!"); decoded with meta_sam_parser (PyPI, named by the docs).
- Docs do not mention temperature for muse-spark-1.3; temperature=0 was accepted without error.
- Docs describe Standard vs Contributor as model ids; there is no separate "mode" request parameter. Only muse-spark-1.3, sam-3.1 used.
- Pricing page matches the brief on all three figures; no price difference to log.
- labels.DRAFT.json (advisor) listed paracetamol with handwriting as d3's fourth med; labels.json has ibuprofen, TDS, no handwriting. labels.json is the pre-registered truth.
- One-run-per-input deviation: SAM was called once as a smoke test on o1 and once more on o1 after my P3 parser code crashed (a code bug, before any scoring). Smoke test raw kept in outputs/raw/smoke_sam_o1.json. The scored run is the later one. Extra cost about $0.005.
- P3 prompts and P1 prompt were written once, before any results; no prompt changed after results were seen, so there is a single run per probe.
- P3 "all 14 slots mapped correctly" has no ground-truth box positions in labels.json, so correctness is judged from overlays plus an automatic grid-monotone check, not an exact match.
