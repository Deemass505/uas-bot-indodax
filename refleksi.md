# Refleksi: Backtest vs Forward Test (Bot Dry Run Indodax)

Dimas Arya Saputra, NIM 25110200012. Angka di bawah dihitung dari log mentah (`bot_log.jsonl`) oleh `hitung_ulang.py` dan dari `bt_result.json` / `bt_window_result.json`.

## 1. Ringkasan
- Strategi: Donchian breakout 20/10 bar + filter SMA 100, long-only, timeframe 4 jam, universe btcidr, ethidr, adaidr.
- Backtest 1 Nov 2023 s.d. 9 Nov 2026 (≥3 tahun): return 28.13%, CAGR 8.51%, max drawdown -22.42%, 255 trade, win rate 30.2%, profit factor 1.20, porsi biaya 67.4% dari laba kotor. Buy and hold BTC/IDR pada periode itu: 130.8%. Strategi kalah jauh dari buy and hold, dan itu saya laporkan apa adanya.
- Forward test 2026-11-05 12.00 WIB s.d. 13 Nov 2026 21.00 WIB (8.38 hari, sesuai cakupan log yang diekspor): 0 order, return 0.00%, max drawdown 0.00%, equity akhir Rp100,000,000.

## 2. Kecocokan backtest dan forward test
- Backtest dijalankan ulang pada jendela forward test yang sama dengan candle yang sama: 0 trade, return 0.00%. Forward test juga 0 order, jadi hasilnya identik.
- Sinyal masuk/keluar dibandingkan candle demi candle (sinyal, close, SMA, high tertinggi, low terendah): 120 dari 120 candle cocok (100.00%). Bot dan backtest memakai fungsi `compute_signal` yang sama di `api/_core.py`.
- Karena tidak ada order selama jendela itu, tidak ada selisih harga fill yang perlu dijelaskan. Penyebabnya bukan kegagalan bot: seluruh 120 sinyal adalah HOLD karena tidak ada breakout di atas high 20 bar yang juga berada di atas SMA 100 pada ketiga pair. Timeframe 4 jam dengan ±8 hari data hanya menghasilkan sekitar 40 candle per pair, jadi peluang sinyal beli kecil. Hal ini menunjukkan keterbatasan: forward test ini tidak menguji eksekusi order di kondisi nyata.
- Jika order terjadi, sumber selisih fill yang diharapkan: spread (median terukur dari snapshot: btcidr 0.0169%, ethidr 0.0545%, adaidr 0.1881%), slippage (median 0% pada ukuran order Rp20 juta), dan keterlambatan jadwal sampai 30 menit setelah candle tertutup.

## 3. Uptime dan gangguan
- Slot terjadwal (30 menit): 402, terlaksana 305, uptime 75.87%.
- Gangguan: 07 Nov 22:00 WIB s.d. 09 Nov 18:48 WIB Indodax membalas HTTP 403 Forbidden pada panggilan dari fungsi Vercel (172 error di log, semuanya 403, tidak ada jenis error lain). Bot mencatat tiap kegagalan dan pulih otomatis setelah wilayah fungsi Vercel dipindah.
- Di luar jendela gangguan itu, uptime 97.12% (304 dari 313 slot). Gangguan berasal dari sisi Indodax/Vercel dan tercatat di log.
- Dampak: selama gangguan bot tidak mengevaluasi candle. Karena panggilan setiap 30 menit dan candle 4 jam diproses sekali (idempotency), candle yang terlewat saat gangguan tidak menghasilkan sinyal di log. Penjadwal kedua (cron-job.org) ditambahkan karena GitHub Actions hanya berjalan sekitar sejam sekali.

## 4. Biaya dan realisme
- Fee taker all-in 0,41555% (halaman resmi Indodax: beli 0,20555%, jual 0,41555%; `/api/pairs` 0,2%; dipakai yang lebih mahal untuk kedua sisi) membuat biaya menyerap 67.4% laba kotor backtest. Dengan 255 trade dalam 3 tahun, strategi frekuensi tinggi seperti ini sensitif terhadap fee.
- Pada kondisi forward test tidak ada order, jadi tidak ada angka biaya riil yang bisa dibandingkan dengan backtest.

## 5. Catatan perbaikan setelah freeze
Aturan, parameter, dan universe tidak diubah sejak freeze. Perubahan yang dilakukan: `FEE_TAKER` disesuaikan ke 0.0041555 agar sama dengan README; penjadwal cron-job.org ditambahkan; wilayah fungsi Vercel dipindah untuk mengatasi 403; skrip `ekspor_log.py`, `hitung_ulang.py`, `buat_dashboard.py` ditambahkan.
