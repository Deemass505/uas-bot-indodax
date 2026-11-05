"""Logika inti BERSAMA: dipakai bot (api/tick.py) DAN backtest (Colab).
Hanya Python standar (tanpa pandas) supaya ringan di Vercel.
Parameter di bagian atas = DIBEKUKAN saat freeze date."""
import math
from datetime import datetime, timezone, timedelta

# ---------- Parameter strategi (jangan diubah setelah freeze) ----------
TF_SECONDS = 4 * 3600          # timeframe 4 jam
TF_API = "240"                 # nilai tf untuk history_v2
ENTRY_N = 20                   # masuk: close > high tertinggi 20 bar sebelumnya
EXIT_K = 10                    # keluar: close < low terendah 10 bar sebelumnya
SMA_M = 100                    # filter: close > SMA 100 (keluar juga bila di bawah SMA)
BARS_NEEDED = max(SMA_M, ENTRY_N + 1, EXIT_K + 1)
UNIVERSE = ["btcidr", "ethidr"]   # TODO: tambah 2-3 pair likuid SEBELUM freeze

INITIAL_CASH = 100_000_000
MAX_POSITIONS = 4
MAX_POS_FRAC = 0.20            # maks 20% equity per posisi
DAILY_LOSS_LIMIT = 0.03        # 3% equity, reset 00.00 WIB
MIN_ORDER_IDR = 25_000         # pakai yang lebih ketat (Pro); cek halaman resmi
MAX_SPREAD = 0.02              # spread bid-ask > 2% = data tidak valid
QTY_DECIMALS = 8               # TODO: samakan dengan presisi pair di /api/pairs


# ---------- Waktu ----------
def to_seconds(ts):
    ts = float(ts)
    return int(ts / 1000) if ts > 1e12 else int(ts)


def wib_date(ts_seconds):
    d = datetime.fromtimestamp(ts_seconds, tz=timezone.utc) + timedelta(hours=7)
    return d.strftime("%Y-%m-%d")


# ---------- Data candle ----------
def normalize_bars(raw):
    """Ubah respons history_v2 jadi list dict {t,o,h,l,c,v}, urut naik.
    CEK bentuk respons asli Indodax; fungsi ini menerima dict ber-key
    Time/Open/High/Low/Close/Volume atau list [t,o,h,l,c,v]."""
    if isinstance(raw, dict):
        raw = raw.get("data") or raw.get("candles") or []
    out = []
    for r in raw:
        if isinstance(r, dict):
            def g(*ks):
                for k in ks:
                    if k in r and r[k] is not None:
                        return r[k]
                raise ValueError("kolom candle tidak ditemukan: %s" % (ks,))
            t, o, h, l, c, v = (g("Time", "time", "t"), g("Open", "open", "o"),
                                g("High", "high", "h"), g("Low", "low", "l"),
                                g("Close", "close", "c"), g("Volume", "volume", "v"))
        else:
            t, o, h, l, c, v = r[:6]
        out.append({"t": to_seconds(t), "o": float(o), "h": float(h),
                    "l": float(l), "c": float(c), "v": float(v)})
    out.sort(key=lambda b: b["t"])
    return out


def drop_open_bars(bars, server_time_s, tf=TF_SECONDS):
    """Buang bar yang masih berjalan: Time + tf > server_time."""
    return [b for b in bars if b["t"] + tf <= server_time_s]


def parse_levels(raw, desc):
    out = []
    for lvl in raw or []:
        p, a = float(lvl[0]), float(lvl[1])
        if p > 0 and a > 0:
            out.append((p, a))
    out.sort(key=lambda x: x[0], reverse=desc)
    return out


def validate(bars, bids, asks, server_time_s, tf=TF_SECONDS):
    """Return (ok, [alasan]). Kalau tidak ok, bot tidak boleh membuka posisi."""
    reasons = []
    if len(bars) < BARS_NEEDED:
        reasons.append("bar_kurang(%d<%d)" % (len(bars), BARS_NEEDED))
    else:
        win = bars[-BARS_NEEDED:]
        # umur dihitung dari waktu TUTUP candle terakhir
        if server_time_s - (win[-1]["t"] + tf) > 2 * tf:
            reasons.append("candle_terakhir_basi")
        if any(win[i + 1]["t"] - win[i]["t"] != tf for i in range(len(win) - 1)):
            reasons.append("candle_hilang")
        if any(b["h"] <= 0 or b["l"] <= 0 or b["c"] <= 0 or b["v"] <= 0 for b in win):
            reasons.append("harga_atau_volume_nol")
    if not bids or not asks:
        reasons.append("order_book_kosong")
    else:
        spread = (asks[0][0] - bids[0][0]) / asks[0][0]
        if spread > MAX_SPREAD:
            reasons.append("spread_%.2f%%" % (spread * 100))
    return (len(reasons) == 0), reasons


# ---------- Sinyal (dipakai backtest & bot, sama persis) ----------
def compute_signal(bars, in_position):
    """bars = HANYA candle tertutup, urut naik. Return dict berisi 'signal'."""
    if len(bars) < BARS_NEEDED:
        return {"signal": "NONE", "why": "bar_kurang"}
    last = bars[-1]
    sma = sum(b["c"] for b in bars[-SMA_M:]) / SMA_M
    hh = max(b["h"] for b in bars[-1 - ENTRY_N:-1])
    ll = min(b["l"] for b in bars[-1 - EXIT_K:-1])
    sig = "HOLD"
    if not in_position:
        if last["c"] > hh and last["c"] > sma:
            sig = "BUY"
    else:
        if last["c"] < ll or last["c"] < sma:
            sig = "SELL"
    return {"signal": sig, "close": last["c"], "hh": hh, "ll": ll, "sma": sma,
            "candle_t": last["t"]}


# ---------- Eksekusi di order book (bukan mid/close) ----------
def floor_qty(q):
    f = 10 ** QTY_DECIMALS
    return math.floor(q * f + 1e-9) / f


def vwap_for_qty(levels, qty):
    need, cost = qty, 0.0
    for p, a in levels:
        take = min(a, need)
        cost += take * p
        need -= take
        if need <= 1e-12:
            break
    return cost, qty - max(need, 0.0)


def simulate_buy(asks, budget_idr, fee):
    """Beli di ask, habiskan level berikutnya bila perlu. Fee = tarif taker all-in."""
    remaining, qty = budget_idr / (1 + fee), 0.0
    for p, a in asks:
        spend = min(a * p, remaining)
        qty += spend / p
        remaining -= spend
        if remaining <= 1e-9:
            break
    qty = floor_qty(qty)
    if qty <= 0:
        return None
    cost, filled = vwap_for_qty(asks, qty)
    if filled < qty - 1e-12:
        return None
    fee_idr = cost * fee
    return {"qty": qty, "avg": cost / qty, "cost": cost,
            "fee": fee_idr, "total": cost + fee_idr}


def simulate_sell(bids, qty, fee):
    """Jual di bid. None bila kedalaman order book tidak cukup."""
    cost, filled = vwap_for_qty(bids, qty)
    if filled < qty - 1e-12:
        return None
    fee_idr = cost * fee
    return {"qty": qty, "avg": cost / qty, "gross": cost,
            "fee": fee_idr, "net": cost - fee_idr}
