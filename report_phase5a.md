# Phase 5a dry run report

Nothing was pushed and nothing was created on GitHub. The public copy exists only on this machine. Scan output below is counts and paths only; no value, key, token, number or email address is printed anywhere.

## Advisor answers applied
1. Monday scene: all five members stay on "everything" for filming; the printed steps now say the real defaults differ (remote members start on alerts and a daily summary).
2. Ladder order unchanged. The Thursday steps are re-printed from the updated docs/VIDEO_SCRIPT.md (Meena, then Sunita, then Arjun; Kabir and Sofía shown skipped while asleep). A test checks the steps against the script.
3. Outbound cap is 80 for filming, counted from a fresh counter file (data/outbound_filming.json, starts at 0). The app now waits so that real sends are at least 3 seconds apart, never a burst (tested with a fake clock).
4. The live Today-card send to r1 still waits for "ready".
5. No visual polish was done in this block; the time went to Block L. Nothing on the board changed.

## Block L
- README.md written to match the code (pitch, real versus simulated, how it works, the Meta models, what was tested and dropped with numbers, safety design, setup, limits).
- docs/ARCHITECTURE.md with the Mermaid diagram; docs/EVALS.md with every probe table and its caveat (Phase 0 to 4, the pre-registration hashes, P7, P3-real, P8 pre-registered and corrected, P9 with its 24 rows, spend); LICENSE (MIT, "CareCircle contributors"); requirements.txt (there was none).
- Found while building the public copy: one unit test made a real model call on every run (a stray line in a draft-summary test), and it passed only because the key was in .env. Removed it, and tests/conftest.py now makes any unit test that reaches the model API fail. 204 tests pass with live calls blocked.

## History scan (36 commits when scanned; 39 now; counts and paths only)
| Check | Result |
|---|---|
| gitleaks 8.30.1 over all commits (patches) | **0 findings** |
| Exact values of every variable in .env, the first 12 characters of key-like values, the recipient numbers (as written and digits-only), in file contents and in commit messages | **0 paths, 0 commits** |
| Twilio account, API and message SIDs; sk-, AWS, GitHub token shapes; Bearer literals | **0 / 0 / 0 / 0 / 0 / 0** |
| 40+ character hex strings | 2 paths: report.md, report_phase1.md. These are the pre-registration sha256 and commit hashes; benign |
| E.164 numbers; whatsapp: addresses with digits | **0; 0** |
| trycloudflare.com hostnames; ngrok or localtunnel hostnames | **0; 0** |
| Tracked-in-history paths that are .env, .mcp.json, databases, images, audio, video, pdf, docx, or under outputs/, data/, media/, photos/, prescriptions/, videos/, raw/ | **0** in every class |
| Largest blobs in history (> 500 KB) | none |
| Word "private" in paths | 2: tools/doc_extract.py, tools/doc_score.py |
| "private" followed by a folder separator in contents | 1 path: report_phase3.md (two table rows naming two files in a folder outside the repo, with 16-hex-character hashes of those files) |
| The word "private" in contents, any use | 12 paths (README, ARCHITECTURE, EVALS, VIDEO_SCRIPT, escalation.py, server.py, report_phase2/3/4, the two private tools, scene_steps.py): almost all are "private message" or "private nudge" |
| Commit author emails | 1 distinct, a free-mail provider address, on all 36 then-existing commits; 1 distinct committer email, same kind |
| Commit trailer emails | 1 distinct (a noreply address), 34 trailers |
| Author name or email appearing in file contents | 0 paths |
| Absolute local Windows paths in contents | 2 paths: report_phase3.md (the two rows above) and CLAUDE.md |
| Working tree, not history (gitleaks dir mode) | 74 hits, all in files that are not tracked: .env (4), .venv packages (test fixtures and Twilio credential classes), outputs/board_server.log (9), outputs/shots_server.log (5), outputs/p9_results.json (1). The two server logs contain request lines with token query strings. They are git-ignored and are not in the public copy |

## Public copy
[a local folder]: `git clone --no-local`, 39 commits, 108 tracked files (root 21, app 29, docs 4, probes 15, site 2, tests 26, tools 11), no remote (the origin was removed after the last refresh). It is NOT filtered: this is the dry run. The test suite run inside it passed except one test that needed the model key (fixed in the main repo, see above; the copy was refreshed afterwards).

## What the filter-repo rules would remove or change (run on a throwaway clone, result counted)
Rules: tools/filter_repo_rules.txt (patterns only), plus three command options.
1. **Remove path:** hindi_comments.txt (a personal review note; contents are Hindi feedback, no secret).
2. **Rename** tools/doc_extract.py and tools/doc_score.py to tools/doc_extract.py and tools/doc_score.py in all 39 commits (the word "private" disappears from every path; the file contents are generic and print counts only). A plain removal would break one test (test_doc_extract_refuses_output_inside_repo), so rename is the recommended option; the replace-text rules also rename the references and that test.
3. **Replace text:** absolute paths to the folder outside the repository (2 rows in report_phase3.md at HEAD; CLAUDE.md has one in earlier commits only) become "[a folder outside the repository]" or "[local user folder]"; the file names inside those rows stay as words.
4. **Mailmap:** the one author and one committer email become "CareCircle contributors <noreply@example.invalid>" in every commit.
Result on the scratch clone: 39 commits before and after, 109 to 108 files at HEAD, paths with rewritten text at HEAD: 3 (report_phase3.md, tests/test_phase2.py, and the rules file itself, which contains its own patterns, so it should be excluded from the public tree or kept out of the rewrite). After the rewrite: 0 paths containing "private", 1 distinct author email and 1 committer email, both noreply; "private" in contents goes from 12 to 14 paths only because the renamed tools, the rules file and the scan tool mention it as an ordinary word.
Not removed (your call): the Co-Authored-By trailers (noreply address, harmless); the word "advisor" (18 files); CLAUDE.md and FRICTION_LOG.md, which are working notes and show the build process.
Also still to do before any publication, not done here: re-run gitleaks and tools/history_scan.py on the filtered result (the scan above on the scratch clone already shows 0 for every secret class), decide on the repository name and description, and decide whether to ship site/replay.html with GitHub Pages.

## Things I could not clean up myself (a delete was blocked; please remove them)
- [a local folder]: a scratch clone from an earlier mistaken dry run (filtered with the wrong options; thrown away).
- [a local folder]: the scratch clone used for the numbers above.
- In your temp folder (C:\Users\<you>\AppData\Local\Temp): one or more *.mailmap files from that mistaken run; they contain the author's email address. Delete any *.mailmap there.
- outputs/board_server.log and outputs/shots_server.log hold token query strings in request lines; they are untracked, but delete them before sharing the folder.

## Commits and spend
Commits: a2d996b (cap, spacing, scene steps), e2ac085 (README, ARCHITECTURE, EVALS, LICENSE, requirements), the scan tool, the test-hygiene fix, the rules file, and this report. No model calls; logged spend is still $6.29 of $8.00.
