#!/usr/bin/env python3
"""
Extract hadith-by-hadith commentary from the cached Sharh an-Nawawi 'ala
Sahih Muslim (shamela book 1711) and align with the app's muslim.json.

This edition is commentary-flow (only ~1,300 hadiths quoted in full), so the
alignment works per chapter:
  1. The sharh's كتاب headers are located and matched to the app's chapter
     list, giving each chapter a page range.
  2. Within a chapter's range, each hadith is anchored by its isnad opening
     (rare narrator names) or its rare matn words — monotonic, and never
     outside the chapter (kills false positives from other regions).
  3. A hadith's entry = the pages between its anchor and the next hadith's
     anchor. Unanchored hadiths simply get no package entry (the app falls
     back to its bundled encyclopedia explanations).

Output: sharh_muslim.json {source, entries:[{num, sharh}]} keyed by the
app's idInBook numbering.
"""
import json, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shamela_parse import parse_page, normalize, content_words, CACHE, STOP

BUILD = "/home/z/my-project/sharh_build"
CACHE1711 = os.path.join(CACHE, '1711')

def load_pages():
    pages = []
    for f in sorted(os.listdir(CACHE1711), key=lambda x: int(x.split('.')[0])):
        pg = int(f.split('.')[0])
        paras = parse_page(os.path.join(CACHE1711, f))
        if paras is None:
            continue
        text = "\n".join(p["text"] for p in paras).strip()
        if len(text) < 50:
            continue
        pages.append({"page": pg, "text": text, "sig": content_words(text)})
    return pages

def find_chapter_starts(pages):
    """(page_index, title) for each كتاب header in the sharh. Headers can be
    standalone paragraphs or runs inside a larger paragraph, so both are
    scanned."""
    out = []
    for i, p in enumerate(pages):
        for line in p["text"].split("\n"):
            for piece in re.split(r'[()]', line):
                tn = normalize(piece)
                if re.match(r'^\s*كتاب\s+\S', tn) and 3 < len(tn) < 90:
                    title = piece.strip('()[]،,. ')
                    if title and (not out or normalize(out[-1][1]) != tn or i - out[-1][0] >= 4):
                        out.append((i, title))
    return out

def match_title(app_title, sharh_headers):
    """Best sharh header index for an app chapter title (word overlap).
    First-best wins: the sharh lists chapters in order and later look-alike
    sub-headers (e.g. a second 'كتاب الإيمان...' note) must not steal the
    match."""
    aw = set(normalize(app_title).split()) - {"كتاب"}
    best, bs = -1, 0
    for j, (idx, title) in enumerate(sharh_headers):
        sw = set(normalize(title).split()) - {"كتاب"}
        inter = len(aw & sw)
        if inter > bs:
            bs, best = inter, j
    return best if bs >= 1 else -1

