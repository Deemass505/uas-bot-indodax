# Bot Dry Run Indodax (UAS Algoritma Trading, Trad1)

Dimas Arya Saputra, NIM 25110200012. Bot trading simulasi (dry run) long-only di pasar kripto IDR Indodax. Berjalan di Vercel, dijadwalkan GitHub Actions.

## Freeze
- Freeze date: Kamis 5 November 2026, 12.00 WIB
- Forward test: 5 Nov 2026 12.00 WIB sampai 19 Nov 2026 12.00 WIB
- Sejak freeze, aturan, parameter, dan universe tidak diubah. Perbaikan bug yang tidak mengubah aturan dicatat di bagian "Catatan perbaikan".
- Hash dan waktu commit freeze: dicatat di catatan pengumpulan RISE.

## Strategi (long-only, timeframe 4 jam, hanya candle tertutup)
Parameter ada di `api/_core.py` (dipakai bersama oleh bot dan backtest).
- Masuk: close bar tertutup > high tertinggi 20 bar sebelumnya DAN close > SMA(close, 100), bila belum ada posisi di pair itu.
- Keluar: close < low terendah 10 bar sebelumnya ATAU close < SMA 100.
- Sizing: min(20% equity, kas), maksimum 4 posisi terbuka, tanpa pyramiding, tanpa short, margin, atau leverage.
- Modal awal virtual Rp100.000.000.

## Universe
btcidr, ethidr, adaidr.
- Kriteria: volume 24 jam (vol_idr) >= Rp500 juta, spread bid-ask < 0,5%, dan sudah tercatat di Indodax lebih dari 3 tahun.
- Survivorship bias: koin yang baru listing tidak dipilih karena tidak punya data 3 tahun. Likuiditas awal periode backtest didekati dari volume candle 4 jam pada data history_v2, karena data order book historis tidak tersedia.

## Eksekusi simulasi
- Beli di ask dan jual di bid dari order book live. Bila order lebih besar dari level terbaik, level berikutnya dihabiskan dan dipakai harga rata-ratanya. Tidak ada fill di mid atau close.
- Fee: tarif taker all-in. Sumber 1, halaman resmi "Pertanyaan Mengenai Fee Transaksi Indodax" (help.indodax.com, https://help.indodax.com/hc/id, diakses 5 Nov 2026, IDR Market mode Pro: beli 0,20555% (service 0,20% + pajak 0% + CFX 0,00555%), jual 0,41555% (service 0,20% + pajak 0,21% + CFX 0,00555%). Sumber 2, https://indodax.com/api/pairs, diakses 5 Nov 2026: `trade_fee_percent_taker` = 0,2%. Dipakai yang lebih mahal, yaitu 0,41555% untuk beli dan jual (`FEE_TAKER` = 0.0041555). Akibatnya biaya sisi beli sengaja sedikit terlalu tinggi (konservatif).
- Minimum order Rp25.000 (/api/pairs menyebut Rp10.000; dipakai yang lebih ketat).
- Kuantitas dibulatkan ke bawah (QTY_DECIMALS = 8). Dicocokkan dengan /api/pairs pada 5 Nov 2026: quantity_increment = 1e-8 untuk btcidr, ethidr, dan adaidr.
- Equity: posisi terbuka dinilai di best bid. Equity harian dicatat pada panggilan pertama setelah 00.00 WIB.

## Validasi data dan risk management
- Bar yang belum tertutup dibuang (Time + 4 jam > server_time).
- Pair dilewati (tidak ada sinyal, dicatat dengan alasan, dicoba lagi di panggilan berikutnya) bila: candle tertutup terakhir lebih tua dari 2x timeframe, ada candle hilang di jendela indikator, harga atau volume nol, order book kosong, atau spread > 2%.
- Daily loss limit 3% dari equity awal hari (batas hari WIB). Bila terlampaui, tidak ada posisi baru sampai hari berikutnya.
- Kill switch: key Redis `bot:kill` = 1 atau env `KILL_SWITCH=1`. Tidak ada posisi baru, penutupan posisi tetap jalan, dan tercatat di log.
- Idempotency: tiap candle per pair hanya diproses sekali (state `last_candle`), ditambah lock Redis agar dua panggilan tidak berjalan bersamaan.
- Retry maksimum 3 kali dengan jeda dan timeout 10 detik. Respons kosong dianggap error.
- Endpoint `/api/tick` wajib header `Authorization: Bearer <CRON_SECRET>`.

## Penjadwalan dan penyimpanan
- GitHub Actions (`.github/workflows/tick.yml`) memanggil `/api/tick` tiap 30 menit (UTC). Waktu panggilan sebenarnya dicatat di log sebagai dasar uptime.
- State dan log disimpan di Upstash Redis (`bot:state`, `bot:log`, satu baris JSON per kejadian).
- Snapshot order book (10 level bid/ask per pair) dicatat tiap panggilan, dipakai untuk estimasi spread dan slippage.

## Menjalankan dan deploy
1. Push repo ke GitHub dan import ke Vercel.
2. Pasang Upstash Redis dari Vercel Marketplace. Isi env: `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `CRON_SECRET`, `FEE_TAKER`, `KILL_SWITCH=0` (lihat `.env.example`).
3. Di GitHub Secrets isi `CRON_SECRET` (sama dengan Vercel) dan `TICK_URL` (https://uas-bot-indodax-fawn.vercel.app/api/tick).
4. Jalankan workflow `tick` secara manual untuk uji. Hasil yang diharapkan: `{"status": "ok", ...}`.
Tidak ada secret di repositori; `.env` ada di `.gitignore`.

## Catatan perubahan dari versi UTS
- Timeframe harian (saham Kompas 100) menjadi 4 jam (kripto IDR Indodax, universe 3 pair).
- Logika Donchian breakout + filter SMA, long-only, tetap. Periode 20/10/100 disesuaikan untuk pasar kripto 24/7.
- Eksekusi memakai bid/ask order book dan fee taker all-in, bukan harga close.

## Backtest
Periode: 1 Nov 2023 sampai 4 Nov 2026 (3 tahun lebih). Sumber data: history_v2 tf=240. Fee 0,41555% per sisi (beli dan jual). Spread dan slippage backtest diukur dari median snapshot order book yang dikumpulkan bot; angka dan tanggal pengukurannya dilaporkan di dashboard. Backtest memakai api/_core.py yang sama dan tidak mengubah parameter di atas. Hasil dilaporkan terpisah..

## Catatan perbaikan setelah freeze
(kosong)
