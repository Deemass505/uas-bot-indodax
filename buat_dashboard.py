#!/usr/bin/env python3
"""buat_dashboard.py: membuat dashboard.html mandiri (tanpa internet) dari berkas hasil, tanpa angka manual.
Masukan: bt_result.json, bt_equity.csv (backtest), hasil_forward.json, fw_equity_daily.csv (dari hitung_ulang.py),
opsional bt_window_result.json (backtest pada jendela forward test yang sama)."""
import csv, json, os
from datetime import datetime, timezone

def jl(f): return json.load(open(f)) if os.path.exists(f) else None
bt, fw, win, pc = jl("bt_result.json"), jl("hasil_forward.json"), jl("bt_window_result.json"), jl("pencocokan_sinyal.json")
eq = [(int(float(t)), float(v)) for t, v in list(csv.reader(open("bt_equity.csv")))[1:]] if os.path.exists("bt_equity.csv") else []
step = max(1, len(eq) // 400)
fwd = [(r["tanggal_wib"], float(r["equity"])) for r in csv.DictReader(open("fw_equity_daily.csv"))] if os.path.exists("fw_equity_daily.csv") else []
data = {"bt": bt, "fw": fw, "win": win, "pc": pc, "eq": eq[::step], "fwd": fwd,
        "dibuat": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sumber": [f for f in ["bt_result.json", "bt_equity.csv", "hasil_forward.json", "fw_equity_daily.csv", "bt_window_result.json", "pencocokan_sinyal.json"] if os.path.exists(f)]}
HTML = """<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard Bot Dry Run Indodax</title><style>
:root{--bg:#070b16;--c1:#00e5ff;--c2:#8b5cf6;--fg:#e8f1ff;--mu:#7d8db0;--bd:rgba(120,160,255,.18);--bad:#ff5d7a;--ok:#35f0a0}
*{box-sizing:border-box}body{margin:0;padding:18px 14px 40px;color:var(--fg);font:14px/1.5 "Segoe UI",system-ui,sans-serif;min-height:100vh;
background:radial-gradient(900px 500px at 85% -10%,rgba(139,92,246,.28),transparent),radial-gradient(800px 500px at -10% 10%,rgba(0,229,255,.18),transparent),
linear-gradient(rgba(120,160,255,.05) 1px,transparent 1px) 0 0/36px 36px,linear-gradient(90deg,rgba(120,160,255,.05) 1px,transparent 1px) 0 0/36px 36px,var(--bg)}
.w{max-width:980px;margin:auto}header{margin-bottom:18px}.tag{letter-spacing:.35em;font-size:11px;color:var(--c1);text-transform:uppercase}
h1{margin:4px 0 4px;font-size:26px;font-weight:600;background:linear-gradient(90deg,#fff,var(--c1) 60%,var(--c2));-webkit-background-clip:text;background-clip:text;color:transparent}
.n{color:var(--mu);font-size:12px}h2{margin:0 0 10px;font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--c1);font-weight:600}
.g{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;margin-bottom:14px}
.k{padding:14px;border:1px solid var(--bd);border-radius:14px;background:linear-gradient(160deg,rgba(255,255,255,.07),rgba(255,255,255,.02));backdrop-filter:blur(8px);box-shadow:0 0 24px rgba(0,229,255,.06)}
.k b{display:block;margin-top:4px;font:600 23px "Consolas","SFMono-Regular",monospace;color:#fff;text-shadow:0 0 14px rgba(0,229,255,.55)}.k span{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--mu)}
.c{padding:16px;margin-bottom:14px;border:1px solid var(--bd);border-radius:16px;background:rgba(10,16,34,.72);backdrop-filter:blur(10px);box-shadow:0 8px 40px rgba(0,0,0,.35)}
.t{overflow-x:auto}table{width:100%;border-collapse:collapse}th{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--mu);font-weight:500}
td,th{padding:8px 6px;border-bottom:1px solid var(--bd);text-align:right}td:first-child,th:first-child{text-align:left}td{font-family:Consolas,monospace}td:first-child{font-family:inherit;color:#cfe0ff}
tr:last-child td{border-bottom:0}svg{width:100%;height:170px;display:block}.bad{color:var(--bad)}.ok{color:var(--ok)}
</style><div class="w"><header><div class="tag">Algorithmic Trading &middot; UAS</div><h1>Bot Dry Run Indodax</h1><p class="n" id="meta"></p></header>
<div class="g" id="kp"></div>
<div class="c"><h2>Backtest vs Forward</h2><div class="t"><table id="t"></table></div><p class="n">CAGR forward tidak ditampilkan (periode pendek tidak bermakna). &ldquo;&mdash;&rdquo; = belum ada data di berkas sumber.</p></div>
<div class="c"><h2>Equity backtest</h2><svg id="c1" viewBox="0 0 600 170" preserveAspectRatio="none"></svg></div>
<div class="c"><h2>Equity harian forward (00.00 WIB)</h2><svg id="c2" viewBox="0 0 600 170" preserveAspectRatio="none"></svg></div>
<div class="c"><h2>Panel operasional</h2><div class="t"><table id="o"></table></div><p class="n" id="oc"></p></div>
<div class="c"><h2>Gap pada jendela yang sama</h2><div class="t"><table id="g"></table></div></div>
<p class="n" id="src"></p></div>
<script id="d" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById("d").textContent),bt=D.bt||{},fw=D.fw||{},k=fw.kinerja||{},p=fw.perdagangan||{},o=fw.operasional||{},w=D.win,pc=D.pc;
const f=(v,d=2,s="")=>v==null?"\u2014":Number(v).toLocaleString("id-ID",{maximumFractionDigits:d})+s;
const row=(a,...c)=>"<tr><td>"+a+"</td>"+c.map(x=>"<td>"+x+"</td>").join("")+"</tr>";
document.getElementById("meta").textContent="Jendela forward: "+(fw.jendela_mulai||"\u2014")+" s.d. "+(fw.jendela_akhir_dipakai||"\u2014")+" ("+f(fw.jendela_hari)+" hari) \u00b7 dibuat "+D.dibuat+" UTC";
document.getElementById("kp").innerHTML=[["Return backtest",f(bt.return_total_pct,2,"%")],["CAGR backtest",f(bt.cagr_pct,2,"%")],["Max DD backtest",f(bt.max_drawdown_pct,2,"%")],
["Return forward",f(k.return_total_pct,2,"%")],["Uptime forward",f(o.uptime_pct,2,"%")],["Kecocokan sinyal",pc?f(pc.persen,1,"%"):"\u2014"]].map(x=>'<div class="k"><span>'+x[0]+"</span><b>"+x[1]+"</b></div>").join("");
document.getElementById("t").innerHTML="<tr><th>Metrik</th><th>Backtest</th><th>Forward</th></tr>"+[
["Return total",f(bt.return_total_pct,2,"%"),f(k.return_total_pct,2,"%")],["CAGR",f(bt.cagr_pct,2,"%"),"n/a"],
["Max drawdown",f(bt.max_drawdown_pct,2,"%"),f(k.max_drawdown_pct,2,"%")],["Jumlah trade",f(bt.jumlah_trade,0),f(p.jumlah_trade_tertutup,0)],
["Profit factor",f(bt.profit_factor),f(p.profit_factor)],["Win rate",f(bt.win_rate_pct,1,"%"),f(p.win_rate_pct,1,"%")],
["Rata-rata untung (Rp)",f(bt.rata2_untung,0),f(p.rata2_untung,0)],["Rata-rata rugi (Rp)",f(bt.rata2_rugi,0),f(p.rata2_rugi,0)],
["Porsi biaya (fee+spread+slippage)/laba kotor",f(bt.porsi_biaya==null?null:bt.porsi_biaya*100,1,"%"),f(p.porsi_biaya==null?null:p.porsi_biaya*100,1,"%")],
["Benchmark buy&hold BTC/IDR",f(bt.buy_hold_btc_pct,2,"%"),f((fw.benchmark_btc_buy_hold||{}).return_pct,2,"%")]].map(r=>row(...r)).join("");
function line(id,pts){const s=document.getElementById(id);if(pts.length<2){s.outerHTML='<p class="n">Data belum cukup.</p>';return}
const ys=pts.map(q=>q[1]),mn=Math.min(...ys),mx=Math.max(...ys),sp=(mx-mn)||1,X=i=>(i*600/(pts.length-1)).toFixed(1),Y=v=>(150-(v-mn)/sp*125).toFixed(1);
const L=pts.map((q,i)=>X(i)+","+Y(q[1])).join(" ");
s.innerHTML='<defs><linearGradient id="a'+id+'" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#00e5ff" stop-opacity=".35"/><stop offset="1" stop-color="#8b5cf6" stop-opacity="0"/></linearGradient></defs><polygon fill="url(#a'+id+')" points="0,160 '+L+' 600,160"/><polyline fill="none" stroke="#00e5ff" stroke-width="2.2" style="filter:drop-shadow(0 0 5px #00e5ff)" points="'+L+'"/><text x="6" y="14" font-size="11" fill="#7d8db0">maks '+f(mx,0)+'</text><text x="6" y="166" font-size="11" fill="#7d8db0">min '+f(mn,0)+'</text>'}
line("c1",D.eq);line("c2",D.fwd);
document.getElementById("o").innerHTML=[["Slot terjadwal ("+f(o.slot_menit,0)+" menit)",f(o.slot_terjadwal,0)],["Slot terlaksana",f(o.slot_terlaksana,0)],["Uptime",f(o.uptime_pct,2,"%")],
["Panggilan tercatat / selesai",f(o.panggilan_tercatat,0)+" / "+f(o.panggilan_selesai,0)],["Error API",f(o.error_api_total,0)],["Pemakaian kill switch",f(o.pemakaian_kill_switch,0)],["Data tidak valid",f(o.data_tidak_valid,0)]].map(r=>row(...r)).join("");
const eg=o.error_per_jenis||{};document.getElementById("oc").innerHTML=Object.keys(eg).map(n=>"Error &ldquo;"+n+"&rdquo;: "+eg[n].jumlah+"x, contoh: <span class='bad'>"+((eg[n].contoh[0]||{}).msg||"")+"</span>").join("<br>")+"<br>"+(o.catatan||"");
document.getElementById("g").innerHTML=w?"<tr><th>Metrik</th><th>Backtest (jendela sama)</th><th>Forward</th><th>Selisih</th></tr>"+[["Return total (%)",w.return_total_pct,k.return_total_pct],["Max drawdown (%)",w.max_drawdown_pct,k.max_drawdown_pct],["Jumlah trade",w.jumlah_trade,p.jumlah_trade_tertutup]].map(r=>row(r[0],f(r[1]),f(r[2]),(r[1]==null||r[2]==null)?"\u2014":f(r[2]-r[1]))).join(""):"<tr><td>Belum tersedia: jalankan backtest pada jendela forward test yang sama (bt_window_result.json), lalu buat ulang dashboard.</td></tr>";
document.getElementById("src").textContent="Sumber data: "+D.sumber.join(", ")+". Semua angka dibaca dari berkas ini (tidak ditulis manual).";
</script></html>"""
open("dashboard.html", "w", encoding="utf-8").write(HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/")))
print("dashboard.html dibuat,", os.path.getsize("dashboard.html"), "byte")