def main():
    pages = load_pages()
    print(f"pages: {len(pages)}")
    page_sigs = [p["sig"] for p in pages]
    freq = Counter()
    for s in page_sigs:
        freq.update(s)

    book = json.load(open(f"{BUILD}/books/muslim.json"))
    hs = book["hadiths"]
    chapters = {c["id"]: c["arabic"] for c in book["chapters"]}

    sharh_headers = find_chapter_starts(pages)
    print(f"sharh chapter headers: {len(sharh_headers)}")

    # chapter -> (start_idx, end_idx) in the sharh page list
    ranges = {}
    last_end = len(pages) - 1
    for cid, title in chapters.items():
        j = match_title(title, sharh_headers)
        if j >= 0:
            start = sharh_headers[j][0]
            # find next distinct header
            k = j + 1
            while k < len(sharh_headers) and sharh_headers[k][0] <= start + 1:
                k += 1
            end = sharh_headers[k][0] - 1 if k < len(sharh_headers) else last_end
            ranges[cid] = (start, end)
    # fill unmatched chapters by interpolation between neighbours (by order)
    cids = sorted(ranges)
    for cid in sorted(chapters):
        if cid in ranges:
            continue
        nxt = next((c for c in cids if c > cid and c in ranges), None)
        prv = next((c for c in reversed(cids) if c < cid and c in ranges), None)
        start = ranges[prv][1] + 1 if prv else 0
        end = ranges[nxt][0] - 1 if nxt else last_end
        if start <= end:
            ranges[cid] = (start, end)
    print(f"chapter ranges resolved: {len(ranges)}/{len(chapters)}")

    # group hadiths per chapter
    by_ch = {}
    for h in hs:
        by_ch.setdefault(h.get("chapterId", 1), []).append(h)

    anchors = {}
    for cid in sorted(by_ch):
        group = by_ch[cid]
        rng = ranges.get(cid)
        if not rng:
            continue
        start, end = rng
        n = len(group)
        span = max(1, end - start + 1)
        ptr = start
        last_k = 0
        for k, h in enumerate(group):
            num = h["idInBook"]
            est = start + int(k * span / n)
            lo = max(start, min(ptr, est + 10) - 2)
            hi = min(end, est + max(12, span // max(1, n) + 15)) + 1
            if lo >= hi:
                hi = min(end + 1, lo + 12)
            words = normalize(h["arabic"]).split()
            head = set(w for w in words[:22]
                       if len(w) >= 4 and 1 <= freq.get(w, 0) and w not in STOP)
            tail = words[int(len(words) * 0.5):] if len(words) > 30 else words
            rare = sorted(
                (w for w in set(tail)
                 if len(w) >= 4 and 1 <= freq.get(w, 0) <= 25 and w not in STOP),
                key=lambda w: freq.get(w, 0))[:6]
            found = None
            # 1) isnad-opening match (decisive)
            if len(head) >= 5:
                best, bs, sec = -1, 0, 0
                for i in range(lo, hi):
                    inter = len(head & page_sigs[i])
                    if inter > bs:
                        sec = bs; bs, best = inter, i
                    elif inter > sec:
                        sec = inter
                if best >= 0 and bs >= 5 and bs / len(head) >= 0.35 and bs - sec >= 2:
                    found = best
            # 2) rare matn words together
            if found is None and len(rare) >= 2:
                need = 2 if len(rare) >= 3 else 1
                for i in range(lo, hi):
                    hits = sum(1 for w in rare if w in page_sigs[i])
                    if hits >= need:
                        found = i
                        break
            # post-hoc verification: the anchored page itself must mention the
            # hadith (its head or rare words) — guards against narrator-name
            # coincidences
            if found is not None:
                sig_page = page_sigs[found]
                if not (len(head & sig_page) >= 4 or sum(1 for w in rare if w in sig_page) >= 2):
                    found = None
            if found is not None:
                anchors[num] = found
                ptr = max(ptr, found)
    print(f"anchored: {len(anchors)}/{len(hs)}")

    # ---- segments ----
    entries = []
    nums = sorted(anchors)
    MAX_SPAN = 25   # pages: cap the bleed between anchors
    for k, num in enumerate(nums):
        i = anchors[num]
        j = anchors[nums[k + 1]] if k + 1 < len(nums) else min(len(pages) - 1, i + 6)
        if j <= i:
            j = min(len(pages) - 1, i + 1)
        if j - i > MAX_SPAN:
            j = i + MAX_SPAN
        text = "\n\n".join(p["text"] for p in pages[i:j + 1]).strip()
        if len(text) < 250:
            continue
        entries.append({"num": num, "sharh": text})
    print(f"entries: {len(entries)}")
    chars = sum(len(e["sharh"]) for e in entries)
    print(f"total chars: {chars:,}")

    out = {
        "source": "المنهاج شرح صحيح مسلم — الإمام يحيى بن شرف النووي",
        "entries": entries,
    }
    with open(f"{BUILD}/sharh_muslim.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    em = {e["num"]: e["sharh"] for e in entries}
    for n in (1, 8, 2210, 7459):
        t = em.get(n)
        print(f"\n=== #{n}: {(t[:160] + '...') if t else 'NO ENTRY'}")

if __name__ == "__main__":
    main()
