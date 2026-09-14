#!/usr/bin/env python3
"""
Extractors for the remaining sharh books:

  Sabil as-Salam (1082, شرح بلوغ المرام): paragraphs whose FIRST run is a c2
  span are the quoted-hadith + commentary units — segment boundaries there.

  Zarqani (551, شرح الموطأ): paragraphs starting with "N - M - (" numbered
  pairs mark commentary units; the hadith text precedes.

Output: per-book sharh packages keyed by the app's idInBook numbering, via
monotonic window alignment with proportional anchoring.
"""
import json, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shamela_parse import parse_page, normalize, content_words, CACHE

BUILD = "/home/z/my-project/sharh_build"

def load_pages(book_id, last_page):
    pages = []
    d = os.path.join(CACHE, str(book_id))
    for f in sorted(os.listdir(d), key=lambda x: int(x.split('.')[0])):
        pg = int(f.split('.')[0])
        if pg > last_page:
            continue
        paras = parse_page(os.path.join(d, f))
        if paras is None:
            continue
        for para in paras:
            para["page"] = pg
        pages.extend(paras)
    return pages

def extract_sabil(pages):
    """Segments at paragraphs whose first run is a c2 quote (the hadith)."""
    segs = []
    cur = None
    for para in pages:
        runs = para["runs"]
        if runs and runs[0][0] == "c2" and len(runs[0][1].strip()) > 25:
            cur = {"head": runs[0][1][:500], "parts": [para["text"]], "page": para["page"]}
            segs.append(cur)
            continue
        if cur is not None:
            cur["parts"].append(para["text"])
    for s in segs:
        s["parts"] = [p for p in (x.strip() for x in s["parts"]) if p]
    return segs

def extract_zarqani(pages):
    """Segments at the Muwatta hadith-text paragraphs (they precede the
    numbered commentary): 'حدثني/وحدثني ... عن مالك ...' openings."""
    segs = []
    cur = None
    OPEN = re.compile(r'^(?:و\s*)?(?:حدثن[اي]|اخبرن[اي]|انبانا)\s+.*\sعن\s')
    for para in pages:
        tn = normalize(para["text"])
        if len(tn) > 60 and OPEN.match(tn):
            cur = {"head": para["text"][:500], "parts": [para["text"]], "page": para["page"]}
            segs.append(cur)
            continue
        if cur is not None:
            cur["parts"].append(para["text"])
    for s in segs:
        s["parts"] = [p for p in (x.strip() for x in s["parts"]) if p]
    return segs

def build(app_json, out_json, source, segs):
    seg_sigs = [content_words(s["head"] + "\n" + "\n".join(s["parts"])[:2000]) for s in segs]
    mega = {i for i, s in enumerate(segs) if sum(len(x) for x in s["parts"]) > 60000}
    for i in mega:
        seg_sigs[i] = set()
    book = json.load(open(f"{BUILD}/books/{app_json}"))
    hs = book["hadiths"]
    entries = []
    ptr = 0
    for h in hs:
        num = h["idInBook"]
        hw = content_words(h["arabic"])
        if not hw:
            continue
        est = int(num * len(segs) / max(1, len(hs)))
        base = ptr if abs(ptr - est) <= 400 else est
        lo = max(0, base - 30)
        hi = min(len(segs), base + 400)
        best, bs, sec = -1, 0, 0
        for j in range(lo, hi):
            inter = len(hw & seg_sigs[j])
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
            if 60 <= len(text) <= 60000:
                entries.append({"num": num, "sharh": text.strip()})
                ptr = best
    print(f"entries: {len(entries)}/{len(hs)}")
    chars = sum(len(e["sharh"]) for e in entries)
    print(f"total chars: {chars:,}")
    out = {"source": source, "entries": entries}
    with open(f"{BUILD}/{out_json}", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"wrote {out_json}")
    em = {e["num"]: e["sharh"] for e in entries}
    for n in list(em)[:2]:
        print(f"=== #{n}: {em[n][:160]}...")

if __name__ == "__main__":
    which = sys.argv[1]
    if which == "sabil":
        pages = load_pages(1082, 2548)
        print(f"paragraphs: {len(pages)}")
        segs = extract_sabil(pages)
        print(f"segments: {len(segs)}")
        build("bulugh_almaram.json", "sharh_bulugh_almaram.json",
              "سبل السلام شرح بلوغ المرام — محمد بن إسماعيل الصنعاني", segs)
    elif which == "zarqani":
        pages = load_pages(551, 4156)
        print(f"paragraphs: {len(pages)}")
        segs = extract_zarqani(pages)
        print(f"segments: {len(segs)}")
        build("malik.json", "sharh_malik.json",
              "شرح الزرقاني على الموطأ — محمد بن عبد الباقي الزرقاني", segs)
