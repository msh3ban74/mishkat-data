#!/usr/bin/env python3
"""
Shared parsing utilities for the shamela sharh extraction pipeline.

A shamela text page (shamela.ws/book/<id>/<page>) contains a <div class="nass">
with <p> paragraphs. Inside paragraphs, <span class="c2"> marks quoted hadith
text, <span class="c4"> marks structural headers ([N] hadith numbers, [باب..]
chapters), <span class="c5"> marks commentary lead-ins (قوله:...), and
<span class="special"> marks the ﷺ ligature.

parse_page() returns a list of paragraphs, each:
  {"runs": [(class, text), ...], "text": str}
"""
import re, html, os, json

CACHE = "/home/z/my-project/sharh_cache"

NASS_RE = re.compile(r'<div class="nass[^"]*"[^>]*>(.*?)</div>\s*(?:<div|<section|<!--)', re.S)
# fallback: to end of file if the closing structure differs
P_RE = re.compile(r'<p>(.*?)</p>', re.S)
SPAN_RE = re.compile(r'<span class="(c\d+|special|anchor)"[^>]*>(.*?)</span>', re.S)
TAG_RE = re.compile(r'<[^>]+>')

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def norm_num(s: str) -> str:
    return s.translate(AR_DIGITS)

def clean_text(s: str) -> str:
    s = TAG_RE.sub('', s)
    s = html.unescape(s)
    s = s.replace('\u200f', '').replace('\u200e', '').replace('\u00ad', '')
    return s.strip()

def parse_page(path: str):
    """Returns list of paragraphs: [{"runs":[(cls,txt)], "text": txt}] or None."""
    try:
        c = open(path, encoding='utf-8', errors='ignore').read()
    except Exception:
        return None
    if 'Just a moment' in c[:3000]:
        return None
    m = NASS_RE.search(c)
    raw = m.group(1) if m else None
    if raw is None:
        # try simpler cut
        m2 = re.search(r'<div class="nass[^"]*"[^>]*>(.*)', c, re.S)
        if not m2:
            return []
        raw = m2.group(1).split('</section>')[0]
    paras = []
    for pm in P_RE.finditer(raw):
        body = pm.group(1)
        runs = []
        # walk spans; text outside spans gets class ''
        pos = 0
        for sm in SPAN_RE.finditer(body):
            if sm.start() > pos:
                t = clean_text(body[pos:sm.start()])
                if t:
                    runs.append(('', t))
            cls = 'special' if sm.group(1) in ('special', 'anchor') else sm.group(1)
            # anchors are empty; skip their text contribution
            if sm.group(1) == 'anchor':
                t = clean_text(sm.group(2))
                if t:
                    runs.append(('', t))
                pos = sm.end()
                continue
            t = clean_text(sm.group(2))
            if t:
                runs.append((cls, t))
            pos = sm.end()
        if pos < len(body):
            t = clean_text(body[pos:])
            if t:
                runs.append(('', t))
        text = ''.join(t for _, t in runs)
        # drop the trailing copy-button artifacts
        text = text.replace('', '').strip()
        if not text:
            continue
        paras.append({"runs": runs, "text": text})
    return paras

def load_book(book_id: int, page_from: int, page_to: int):
    """Loads all cached pages in range, concatenated in order."""
    doc = []
    for p in range(page_from, page_to + 1):
        path = os.path.join(CACHE, str(book_id), f"{p}.html")
        if not os.path.exists(path):
            continue
        paras = parse_page(path)
        if paras is None:
            continue
        for para in paras:
            para["page"] = p
        doc.extend(paras)
    return doc

# ---------------- Arabic normalization (matches the app's) ----------------

DIACRITICS = re.compile(r'[\u0610-\u061A\u064B-\u065F\u06D6-\u06ED\u0640\u0670]')

def normalize(s: str) -> str:
    s = s.translate(AR_DIGITS)
    s = DIACRITICS.sub('', s)
    s = (s.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ٱ', 'ا')
          .replace('ى', 'ي').replace('ة', 'ه')
          .replace('ؤ', 'و').replace('ئ', 'ي').replace('ء', ''))
    s = re.sub(r'[^\u0600-\u06FF0-9A-Za-z ]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

STOP = set("""حدثنا حدثني أخبرنا أخبرني أنبأنا نبأنا سمعت عن قال قالت يقول عليه وسلم صلى
رسول الله النبي رسوله قالوا قيل ذكر أول ثم كان يكون قد لا ما في من علي الي مع او
حتي كل هذا هذه ذلك الذي التي الذين هو هي هم انا انت نحن بن ابن بنت ابو ابي ام فقال فحدثنا
فأخبرنا لقد يا ايها انه انها مما الذي رضي سلامه صلاته
""".split())
STOP = set(normalize(x) for x in STOP if x.strip())

def content_words(text: str, min_len=4):
    n = normalize(text)
    ws = [w for w in n.split() if len(w) >= min_len and w not in STOP]
    return set(ws)

if __name__ == '__main__':
    import sys
    bid, pg = int(sys.argv[1]), int(sys.argv[2])
    paras = parse_page(os.path.join(CACHE, str(bid), f"{pg}.html"))
    if paras is None:
        print("CHALLENGE/missing")
    else:
        for i, p in enumerate(paras[:10]):
            print(f"[{i}] {p['text'][:120]}")
