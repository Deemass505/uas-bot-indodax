#!/usr/bin/env python3
"""ekspor_log.py: ambil seluruh log bot dari Upstash Redis (key bot:log) menjadi bot_log.jsonl.

Pemakaian:
  1) Isi environment variable (jangan ditulis di dalam file ini, jangan di-commit):
       Windows PowerShell:
         $env:UPSTASH_REDIS_REST_URL="https://xxxx.upstash.io"
         $env:UPSTASH_REDIS_REST_TOKEN="isi_token"
       macOS/Linux:
         export UPSTASH_REDIS_REST_URL="https://xxxx.upstash.io"
         export UPSTASH_REDIS_REST_TOKEN="isi_token"
  2) python ekspor_log.py            -> menulis bot_log.jsonl
     python ekspor_log.py nama.jsonl -> menulis ke nama lain

Skrip hanya MEMBACA (LLEN dan LRANGE). Tidak mengubah atau menghapus apa pun di Redis.
Tiap entri di bot:log sudah berupa string JSON ({"ts": ..., "type": ..., ...}),
jadi langsung ditulis satu baris per entri, format yang dibaca hitung_ulang.py.
"""
import os
import sys
import json
import urllib.request

KEY = "bot:log"
CHUNK = 1000


def redis(url, tok, cmd):
    req = urllib.request.Request(
        url,
        data=json.dumps(cmd).encode(),
        headers={
            "Authorization": "Bearer " + tok,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())["result"]


def main():
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    tok = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not tok:
        sys.exit("Isi dulu UPSTASH_REDIS_REST_URL dan UPSTASH_REDIS_REST_TOKEN (lihat petunjuk di atas file).")
    out = sys.argv[1] if len(sys.argv) > 1 else "bot_log.jsonl"

    total = int(redis(url, tok, ["LLEN", KEY]))
    print("Jumlah entri di %s: %d" % (KEY, total))

    n, bad = 0, 0
    first_ts = last_ts = None
    with open(out, "w", encoding="utf-8") as f:
        for start in range(0, total, CHUNK):
            rows = redis(url, tok, ["LRANGE", KEY, start, start + CHUNK - 1]) or []
            for raw in rows:
                try:
                    e = json.loads(raw)
                except Exception:
                    bad += 1
                    continue
                f.write(raw.strip() + "\n")
                n += 1
                ts = e.get("ts")
                first_ts = first_ts or ts
                last_ts = ts

    print("Ditulis: %s (%d entri, %d baris rusak dilewati)" % (out, n, bad))
    print("Entri pertama:", first_ts)
    print("Entri terakhir:", last_ts)
    if n != total:
        print("PERHATIAN: jumlah ditulis (%d) berbeda dari LLEN (%d). Jalankan ulang." % (n, total))


if __name__ == "__main__":
    main()
