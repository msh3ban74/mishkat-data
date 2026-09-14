# mishkat-data

Classical hadith commentary (sharh) packages for the Mishkat Android app,
extracted from the authoritative shamela.ws (al-Maktaba ash-Shamela)
digitizations and aligned hadith-by-hadith to the app's book numbering.

| File | Book | Sharh |
|------|------|-------|
| sharh_bukhari.json.gz | Sahih al-Bukhari | Fath al-Bari (Ibn Hajar) |
| sharh_muslim.json.gz | Sahih Muslim | Sharh an-Nawawi |
| sharh_abudawud.json.gz | Sunan Abi Dawud | Awn al-Mabud |
| sharh_tirmidhi.json.gz | Jami' at-Tirmidhi | Tuhfat al-Ahwadhi |
| sharh_nasai.json.gz | Sunan an-Nasa'i | Hashiyat as-Sindi |
| sharh_ibnmajah.json.gz | Sunan Ibn Majah | Hashiyat as-Sindi |
| sharh_malik.json.gz | Muwatta Malik | Sharh az-Zarqani |
| sharh_bulugh_almaram.json.gz | Bulugh al-Maram | Subul as-Salam |

Format: gzip-compressed JSON `{"source": "...", "entries": [{"num": <app idInBook>, "sharh": "..."}]}`.
The build tooling lives in tools/ (also mirrored in the app repository).
