"""Endpoint bot dry run: dipanggil penjadwal luar (GitHub Actions) tiap ~30 menit.
Tiap panggilan: baca state -> ambil data -> hitung sinyal -> simulasi order -> simpan state & log."""
import os, sys, json, time, uuid, hmac
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(__file__))
import _core as core

BASE = "https://indodax.com"
GAP = 0.4            # jeda antar request ke Indodax (<3 request/detik)
_last_req = [0.0]


def http_json(url, data=None, headers=None, tries=3, timeout=10, throttle=True):
    """Request dengan retry TERBATAS (maks 3x)."""
    last = None
    for i in range(tries):
        try:
            if throttle:
                wait = GAP - (time.time() - _last_req[0])
                if wait > 0:
                    time.sleep(wait)
                _last_req[0] = time.time()
            hdrs = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
            }
            hdrs.update(headers or {})
            req = urllib.request.Request(url, data=data, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode()
            if not body.strip():
                raise ValueError("respons kosong")
            return json.loads(body)
        except Exception as e:
            last = e
            time.sleep(1.0 * (i + 1))
    raise RuntimeError("gagal setelah %d percobaan: %s" % (tries, str(last)[:150]))


def redis(cmd):
    url = os.environ["UPSTASH_REDIS_REST_URL"]
    tok = os.environ["UPSTASH_REDIS_REST_TOKEN"]
    res = http_json(url, data=json.dumps(cmd).encode(), throttle=False,
                    headers={"Authorization": "Bearer " + tok,
                             "Content-Type": "application/json"})
    return res.get("result")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_state():
    return {"cash": float(core.INITIAL_CASH), "positions": {}, "last_candle": {},
            "last_bid": {}, "day": None, "day_start_equity": float(core.INITIAL_CASH),
            "loss_logged_day": None, "tick_count": 0}


def equity_of(st):
    return st["cash"] + sum(p["qty"] * st["last_bid"].get(pair, 0.0)
                            for pair, p in st["positions"].items())


def run_tick():
    token = uuid.uuid4().hex
    if redis(["SET", "bot:lock", token, "NX", "EX", "120"]) != "OK":
        return {"status": "locked"}
    logs = []

    def L(kind, **kw):
        logs.append(json.dumps({"ts": now_iso(), "type": kind, **kw}))

    try:
        return _tick(L)
    except Exception as e:
        L("error", where="tick", msg=str(e)[:200])
        raise
    finally:
        try:
            if logs:
                redis(["RPUSH", "bot:log"] + logs)
            if redis(["GET", "bot:lock"]) == token:
                redis(["DEL", "bot:lock"])
        except Exception:
            pass


def _tick(L):
    t0 = time.time()
    raw_fee = os.environ.get("FEE_TAKER")
    if not raw_fee:
        L("error", where="config", msg="FEE_TAKER belum diisi; bot tidak trading")
        return {"status": "no_fee"}
    fee = float(raw_fee)

    srv = http_json(BASE + "/api/server_time")
    now = core.to_seconds(srv["server_time"])
    st = json.loads(redis(["GET", "bot:state"]) or "null") or new_state()
    st["tick_count"] += 1
    kill = os.environ.get("KILL_SWITCH") == "1" or redis(["GET", "bot:kill"]) == "1"
    L("call", server_time=now, tick=st["tick_count"], kill_switch=kill)
    if kill:
        L("kill_switch", msg="kill switch aktif: tidak membuka posisi baru")

    # 1) Ambil data semua pair
    data = {}
    for pair in core.UNIVERSE:
        try:
            frm = now - (core.BARS_NEEDED + 6) * core.TF_SECONDS
            raw = http_json("%s/tradingview/history_v2?symbol=%s&tf=%s&from=%d&to=%d"
                            % (BASE, pair.upper(), core.TF_API, frm, now))
            bars = core.drop_open_bars(core.normalize_bars(raw), now)
            book = http_json("%s/api/depth/%s" % (BASE, pair))
            bids = core.parse_levels(book.get("buy"), desc=True)
            asks = core.parse_levels(book.get("sell"), desc=False)
            ok, why = core.validate(bars, bids, asks, now)
            data[pair] = {"bars": bars, "bids": bids, "asks": asks, "ok": ok, "why": why}
            if bids:
                st["last_bid"][pair] = bids[0][0]
            if bids and asks:
                ref = core.simulate_buy(asks, core.INITIAL_CASH * core.MAX_POS_FRAC, 0.0)
                L("snapshot", pair=pair, best_bid=bids[0][0], best_ask=asks[0][0],
                  spread_pct=(asks[0][0] - bids[0][0]) / asks[0][0] * 100,
                  buy_slip_pct_ref20jt=(ref["avg"] / asks[0][0] - 1) * 100 if ref else None,
                  bids=bids[:10], asks=asks[:10])
        except Exception as e:
            L("error", where="fetch", pair=pair, msg=str(e)[:200])

    # 2) Equity (posisi dinilai di best bid) + pergantian hari WIB
    equity = equity_of(st)
    today = core.wib_date(now)
    if st["day"] != today:
        st["day"], st["day_start_equity"] = today, equity
        L("equity_daily", date=today, equity=equity)
    loss_hit = equity < st["day_start_equity"] * (1 - core.DAILY_LOSS_LIMIT)
    if loss_hit and st["loss_logged_day"] != today:
        st["loss_logged_day"] = today
        L("daily_loss_limit", equity=equity, start=st["day_start_equity"])

    # 3) Sinyal & eksekusi (tiap candle hanya sekali)
    done = []
    for pair, d in data.items():
        if not d["bars"]:
            continue
        t = d["bars"][-1]["t"]
        if st["last_candle"].get(pair) == t:
            continue                                  # idempotency
        if not d["ok"]:
            L("invalid_data", pair=pair, reasons=d["why"])   # dicoba lagi di tick berikut
            continue
        pos = st["positions"].get(pair)
        sig = core.compute_signal(d["bars"], pos is not None)
        L("signal", pair=pair, **sig)
        rejected = False
        if sig["signal"] == "SELL":
            f = core.simulate_sell(d["bids"], pos["qty"], fee)
            if f is None:
                L("order_rejected", pair=pair, side="sell", reason="depth_kurang")
                rejected = True
            else:
                st["cash"] += f["net"]
                del st["positions"][pair]
                L("order", pair=pair, side="sell", qty=f["qty"], best_bid=d["bids"][0][0],
                  best_ask=d["asks"][0][0], avg_fill=f["avg"], fee=f["fee"],
                  vs_signal=f["avg"] / sig["close"] - 1, pnl=f["net"] - pos["cost_basis"])
        elif sig["signal"] == "BUY":
            size = min(core.MAX_POS_FRAC * equity, st["cash"])
            block = None
            if kill:
                block = "kill_switch"
            elif loss_hit:
                block = "daily_loss_limit"
            elif len(st["positions"]) >= core.MAX_POSITIONS:
                block = "maks_posisi"
            elif size < core.MIN_ORDER_IDR:
                block = "di_bawah_minimum_order"
            if block:
                L("buy_blocked", pair=pair, reason=block)
            else:
                f = core.simulate_buy(d["asks"], size, fee)
                if f is None or f["cost"] < core.MIN_ORDER_IDR:
                    L("order_rejected", pair=pair, side="buy", reason="qty_nol_atau_min_order")
                else:
                    st["cash"] -= f["total"]
                    st["positions"][pair] = {"qty": f["qty"], "avg": f["avg"],
                                             "entry_t": now, "cost_basis": f["total"]}
                    L("order", pair=pair, side="buy", qty=f["qty"], best_bid=d["bids"][0][0],
                      best_ask=d["asks"][0][0], avg_fill=f["avg"], fee=f["fee"],
                      vs_signal=f["avg"] / sig["close"] - 1)
        if not rejected:
            st["last_candle"][pair] = t
            done.append(pair)

    equity = equity_of(st)
    redis(["SET", "bot:state", json.dumps(st)])
    L("done", processed=done, equity=equity, cash=st["cash"],
      open_positions=list(st["positions"]), ms=int((time.time() - t0) * 1000))
    return {"status": "ok", "processed": done, "equity": equity}


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def _run(self):
        secret = os.environ.get("CRON_SECRET", "")
        auth = self.headers.get("Authorization", "")
        if not secret or not hmac.compare_digest(auth, "Bearer " + secret):
            return self._send(401, {"error": "unauthorized"})
        try:
            self._send(200, run_tick())
        except Exception as e:
            self._send(500, {"error": str(e)[:200]})

    def do_GET(self):
        self._run()

    def do_POST(self):
        self._run()
