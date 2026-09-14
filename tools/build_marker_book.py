#!/usr/bin/env python3
"""
Generic extractor for [N]-marker sharh books on shamela:
  - 21543 تطريز رياض الصالحين (Riyadh al-Salihin)
  - 522    حاشية السندي على سنن النسائي
  - 5760   عون المعبود (Sunan Abi Dawud)
  - 9810   حاشية السندي على سنن ابن ماجه (N - حدثنا headers, Fath-like)

Each [N] marker starts the commentary of that book's hadith number N. The
numbering correspondence with the app's JSON is verified empirically (direct
number mapping with text verification + monotonic window fallback for the
rest).

Usage: python3 build_marker_book.py <book_id> <app_json> <out_json> <source> <pages>
"""
import json, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shamela_parse import parse_page, normalize, content_words, CACHE, STOP

BUILD = "/home/z/my-project/sharh_build"

def load_doc(book_id, last_page):
    d = os.path.join(CACHE, str(book_id))
    doc = []
    for p in range(1, last_page + 1):
        path = os.path.join(d, f"{p}.html")
        if not os.path.exists(path):
            continue
        paras = parse_page(path)
        if paras is None:
            continue
        for para in paras:
            para["page"] = p
        doc.extend(paras)
    return doc

def extract_marker_segments(doc):
    """Segments starting at c4 [N] markers (run-level split)."""
    segments = []
    for para in doc:
        runs = para["runs"]
        if not runs:
            continue
        for k, (cls, txt) in enumerate(runs):
            t = re.sub(r'[\u0610-\u061A\u064B-\u065F\u06D6-\u06ED\u0640]', '', txt.strip())
            if cls == "c4" and re.match(r'^\[[\d٠-٩]{1,4}\]$', t):
                n = int(t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))[1:-1])
                segments.append({
                    "hdr_num": n,
                    "head": "".join(x for _, x in runs[k+1:])[:400].strip(),
                    "text_parts": ["".join(x for _, x in runs[k+1:])],
                    "page": para["page"],
                })
                break  # one marker per paragraph is enough
            # Fath-like "N - حدثنا..." headers (for 9810)
            if cls == "" and k == 0:
                tn = normalize(txt)
                m = re.match(r'^(\d{1,4})\s+(.*)$', tn)
                if m and re.match(r'^(?:و\s*)?(?:حدثن[اي]|اخبرن[اي]|قال|سمعت)', normalize(m.group(2))):
                    segments.append({
                        "hdr_num": int(m.group(1)),
                        "head": txt[:400],
                        "text_parts": [],
                        "page": para["page"],
                    })
                    break
    # attach following paragraphs to the last segment (for Fath-like books)
    ...
    return segments

def extract_flow(doc, mode):
    """mode='marker': segments split at [N] c4 markers, text = everything until
    the next marker. mode='header': Fath-like N- headers."""
    segments = []
    cur = None
    for para in doc:
        runs = para["runs"]
        started_here = False
        if runs and mode in ("marker", "marker_after"):
            # marker can start the paragraph OR appear mid-paragraph — split there
            marker_at = None
            for k, (cls, txt) in enumerate(runs):
                t = re.sub(r'[\u0610-\u061A\u064B-\u065F\u06D6-\u06ED\u0640]', '', txt.strip())
                if cls == "c4" and re.match(r'^\[[\d٠-٩]{1,4}\]$', t):
                    marker_at = (k, int(t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))[1:-1]))
                    break
            if marker_at is not None:
                k, n = marker_at
                before = "".join(x for _, x in runs[:k])
                after = "".join(x for _, x in runs[k+1:])
                if mode == "marker_after":
                    # Tuhfa convention: the hadith text PRECEDES the [N] marker,
                    # the commentary follows it.
                    cur = {"hdr_num": n, "head": before[:500], "parts": [after], "page": para["page"]}
                    segments.append(cur)
                    continue
                if cur is not None and before.strip():
                    cur["parts"].append(before)
                cur = {"hdr_num": n, "head": after[:400], "parts": [after], "page": para["page"]}
                segments.append(cur)
                continue
        elif runs and mode == "header":
            tn = normalize(para["text"])
            m = re.match(r'^(\d{1,4})\s+(.*)$', tn)
            if m and re.match(r'^(?:و\s*)?(?:حدثن[اي]|اخبرن[اي]|قال|سمعت)', normalize(m.group(2))):
                cur = {"hdr_num": int(m.group(1)), "head": para["text"][:400], "parts": [], "page": para["page"]}
                segments.append(cur)
                continue
        if cur is not None:
            cur["parts"].append(para["text"])
    for s in segments:
        s["parts"] = [p for p in (x.strip() for x in s["parts"]) if p and p != "ــ"]
    return segments

