"""One live send of the Today card to r1 (Arjun's iPhone), with the "Board (optional)" link. Counts toward the outbound cap (40).
Run it only when the user has said "ready". The server must be running and reachable at PUBLIC_BASE_URL with the same database (Twilio fetches the card from it).
Usage: python tools/send_card_live.py --yes        (without --yes it only says what it would do)
Prints nothing secret: no token, no number, no card address."""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
from app import channel, config, db, record
from app.outbox import Outbox

if "--yes" not in sys.argv:
    print(f"Would send the Today card to r1 (member m1) now; {channel.outbound_count()} of {config.PHASE1_MESSAGE_CAP} outbound messages used. Add --yes to send.")
    sys.exit(0)
conn = db.connect()
sent = Outbox(conn, channel.Router()).send_card("m1", "today_caption", "live send of the Today card to r1", patient=config.PATIENT_NAME)
print("sent to r1:" if sent else "not sent (window closed or member chose STOP):", (sent or "").split("Board")[0].strip())
print(f"{channel.outbound_count()} of {config.PHASE1_MESSAGE_CAP} outbound messages used.")
