"""Personal read-only board links. Each member has a token derived from the server secret and a generation number; only its SHA-256 is stored, so a
stolen database does not give the links, and revoking a member bumps the generation (the old link stops working, a new one can be issued).
A member token opens the board, its data and the doctor summary; it never opens /admin."""
import base64, hashlib, hmac, os, secrets
from .clock import clock

BASE_DEFAULT = "http://localhost:8000"


def _secret(conn):
    """The server secret plus a random salt kept in this database, so tokens differ from one database to the next."""
    r = conn.execute("SELECT value FROM meta WHERE key='link_salt'").fetchone()
    if r is None:
        conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('link_salt',?)", (secrets.token_hex(16),))
        conn.commit()
        r = conn.execute("SELECT value FROM meta WHERE key='link_salt'").fetchone()
    return ((os.environ.get("BOARD_TOKEN") or "dev-only-secret") + r["value"]).encode()


def _token(conn, member_id, gen):
    return base64.urlsafe_b64encode(hmac.new(_secret(conn), f"{member_id}:{gen}".encode(), hashlib.sha256).digest())[:24].decode()


def _hash(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


def _active(conn, member_id):
    return conn.execute("SELECT * FROM board_tokens WHERE member_id=? AND revoked_at IS NULL ORDER BY gen DESC LIMIT 1", (member_id,)).fetchone()


def token_for(conn, member_id):
    """The member's current link token (issued on first use)."""
    r = _active(conn, member_id)
    if r is None:
        last = conn.execute("SELECT MAX(gen) g FROM board_tokens WHERE member_id=?", (member_id,)).fetchone()["g"] or 0
        tok = _token(conn, member_id, last + 1)
        conn.execute("INSERT INTO board_tokens(token_hash,member_id,gen,created_at) VALUES(?,?,?,?)", (_hash(tok), member_id, last + 1, clock.iso()))
        conn.commit()
        return tok
    return _token(conn, member_id, r["gen"])


def verify(conn, tok):
    """-> member id for a valid, unrevoked member token, else None."""
    if not tok:
        return None
    r = conn.execute("SELECT member_id FROM board_tokens WHERE token_hash=? AND revoked_at IS NULL", (_hash(tok),)).fetchone()
    return r["member_id"] if r else None


def revoke(conn, member_id):
    n = conn.execute("UPDATE board_tokens SET revoked_at=? WHERE member_id=? AND revoked_at IS NULL", (clock.iso(), member_id)).rowcount
    conn.commit()
    return n


def link(conn, member_id):
    base = (os.environ.get("PUBLIC_BASE_URL") or BASE_DEFAULT).rstrip("/")
    return f"{base}/board?token={token_for(conn, member_id)}"