def main():
    book_id = int(sys.argv[1])
    app_json = sys.argv[2]
    out_json = sys.argv[3]
    source_name = sys.argv[4]
    last_page = int(sys.argv[5])
    mode = sys.argv[6] if len(sys.argv) > 6 else "marker"
    global_match = len(sys.argv) > 7 and sys.argv[7] == "global"
    force_direct = len(sys.argv) > 7 and sys.argv[7] == "direct"

    doc = load_doc(book_id, last_page)
    print(f"paragraphs: {len(doc)}")
    segs = extract_flow(doc, mode)
    print(f"segments: {len(segs)} (max num {max((s['hdr_num'] for s in segs), default=0)})")

    seg_by_num = {}
    for i, s in enumerate(segs):
        n = s["hdr_num"]
        if n not in seg_by_num:
            seg_by_num[n] = i
    seg_sigs = [content_words(s["head"]) for s in segs]
    # bounded full-text sigs: head + the first ~2000 chars of the segment — a
    # marker-less mega-segment must not out-match everything by sheer size
    seg_full_sigs = [
        content_words(s["head"] + "\n" + "\n".join(s["parts"])[:2000])
        for s in segs
    ]
    # mega-segments (marker-less regions) are excluded from matching entirely
    mega = {i for i, s in enumerate(segs) if sum(len(x) for x in s["parts"]) > 60000}
    for i in mega:
        seg_full_sigs[i] = set()
        seg_sigs[i] = set()

    book = json.load(open(f"{BUILD}/books/{app_json}"))
    hs = book["hadiths"]

    # ---- number correspondence check ----
    agree = disagree = missing = 0
    for h in hs[:1500]:
        num = h["idInBook"]
        i = seg_by_num.get(num)
        if i is None:
            missing += 1
            continue
        hw = content_words(h["arabic"])
        inter = len(hw & seg_sigs[i])
        # the sharh may quote only a short matn fragment — a small overlap on a
        # long isnad-heavy hadith still counts as agreement
        if inter >= 4 or (hw and inter / len(hw) >= 0.2) or \
           (inter >= 3 and len(hw) >= 15):
            agree += 1
        else:
            disagree += 1
    print(f"number check (first 1500): agree={agree} disagree={disagree} missing={missing}")

    # ---- build entries: direct number map ONLY when the numbering
    # correspondence is verified; otherwise pure monotonic window alignment ----
    freq = Counter()
    for s in seg_sigs:
        freq.update(s)
    entries = []
    have = set()
    ptr = 0
    checked = sum(1 for h in hs[:1500] if h["idInBook"] in seg_by_num)
    direct_ok = force_direct or (checked > 0 and agree / max(1, agree + disagree) > 0.6)
    print(f"direct mapping {'ENABLED' if direct_ok else 'DISABLED (numbering differs)'}")
    for h in hs:
        num = h["idInBook"]
        i = None
        if direct_ok:
            # pick the best of N-1/N/N+1 — the numberings align but some
            # regions drift by one (edition counting differences); verified
            # against the FULL segment text (the commentary quotes the hadith
            # fragments anywhere inside it, not just at the head)
            hw0 = content_words(h["arabic"])
            best_i, best_inter = None, 0
            for off in (-1, 0, 1):
                j = seg_by_num.get(num + off)
                if j is None:
                    continue
                inter = len(hw0 & seg_full_sigs[j])
                if inter > best_inter:
                    best_inter, best_i = inter, j
            min_verify = 1 if len(hs) > 5000 and len(segs) < 2500 else 3
            if best_i is not None and best_inter >= min_verify:
                i = best_i
        if i is not None:
            text = "\n\n".join(segs[i]["parts"])
            if len(text) >= 60:
                entries.append({"num": num, "sharh": text.strip()})
                have.add(num)
            ptr = max(ptr, i)
            continue
        # window fallback / primary alignment
        hw = content_words(h["arabic"])
        if not hw:
            continue
        if global_match:
            # order-independent matching (the app's edition rearranges the
            # book): find the globally best-matching segment with STRICT
            # thresholds — only near-exact text matches are accepted.
            best, bs, sec = -1, 0, 0
            for j in range(len(segs)):
                inter = len(hw & seg_sigs[j])
                if inter > bs:
                    sec = bs; bs, best = inter, j
                elif inter > sec:
                    sec = inter
            ratio = bs / max(1, len(hw))
            if (bs >= 5 and ratio >= 0.5) or (bs >= 8 and ratio >= 0.35) or \
               (bs >= 4 and ratio >= 0.65):
                text = "\n\n".join(segs[best]["parts"])
                if len(text) >= 60:
                    entries.append({"num": num, "sharh": text.strip()})
                    have.add(num)
            continue
        # proportional anchor: the app's hadith count and the sharh's segment
        # count can differ in ratio; center the window on the proportional
        # estimate so stalled pointers cannot strand later hadiths
        est = int(num * len(segs) / max(1, len(hs)))
        base = max(ptr - 30, min(est, est)) if abs(ptr - est) > 400 else ptr
        lo = max(0, min(ptr, base) - 30)
        hi = min(len(segs), max(ptr, base) + 400)
        best, bs, sec = -1, 0, 0
        for j in range(lo, hi):
            inter = len(hw & seg_full_sigs[j])
            if inter > bs:
                sec = bs; bs, best = inter, j
            elif inter > sec:
                sec = inter
        ratio = bs / max(1, len(hw))
        margin = bs - sec
        if (bs >= 4 and ratio >= 0.35) or (bs >= 3 and ratio >= 0.55) or \
           (bs >= 5 and ratio >= 0.25 and margin >= 2) or \
           (bs >= 10 and margin >= 3) or (bs >= 12 and ratio >= 0.25):
            text = "\n\n".join(segs[best]["parts"])
            if len(text) >= 60:
                entries.append({"num": num, "sharh": text.strip()})
                have.add(num)
                ptr = best
    print(f"entries: {len(entries)}/{len(hs)}")
    chars = sum(len(e["sharh"]) for e in entries)
    print(f"total chars: {chars:,}")

    out = {"source": source_name, "entries": entries}
    with open(f"{BUILD}/{out_json}", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"wrote {out_json}")

    em = {e["num"]: e["sharh"] for e in entries}
    for n in list(em)[:2] + [len(hs) // 2, len(hs)]:
        t = em.get(n)
        if t:
            print(f"\n=== #{n}: {t[:170]}...")

if __name__ == "__main__":
    main()
