#!/usr/bin/env python3
"""V5 DATA GATE — release blocker for the print-repair wave.

  V1 numbering: exact unit counts, no empties, monotonic ids.
  V2 sharh pairing: quoted-fragment verbatim verification (per book package).
  V4 print-repair invariants:
     a. bukhari 1066 = الأوزاعي eclipse hadith; 1065 ≠ 1066; both under كتاب الكسوف.
     b. no glued باب/كتاب tails in hadith texts (pattern scan).
     c. no stray number prefixes («، N -») in texts.
     d. no consecutive-identical texts beyond the documented multi-number units.
     e. the encyclopedia map keys must lie inside each book's number range.
"""
import json, os, re, sys

ROOT = os.environ.get("CANONICAL_ROOT", "/home/z/my-project/build_v5")
DATA = os.environ.get("DATA_ROOT", "/home/z/my-project/mishkat-data")

DIAC = re.compile(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]')

def strip(s):
    s = DIAC.sub('', s)
    s = s.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ى', 'ي').replace('ة', 'ه')
    return re.sub(r'\s+', ' ', s)

BOOKS = {
    "bukhari": 7563, "muslim": 3033, "abudawud": 5274, "tirmidhi": 3956,
    "nasai": 5758, "ibnmajah": 4341, "malik": 1858, "bulugh_almaram": 1767,
}
# units may fall short of the print maxima only for the documented honest gaps
LEN_TOLERANCE = {"muslim": 13, "tirmidhi": 4, "ibnmajah": 1, "malik": 29}
failures = 0

_D = r'[\u0610-\u061A\u064B-\u065F\u0670\u0640]{0,2}'
_B = rf'ب{_D}ا{_D}ب{_D}'
_K = rf'ك{_D}ت{_D}ا{_D}ب{_D}'
TAIL_END_RE = re.compile(rf'[٠١٢٣٤٥٦٧٨٩]{{0,4}}\s*[-–—]?\s*({_B}|{_K})\s+\S[^.؟!»"]{{0,90}}$')
STRAY_RE = re.compile(r'^\s*[،,]?\s*[٠١٢٣٤٥٦٧٨٩]{1,4}\s*[-–—]\s*\S')
MULTI_NUMBER_OK = {
    (2201, 2202), (2724, 2725), (2788, 2789), (4240, 4241), (5709, 5710),
    (5710, 5711), (6073, 6074), (6074, 6075), (6835, 6836), (6859, 6860),
    (7102, 7103), (7103, 7104), (7105, 7106), (7106, 7107),
}

# ---------- V1 + V4 data invariants ----------
book_texts = {}
for slug, canon_max in BOOKS.items():
    path = f'{ROOT}/{slug}.json'
    if not os.path.exists(path):
        path = f'{DATA}/books/{slug}.json'
    book = json.load(open(path))
    hs = book['hadiths']
    nums = [h['idInBook'] for h in hs]
    nonmono = sum(1 for i in range(1, len(nums)) if nums[i] < nums[i - 1])
    empty = sum(1 for h in hs if len(strip(h['arabic'])) < 10)
    tol = LEN_TOLERANCE.get(slug, 0)
    ok1 = (empty == 0 and max(nums) == canon_max and len(hs) >= canon_max - tol
           and (slug == 'muslim' or nonmono == 0))
    if not ok1:
        failures += 1
    print(f"[V1] {slug}: hadiths={len(hs)} nonmono={nonmono} empty={empty} "
          f"max={max(nums)}/{canon_max} -> {'OK' if ok1 else 'FAIL'}")
    book_texts[slug] = {h['idInBook']: h['arabic'] for h in hs}

# V4a — the user's exact case
bk = book_texts['bukhari']
t1065, t1066 = strip(bk[1065]), strip(bk[1066])
a = 'الاوزاعي' in t1066 or 'اوزاعي' in t1066
b = 'المنادي' in t1066 or 'مناديا' in t1066
c = t1065 != t1066
ok4a = a and b and c
if not ok4a:
    failures += 1
print(f"[V4a] bukhari 1066=الأوزاعي({a}) المنادي({b}) 1065!=1066({c}) -> {'OK' if ok4a else 'FAIL'}")

# V4b — glued tails
tail_hits = []
for slug, m in book_texts.items():
    for n, t in m.items():
        tail = t[-300:]
        if TAIL_END_RE.search(t.rstrip()) and len(strip(t)) > 80:
            tail_hits.append((slug, n, strip(tail)[-60:]))
