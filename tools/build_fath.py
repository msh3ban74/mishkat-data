#!/usr/bin/env python3
"""
Extract hadith-by-hadith commentary segments from the cached Fath al-Bari
(shamela book 1673, pages 494..7978) and align them with the app's
bukhari.json hadith list, then emit the per-book sharh package.

Alignment strategy (verified against the data):
  PRIMARY  — direct hadith-number mapping. The app's bukhari.json idInBook
  uses the same standard numbering as the Fath al-Bari print (verified:
  app#1=الحميدي، app#221=حدثنا عبدان، app#331=محمد بن سنان عن هشيم ... all
  land on the identically-numbered Fath headers with identical text).
  FALLBACK — monotonic content-word window alignment for numbers with no
  extracted segment (~170) and for verification.

Output: sharh_bukhari.json {source, entries:[{num, sharh}]} keyed by the
app's idInBook.
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shamela_parse import load_book, normalize, content_words

CACHE = "/home/z/my-project/sharh_cache"
BUILD = "/home/z/my-project/sharh_build"

ISNAD_STARTS = (
    "حدثنا", "حدثني", "اخبرنا", "اخبرني", "انبانا", "انبا", "سمعت", "قال",
    "يذكر", "حدثه", "حدثت", "حدث", "قالت", "وعن", "وقال", "زعم", "بلغنا",
)
CHAP_STARTS = ("كتاب", "باب", "فصل", "كتب", "خاتمة", "ترجمة", "الخاتمة", "مقدمة", "بسم")

NUM_PREFIX = re.compile(r'^\s*(\d{1,4})\s*(?:[-–—]\s*)?(.+)$')
HADITH_MARKER = re.compile(r'^\s*الحديث\s*(\d{1,4})')

def extract_fath():
    doc = load_book(1673, 494, 7978)
    print(f"paragraphs: {len(doc)}")
    segments = []
    cur = None
    for para in doc:
        t = para["text"]
        tn = normalize(t)
        m_marker = HADITH_MARKER.match(tn)
        m_num = NUM_PREFIX.match(tn)
        if m_marker:
            n = int(m_marker.group(1))
            if cur is not None and cur.get("hdr_num") is None:
                cur["hdr_num"] = n
                cur["commentary"].append(t)
            elif cur is None or cur.get("hdr_num") is not None:
                cur = {"hdr_num": n, "header": "", "commentary": [t], "page": para["page"]}
                segments.append(cur)
            continue
        if m_num:
            n = int(m_num.group(1))
            rest_norm = normalize(m_num.group(2))
            is_chapter = any(rest_norm.startswith(w) or rest_norm.startswith("و" + w)
                             for w in CHAP_STARTS)
            is_isnad = any(rest_norm.startswith(w) for w in ISNAD_STARTS)
            if is_chapter:
                continue
            if is_isnad or len(t) < 900:
                cur = {"hdr_num": n, "header": t, "commentary": [], "page": para["page"],
                       "is_isnad": is_isnad}
                segments.append(cur)
                continue
        if cur is not None:
            cur["commentary"].append(t)

    # ---- validate: drop numbered false-positives whose number is far from the
    # running sequence (enumerations inside commentary), then merge only the
    # ADJACENT duplicates (header segment + marker segment of the same hadith).
    real = []
    last_num = 0
    for s in segments:
        n = s.get("hdr_num")
        if s.get("is_isnad") or not s["header"]:
            # isnad header or marker-created: always real
            if n is not None:
                last_num = n
            real.append(s)
            continue
        # non-isnad numbered paragraph: real only when its number continues the
        # sequence (within a generous window) — e.g. "N - وقال الليث حدثني..."
        if n is not None and abs(n - last_num) <= 60 and n >= last_num - 5:
            last_num = n
            real.append(s)
        # else: numbered enumeration inside commentary -> dropped

    merged = []
    for idx, s in enumerate(real):
        n = s.get("hdr_num")
        if n is None:
            merged.append(s)
            continue
        if merged and merged[-1].get("hdr_num") == n:
            prev = merged[-1]
            if not prev["header"] and s["header"]:
                prev["header"] = s["header"]
            prev["commentary"].extend(s["commentary"])
            continue
        # also merge a marker-created segment directly after a same-number header
        merged.append(s)
    out = [s for s in merged if s["header"] or s.get("hdr_num")]
    print(f"segments: {len(segments)} -> validated: {len(real)} -> merged: {len(out)}")
    return out

def window_align(app_hadiths, segments, seg_by_num):
    """Monotonic content-word alignment for numbers without a direct segment."""
    seg_sigs = [content_words(s["header"]) for s in segments]
    ptr = 0
    mapping = {}
    for h in app_hadiths:
        num = h["idInBook"]
        if num in seg_by_num:
            i = seg_by_num[num]
            if i >= ptr - 30:
                ptr = max(ptr, i)
            continue
        hw = content_words(h["arabic"])
        if not hw:
            continue
        expected = ptr + max(0, num - ptr)
        lo = max(0, ptr - 30)
        hi = min(len(segments), ptr + 250)
        scores = [(i, len(hw & seg_sigs[i])) for i in range(lo, hi)]
        if not scores:
            continue
        top = max(s for _, s in scores)
        threshold = int(0.88 * top)
        cand = [i for i, s in scores if s >= threshold and s >= 4] or \
               [i for i, s in scores if s == top]
        best = min(cand, key=lambda i: (abs(i - expected), i))
        best_score = dict(scores)[best]
        second = max((s for i, s in scores if i not in cand), default=0)
        ratio = best_score / max(1, len(hw))
        margin = best_score - second
        if (best_score >= 5 and ratio >= 0.55) or \
           (best_score >= 6 and margin >= 4) or \
           (best_score >= 15 and margin >= 5) or \
           (best_score >= 6 and margin >= 2 and ratio >= 0.45) or \
           (best_score >= 8 and ratio >= 0.6):
            mapping[num] = best
            ptr = best
    return mapping

def main():
    segs = extract_fath()
    seg_by_num = {}
    for i, s in enumerate(segs):
        n = s.get("hdr_num")
        if n is not None and n not in seg_by_num:
            seg_by_num[n] = i

    book = json.load(open(f"{BUILD}/books/bukhari.json"))
    hs = book["hadiths"]

    # direct number mapping
    direct = {num: seg_by_num[num] for num in
              (h["idInBook"] for h in hs) if num in seg_by_num}
    print(f"direct number-mapped: {len(direct)}/{len(hs)}")

    # text-verification of the number mapping (long-signature hadiths)
    seg_sigs = [content_words(s["header"]) for s in segs]
    suspects = 0
    for h in hs:
        num = h["idInBook"]
        i = direct.get(num)
        if i is None:
            continue
        hw = content_words(h["arabic"])
        if len(hw) < 10:
            continue
        inter = len(hw & seg_sigs[i])
        if inter < 4 and inter < 0.15 * len(hw):
            suspects += 1
    print(f"number-mapping suspects (weak text): {suspects}")

    # fallback window alignment for the rest
    extra = window_align(hs, segs, seg_by_num)

    def commentary_text(s):
        text = "\n\n".join(p.strip() for p in s["commentary"] if p.strip())
        text = re.sub(r'^\[?[اال]حد[يبنث]+\s*[\d٠-٩]+[^\n]*\]?', '', text).strip()
        text = re.sub(r'\n\s*ــ\s*\n', '\n\n', text)
        return text.strip()

    entries = []
    have = set()
    for h in hs:
        num = h["idInBook"]
        i = direct.get(num, extra.get(num))
        if i is None:
            continue
        text = commentary_text(segs[i])
        if len(text) < 40:
            continue
        entries.append({"num": num, "sharh": text})
        have.add(num)
    print(f"entries with own commentary: {len(entries)}")

    # ---- Fill repeats/أطراف: hadiths whose Fath entry is empty or a bare
    # cross-reference borrow the commentary of their main occurrence — the
    # same hadith text carries the same scholarly commentary.
    # Source 1: the explicit "أطرافه في: M1، M2" cross-references in Fath.
    # Source 2: a relaxed global text match (same matn, different isnad).
    taraf_edges = {}  # N -> [M...] from "الحديث N - أطرافه في: M..."
    TARAF_RE = re.compile(r'(?:ال)?حد[يبنث]+\s*[\d٠-٩]+\s*[-–—:]*\s*(?:أطرافه|طرفاه|أطراف)(?:\s*في)?\s*[:،]?\s*([\d٠-٩،,\s]+)')
    for s in segs:
        blob = "\n".join([s.get("header", "")] + s["commentary"][:2])
        m = TARAF_RE.search(blob)
        n = s.get("hdr_num")
        if m and n is not None:
            nums = [int(x.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
                    for x in re.split(r'[،,\s]+', m.group(1).strip()) if x.strip()]
            if nums:
                taraf_edges.setdefault(n, []).extend(nums)

    def usable_text(i):
        return commentary_text(segs[i])

    usable = [i for i, s in enumerate(segs) if len(commentary_text(s)) >= 40]
    # quick lookup: hdr_num -> usable segment index (with commentary)
    num_to_usable = {}
    for i in usable:
        n = segs[i].get("hdr_num")
        if n is not None and n not in num_to_usable:
            num_to_usable[n] = i
    usable_sigs = [seg_sigs[i] for i in usable]
    # inverted index for speed
    inv = {}
    for j, sig in enumerate(usable_sigs):
        for w in sig:
            inv.setdefault(w, []).append(j)
    from collections import Counter
    filled = 0
    for h in hs:
        num = h["idInBook"]
        if num in have:
            continue
        got = None
        # 1) explicit أطراف edge
        partners = taraf_edges.get(num, [])
        for p in partners:
            if p in num_to_usable:
                got = num_to_usable[p]
                break
        if got is None:
            # reverse edge: num is listed as a طرف of some N with commentary
            for n_part, ms in taraf_edges.items():
                if num in ms and n_part in num_to_usable:
                    got = num_to_usable[n_part]
                    break
        if got is None:
            # 2) relaxed global text match
            hw = content_words(h["arabic"])
            if hw:
                cnt = Counter()
                for w in hw:
                    for j in inv.get(w, ()):
                        cnt[j] += 1
                if cnt:
                    j, score = cnt.most_common(1)[0]
                    if (score >= 8 and score >= 0.35 * len(hw)) or \
                       (score >= 15 and score >= 0.25 * len(hw)):
                        got = usable[j]
        if got is not None and len(commentary_text(segs[got])) >= 40:
            entries.append({"num": num, "sharh": commentary_text(segs[got])})
            have.add(num)
            filled += 1
    print(f"repeat-filled: {filled}")

    total_chars = sum(len(e["sharh"]) for e in entries)
    print(f"total entries: {len(entries)} | total commentary chars: {total_chars:,}")

    out = {
        "source": "فتح الباري شرح صحيح البخاري — الحافظ ابن حجر العسقلاني",
        "entries": entries,
    }
    with open(f"{BUILD}/sharh_bukhari.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"wrote {BUILD}/sharh_bukhari.json")

    # ---- spot checks ----
    seg_json = {e["num"]: e["sharh"] for e in entries}
    for n in (1, 8, 25, 138, 50, 960):
        t = seg_json.get(n)
        if t:
            print(f"\n=== #{n} ({len(t)} chars): {t[:220]}...")
        else:
            print(f"\n=== #{n}: NO ENTRY")

if __name__ == "__main__":
    main()
