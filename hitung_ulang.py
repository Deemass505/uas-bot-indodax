#!/usr/bin/env python3
"""hitung_ulang.py: menghasilkan ulang SEMUA angka dashboard forward test dari log mentah.

Pemakaian:
  python hitung_ulang.py bot_log.jsonl --start 2026-11-05T12:00:00+07:00 --end 2026-11-14T12:00:00+07:00
Keluaran: hasil_forward.json, fw_trades.csv, fw_orders.csv, fw_signals.csv, fw_equity_daily.csv (+ ringkasan di layar).
Tidak ada angka yang ditulis manual: semuanya dihitung dari entri log (call, done, order, snapshot, signal, error, ...).
"""
import argparse, csv, json, statistics
from datetime import datetime, timezone, timedelta


def parse_ts(s):
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--slot-minutes", type=int, default=30)
    ap.add_argument("--initial", type=float, default=100_000_000.0)
    ap.add_argument("--out", default="hasil_forward.json")
    a = ap.parse_args()

    start, end = parse_ts(a.start), parse_ts(a.end)
    ev = []
    for line in open(a.log):
        line = line.strip()
        if line:
            e = json.loads(line)
            e["_ts"] = parse_ts(e["ts"])
            ev.append(e)
    ev.sort(key=lambda e: e["_ts"])
    last_ts = ev[-1]["_ts"] if ev else start
    eff_end = min(end, last_ts)
    w = [e for e in ev if start <= e["_ts"] <= eff_end]
    by = lambda t: [e for e in w if e["type"] == t]

    res = {"jendela_mulai": a.start, "jendela_akhir_diminta": a.end, "jendela_akhir_dipakai": eff_end.isoformat(),
           "jendela_hari": round((eff_end - start).total_seconds() / 86400, 3), "entri_log_dalam_jendela": len(w)}

    # ---- Operasional: uptime, error, kill switch ----
    calls, dones = by("call"), by("done")
    slot = timedelta(minutes=a.slot_minutes)
    n_slots = int((eff_end - start) / slot)
    covered = {int((d["_ts"] - start) / slot) for d in dones if int((d["_ts"] - start) / slot) < n_slots}
    errs = by("error")
    err_group = {}
    for e in errs:
        k = e.get("where", "?")
        g = err_group.setdefault(k, {"jumlah": 0, "contoh": []})
        g["jumlah"] += 1
        if len(g["contoh"]) < 3:
            g["contoh"].append({"ts": e["ts"], "pair": e.get("pair"), "msg": e.get("msg")})
    inv = {}
    for e in by("invalid_data"):
        for r in e.get("reasons", []):
            inv[r] = inv.get(r, 0) + 1
    res["operasional"] = {
        "slot_menit": a.slot_minutes, "slot_terjadwal": n_slots, "slot_terlaksana": len(covered),
        "uptime_pct": round(100 * len(covered) / n_slots, 2) if n_slots else None,
        "panggilan_tercatat": len(calls), "panggilan_selesai": len(dones),
        "panggilan_tidak_selesai": len(calls) - len(dones),
        "error_api_total": len(errs), "error_per_jenis": err_group,
        "pemakaian_kill_switch": len(by("kill_switch")), "daily_loss_limit_tercapai": len(by("daily_loss_limit")),
        "data_tidak_valid": sum(inv.values()), "alasan_data_tidak_valid": inv,
        "catatan": "Slot terlaksana = slot 30 menit yang berisi minimal satu panggilan selesai (type=done). "
                   "Panggilan yang ditahan lock tidak tercatat di log.",
    }

    # ---- Order & trade ----
    orders = sorted(by("order"), key=lambda e: e["_ts"])
    open_pos, trades, order_rows = {}, [], []
    for o in orders:
        mid = (o["best_bid"] + o["best_ask"]) / 2
        spread_cost = (o["avg_fill"] - mid) * o["qty"] if o["side"] == "buy" else (mid - o["avg_fill"]) * o["qty"]
        order_rows.append({"ts": o["ts"], "pair": o["pair"], "side": o["side"], "qty": o["qty"], "best_bid": o["best_bid"],
                           "best_ask": o["best_ask"], "avg_fill": o["avg_fill"], "fee": o["fee"],
                           "vs_signal_pct": o["vs_signal"] * 100, "biaya_spread": spread_cost, "pnl": o.get("pnl")})
        if o["side"] == "buy":
            open_pos[o["pair"]] = (o, spread_cost)
        elif o["pair"] in open_pos:
            b, b_sp = open_pos.pop(o["pair"])
            fee_t = b["fee"] + o["fee"]; sp_t = b_sp + spread_cost
            trades.append({"pair": o["pair"], "masuk": b["ts"], "keluar": o["ts"], "qty": o["qty"],
                           "harga_masuk": b["avg_fill"], "harga_keluar": o["avg_fill"], "pnl": o["pnl"],
                           "fee": fee_t, "biaya_spread": sp_t, "laba_kotor": o["pnl"] + fee_t + sp_t})
    pnl = [t["pnl"] for t in trades]
    wins = [x for x in pnl if x > 0]; losses = [x for x in pnl if x <= 0]
    gross = sum(t["laba_kotor"] for t in trades)
    costs = sum(t["fee"] + t["biaya_spread"] for t in trades)
    vs = [r["vs_signal_pct"] for r in order_rows]
    res["perdagangan"] = {
        "jumlah_order": len(orders), "jumlah_trade_tertutup": len(trades),
        "posisi_terbuka_akhir": dones[-1].get("open_positions") if dones else None,
        "win_rate_pct": round(100 * len(wins) / len(pnl), 2) if pnl else None,
        "rata2_untung": statistics.mean(wins) if wins else None, "rata2_rugi": statistics.mean(losses) if losses else None,
        "profit_factor": (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else None,
        "total_fee": sum(t["fee"] for t in trades), "total_biaya_spread": sum(t["biaya_spread"] for t in trades),
        "laba_kotor_sebelum_biaya": gross, "porsi_biaya": (costs / gross) if gross > 0 else None,
        "selisih_fill_vs_sinyal_pct_rata2": statistics.mean(vs) if vs else None,
        "catatan": "porsi_biaya = (fee + spread + slippage) / laba kotor; None bila laba kotor <= 0 atau belum ada trade.",
    }

    # ---- Equity, return, drawdown ----
    series = [(d["_ts"], d["equity"]) for d in dones]
    peak, mdd = a.initial, 0.0
    for _, v in series:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    last_eq = series[-1][1] if series else a.initial
    res["kinerja"] = {"equity_awal": a.initial, "equity_akhir": last_eq,
                      "return_total_pct": (last_eq / a.initial - 1) * 100, "max_drawdown_pct": mdd * 100,
                      "catatan": "Equity dari entri done (posisi dinilai di best bid). Drawdown dihitung pada titik panggilan."}
    daily = [{"tanggal_wib": e["date"], "equity": e["equity"]} for e in by("equity_daily")]

    # ---- Benchmark buy & hold BTC/IDR dari snapshot order book ----
    snaps = [e for e in by("snapshot") if e.get("pair") == "btcidr"]
    if len(snaps) >= 2:
        res["benchmark_btc_buy_hold"] = {"harga_beli_ask": snaps[0]["best_ask"], "harga_nilai_bid": snaps[-1]["best_bid"],
                                         "return_pct": (snaps[-1]["best_bid"] / snaps[0]["best_ask"] - 1) * 100,
                                         "dari": snaps[0]["ts"], "sampai": snaps[-1]["ts"]}
    # ---- Spread terukur dari snapshot ----
    sp = {}
    for e in by("snapshot"):
        sp.setdefault(e["pair"], []).append(e["spread_pct"])
    res["spread_snapshot"] = {p: {"n": len(v), "median_pct": statistics.median(v), "maks_pct": max(v)} for p, v in sp.items()}

    # ---- Sinyal per candle (untuk dicocokkan dengan backtest) ----
    seen, sig_rows = set(), []
    for e in by("signal"):
        k = (e["pair"], e.get("candle_t"))
        if k in seen:
            continue
        seen.add(k)
        sig_rows.append({"pair": e["pair"], "candle_t_unix": e.get("candle_t"), "sinyal": e["signal"], "close": e.get("close"),
                         "sma": e.get("sma"), "hh": e.get("hh"), "ll": e.get("ll")})
    res["sinyal_unik"] = len(sig_rows)

    def dump(name, rows):
        with open(name, "w", newline="") as f:
            if rows:
                wr = csv.DictWriter(f, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows)
    dump("fw_trades.csv", trades); dump("fw_orders.csv", order_rows)
    dump("fw_signals.csv", sig_rows); dump("fw_equity_daily.csv", daily)
    json.dump(res, open(a.out, "w"), indent=1, default=str)

    print("== Ringkasan forward test (dihitung ulang dari log) ==")
    print("Jendela: %s -> %s (%.2f hari)" % (a.start, eff_end.isoformat(), res["jendela_hari"]))
    o = res["operasional"]; print("Uptime: %s%% (%d dari %d slot %d menit)" % (o["uptime_pct"], o["slot_terlaksana"], o["slot_terjadwal"], a.slot_minutes))
    print("Error:", o["error_api_total"], "| kill switch:", o["pemakaian_kill_switch"], "| data tidak valid:", o["data_tidak_valid"])
    k = res["kinerja"]; print("Return: %.4f%% | Max DD: %.4f%% | Equity akhir: %.2f" % (k["return_total_pct"], k["max_drawdown_pct"], k["equity_akhir"]))
    p = res["perdagangan"]; print("Order:", p["jumlah_order"], "| trade tertutup:", p["jumlah_trade_tertutup"], "| posisi terbuka:", p["posisi_terbuka_akhir"])
    print("Disimpan:", a.out, "fw_trades.csv fw_orders.csv fw_signals.csv fw_equity_daily.csv")


if __name__ == "__main__":
    main()