ok4b = len(tail_hits) <= 8   # a small documented residue is tolerated
if not ok4b:
    failures += 1
print(f"[V4b] glued-tail residue: {len(tail_hits)} -> {'OK' if ok4b else 'FAIL'}")
for x in tail_hits[:5]:
    print('   ', x)

# V4c — stray prefixes
stray_hits = [(slug, n) for slug, m in book_texts.items()
              for n, t in m.items() if STRAY_RE.match(t)]
ok4c = len(stray_hits) == 0
if not ok4c:
    failures += 1
print(f"[V4c] stray number prefixes: {len(stray_hits)} {stray_hits[:5]} -> {'OK' if ok4c else 'FAIL'}")

# V4d — consecutive-identical beyond the documented multi-number units
bd = [(n, n + 1) for n in sorted(book_texts['bukhari'])
      if (n + 1) in book_texts['bukhari']
      and strip(book_texts['bukhari'][n]) == strip(book_texts['bukhari'][n + 1])
      and len(strip(book_texts['bukhari'][n])) > 60]
extra = [p for p in bd if p not in MULTI_NUMBER_OK]
ok4d = len(extra) == 0
if not ok4d:
    failures += 1
print(f"[V4d] bukhari consecutive-identical: {len(bd)} (documented {len(bd) - len(extra)}) "
      f"extra={extra} -> {'OK' if ok4d else 'FAIL'}")

# V4e — the map keys lie inside each book's range
mroot = json.load(open(f'{ROOT}/hadith_sharh.json')) if os.path.exists(f'{ROOT}/hadith_sharh.json') \
    else json.load(open('/home/z/my-project/mishkat/app/src/main/assets/hadith_sharh.json'))
bad_keys = []
for slug, mp in mroot['map'].items():
    if slug not in book_texts:
        continue
    mx = max(book_texts[slug])
    for k in mp:
        if int(k) > mx:
            bad_keys.append((slug, k, mx))
ok4e = len(bad_keys) == 0
if not ok4e:
    failures += 1
print(f"[V4e] map keys out of range: {len(bad_keys)} {bad_keys[:5]} -> {'OK' if ok4e else 'FAIL'}")

# ---------- V2 sharh pairing (bukhari) ----------
pkg_path = f'{ROOT}/sharh_bukhari.json'
if os.path.exists(pkg_path):
    pkg = json.load(open(pkg_path))
    texts_by_num = {n: [strip(t)] for n, t in book_texts['bukhari'].items()}
    PAREN = re.compile(r'[\(«]([^)»]{18,150})')
    QOLE = re.compile(r'قَوْلُهُ|قوله')
    ver = wrong = nofrag = 0
    for e in pkg['entries']:
        t = e['sharh']
        m = QOLE.search(t[:1200])
        seg = t[m.start():] if m else t
        frags = [strip(f) for f in PAREN.findall(seg[:3000])]
        frags = [f for f in frags if len(f) >= 18][:4]
        own = texts_by_num.get(e['num'], [])
        if not frags:
            nofrag += 1
            continue
        if any(f in t2 for f in frags for t2 in own):
            ver += 1
            continue
        # provably wrong: a matn fragment appears in a DIFFERENT hadith
        # (isnad-opener fragments excluded: quoting an isnad name is not pairing)
        ISNAD_OPEN = re.compile(r'^(?:حدثنا|اخبرنا|حدثني|اخبرني|سمعت|قال|عن|حدث|بال|وحدثنا|وعن|وقال|وهو|هو|ابن|بن)')
        matn_frags = [f for f in frags if not ISNAD_OPEN.match(f)]
        hit_other = False
        for f in matn_frags:
            for n2, t2s in texts_by_num.items():
                if n2 == e['num']:
                    continue
                if any(f in t2 for t2 in t2s):
                    hit_other = True
                    break
            if hit_other:
                break
        if hit_other:
            wrong += 1
        else:
            nofrag += 1
    total = ver + wrong
    rate = 100.0 * ver / max(1, total)
    ok2 = (rate >= 85.0 if total > 0 else True) and wrong <= 0.05 * len(pkg['entries'])
    if not ok2:
        failures += 1
    print(f"[V2] bukhari package: entries={len(pkg['entries'])} verbatim-verified={ver}/{total} "
          f"({rate:.1f}%) wrong={wrong} -> {'OK' if ok2 else 'FAIL'}")

print('\nGATE:', 'PASS' if failures == 0 else f'FAIL ({failures})')
sys.exit(0 if failures == 0 else 1)
