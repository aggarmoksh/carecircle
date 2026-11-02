#!/bin/sh
# Rebuild data/shots.db and capture the Phase 4 screenshots with headless Chrome (server on port 8001, fictional data only).
cd "$(dirname "$0")/.." || exit 1
P=$(netstat -ano | grep "127.0.0.1:8001 .*LISTENING" | awk '{print $5}'); [ -n "$P" ] && taskkill //PID "$P" //F >/dev/null; sleep 1
.venv/Scripts/python.exe tools/make_shots_db.py | tail -1
START=${SHOTS_START:-2026-11-05T03:01:30Z}
(CC_START_TIME=$START CARECIRCLE_DB=data/shots.db BOARD_TOKEN=shotstoken CC_TICKER=0 nohup .venv/Scripts/python.exe -m uvicorn app.server:app --host 127.0.0.1 --port 8001 > outputs/server_shots.log 2>&1 &)
sleep 7
C="/c/Program Files/Google/Chrome/Application/chrome.exe"
U="http://127.0.0.1:8001/board?token=shotstoken"
O="$(pwd -W)/outputs"
"$C" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=6000 --window-size=1440,900 --screenshot="$O/board_p4_1440x900.png" "$U" >/dev/null 2>&1
"$C" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=6000 --window-size=1440,${FULLH:-2900} --screenshot="$O/board_p4_full.png" "$U" >/dev/null 2>&1
"$C" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=6000 --window-size=390,844 --screenshot="$O/board_p4_390x844.png" "$U" >/dev/null 2>&1
"$C" --headless=new --disable-gpu --virtual-time-budget=6000 --print-to-pdf="$O/summary_p4.pdf" --no-pdf-header-footer "http://127.0.0.1:8001/doctor?token=shotstoken&from=2026-11-02&to=2026-11-05" >/dev/null 2>&1
ls -la outputs/*p4*.png outputs/summary_p4.pdf
# phone layout: a 390 px wide iframe (headless Chrome will not make a window narrower than about 500 px), cropped to 390 x 844
cat > "$O/_phone.html" <<EOF
<!doctype html><body style="margin:0;background:#fff"><iframe src="$U" width="390" height="844" style="border:0;display:block"></iframe>
EOF
"$C" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=8000 --window-size=500,844 --screenshot="$O/_phone_raw.png" "file:///$O/_phone.html" >/dev/null 2>&1
.venv/Scripts/python.exe -c "
from PIL import Image
im=Image.open('outputs/_phone_raw.png'); im.crop((0,0,390,min(844,im.height))).save('outputs/board_p4_390x844.png')"
