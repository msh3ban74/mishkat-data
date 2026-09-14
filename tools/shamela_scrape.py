#!/usr/bin/env python3
"""
Scrape shamela.ws book pages into a local cache for offline processing.

Usage:
  python3 shamela_scrape.py <book_id> <page_start> <page_end> [workers]

Each page is saved as tools cache: /home/z/my-project/sharh_cache/<book_id>/<page>.html
Resumable: existing non-empty files are skipped.
Cloudflare challenges trigger a shared cool-down.
"""
import sys, os, re, time, random, threading, queue
import urllib.request, urllib.error
import gzip

BASE = "https://shamela.ws/book"
CACHE = "/home/z/my-project/sharh_cache"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip",
    "Connection": "keep-alive",
}

# global cool-down coordination
cool = threading.Condition()
cool_until = 0.0
challenge_hits = 0

def is_challenge(html_bytes: bytes) -> bool:
    return b"Just a moment" in html_bytes[:2000] or b"challenges.cloudflare.com" in html_bytes[:3000]

def fetch(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers=dict(HEADERS, Referer="https://shamela.ws/"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if r.headers.get("Content-Encoding", "") == "gzip":
            data = gzip.decompress(data)
        return r.status, data

def worker(book_id: int, q: "queue.Queue", stats: dict, lock: threading.Lock):
    global cool_until, challenge_hits
    while True:
        try:
            page = q.get_nowait()
        except queue.Empty:
            return
        out = os.path.join(CACHE, str(book_id), f"{page}.html")
        if os.path.exists(out) and os.path.getsize(out) > 4000:
            with lock:
                stats["skip"] += 1
            q.task_done()
            continue
        ok = False
        for attempt in range(6):
            # respect cool-down
            with cool:
                wait = cool_until - time.time()
                while wait > 0:
                    cool.wait(wait)
                    wait = cool_until - time.time()
            try:
                status, data = fetch(f"{BASE}/{book_id}/{page}")
                if status == 200 and not is_challenge(data):
                    if len(data) > 2000:
                        with open(out, "wb") as f:
                            f.write(data)
                        with lock:
                            stats["ok"] += 1
                        ok = True
                    else:
                        # tiny page: probably "not found" page
                        with lock:
                            stats["small"] += 1
                        ok = True  # don't retry; record as small
                    break
                elif status == 404:
                    with lock:
                        stats["404"] += 1
                    ok = True
                    break
                else:
                    raise RuntimeError(f"status {status}")
            except Exception as e:
                err = str(e)[:60]
                if "404" in err:
                    with lock:
                        stats["404"] += 1
                    ok = True
                    break
                # challenge or network error -> backoff
                with cool:
                    challenge_hits += 1
                    dur = min(120.0, 15.0 * (1 + challenge_hits // 3)) + random.uniform(2, 8)
                    cool_until = max(cool_until, time.time() + dur)
                    print(f"  [cooldown {dur:.0f}s] {e}", flush=True)
                    cool.notify_all()
                time.sleep(random.uniform(1, 3))
        if not ok:
            with lock:
                stats["fail"] += 1
        q.task_done()
        # gentle pacing
        time.sleep(random.uniform(0.02, 0.12))

def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    book_id = int(sys.argv[1])
    p_start, p_end = int(sys.argv[2]), int(sys.argv[3])
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    d = os.path.join(CACHE, str(book_id))
    os.makedirs(d, exist_ok=True)
    q: "queue.Queue" = queue.Queue()
    for p in range(p_start, p_end + 1):
        q.put(p)
    stats = {"ok": 0, "skip": 0, "fail": 0, "404": 0, "small": 0}
    lock = threading.Lock()
    ths = [threading.Thread(target=worker, args=(book_id, q, stats, lock), daemon=True) for _ in range(workers)]
    t0 = time.time()
    for t in ths:
        t.start()
    # progress monitor
    total = p_end - p_start + 1
    while any(t.is_alive() for t in ths):
        time.sleep(20)
        done = stats["ok"] + stats["skip"] + stats["fail"] + stats["404"] + stats["small"]
        rate = done / max(1e-9, time.time() - t0)
        print(f"book {book_id}: {done}/{total} ({rate:.1f}/s) {stats}", flush=True)
    for t in ths:
        t.join()
    print(f"DONE book {book_id}: {stats} in {time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    main()
