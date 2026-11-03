#!/bin/sh
# Phase 4c screenshots: 1440x900 and 390x844, light and dark, plus the full page (fictional data, server on 8001 from tools/shots.sh's database).
cd "$(dirname "$0")/.." || exit 1
P=$(netstat -ano | grep "127.0.0.1:8001 .*LISTENING" | awk '{print $5}'); [ -n "$P" ] && taskkill //PID "$P" //F >/dev/null; sleep 1
.venv/Scripts/python.exe tools/make_shots_db.py | tail -1
START=${SHOTS_START:-2026-11-05T03:01:30Z}
(CC_START_TIME=$START CARECIRCLE_DB=data/shots.db BOARD_TOKEN=shotstoken CC_TICKER=0 PUBLIC_BASE_URL=https://example.invalid nohup .venv/Scripts/python.exe -m uvicorn app.server:app --host 127.0.0.1 --port 8001 > outputs/server_shots.log 2>&1 &)
sleep 7
C="/c/Program Files/Google/Chrome/Application/chrome.exe"
O="$(pwd -W)/outputs"
for T in light dark; do
  U="http://127.0.0.1:8001/board?token=shotstoken&theme=$T&live=0"
  "$C" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=6000 --window-size=1440,900 --screenshot="$O/board_p4c_1440x900_$T.png" "$U" >/dev/null 2>&1
  "$C" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=6000 --window-size=1440,${FULLH:-3300} --screenshot="$O/board_p4c_full_$T.png" "$U" >/dev/null 2>&1
  cat > "$O/_phone.html" <<EOT
<!doctype html><body style="margin:0;background:#888"><iframe src="$U" width="390" height="844" style="border:0;display:block"></iframe>
EOT
  "$C" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=8000 --window-size=500,844 --screenshot="$O/_phone_raw.png" "file:///$O/_phone.html" >/dev/null 2>&1
  .venv/Scripts/python.exe -c "
from PIL import Image
im=Image.open('outputs/_phone_raw.png'); im.crop((0,0,390,min(844,im.height))).save('outputs/board_p4c_390x844_$T.png')"
  cat > "$O/_phonefull.html" <<EOT
<!doctype html><body style="margin:0;background:#888"><iframe src="$U" width="390" height="3600" style="border:0;display:block"></iframe>
EOT
  "$C" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=8000 --window-size=500,3600 --screenshot="$O/_phonefull_raw.png" "file:///$O/_phonefull.html" >/dev/null 2>&1
  .venv/Scripts/python.exe -c "
from PIL import Image
im=Image.open('outputs/_phonefull_raw.png'); im.crop((0,0,390,im.height)).save('outputs/board_p4c_390_full_$T.png')"
done
ls outputs/*p4c*.png
