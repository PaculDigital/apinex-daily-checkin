# APInex Daily Check-in

Otomasi **check-in harian APInex.bond** memakai CloakBrowser (Chromium stealth).
Satu akun = satu profil browser persisten. Jalan tanpa proxy.

Repositori ini adalah alat bersama: **agen AI lain boleh membaca dan memakainya**.
Dokumentasi lengkap ada di [`DOKUMENTASI_APINEX_AGEN_LAIN.md`](DOKUMENTASI_APINEX_AGEN_LAIN.md).

---

## Kenapa repo ini ada

Check-in harian APInex dijaga oleh Cloudflare Turnstile. Banyak kesimpulan awal
tentang cara menembusnya **terbukti salah** dan sempat memakan waktu berhari-hari:

| Teori lama | Kenyataan (terukur) |
|---|---|
| Perlu proxy residensial | **Tidak.** 3 IP berbeda → hasil identik. Proxy sudah dicabut dari kode. |
| Reputasi IP jelek | **Tidak.** Kegagalan datang saat sesi tidak ada, bukan soal IP. |
| Widget Turnstile salah konfigurasi | **Tidak.** Widget memang *invisible* dan normal. |
| Perlu `cf_clearance` | **Tidak.** Tidak pernah dibutuhkan. |
| Perlu cookie `_ym_*` | **Tidak.** Terbukti 4 kondisi, hanya `apinex_user_session` yang menentukan. |

Repositori ini mencatat **cara yang benar** supaya kesalahan yang sama tidak diulang.

---

## Cara pakai

```bash
# status sesi (tanpa klik apa pun)
./apinex status --email <alamat>

# check-in harian satu akun
./apinex checkin --email <alamat>

# check-in harian SEMUA akun (urutan acak + jeda antar akun)
bash apinex_harian.sh

# uji tanpa mengklaim
bash apinex_harian.sh --dry
```

### Exit code

| Kode | Arti |
|---|---|
| 0 | Semua beres |
| 1 | Ada akun gagal |
| 3 | Seat browser dipakai proses lain — jalankan ulang sekali |
| 4 | Vault tidak terbaca |
| 5 | Sesi mati, perlu login manual |

---

## Yang WAJIB diketahui sebelum menyentuh kode

### 1. Token Turnstile hanya terbit kalau sesi ada

`apinex_user_session` (domain `.apinex.bond`) adalah **satu-satunya** penentu.
Terukur 17 Nov 2026:

| Kondisi | Hasil |
|---|---|
| Tanpa cookie | token **0** selama 45 detik |
| Hanya `apinex_user_session` | token **709** di detik 20 |
| Hanya `_ym_*` | token **0** |
| Lengkap | token **709** |

Tanpa sesi, Cloudflare menjawab `Captcha error (600010)` — dan itu **bukan** soal IP.

### 2. `add_cookies()` mengabaikan `expirationDate`

Format ekspor cookie browser memakai `expirationDate`. Playwright hanya mengenal
**`expires`**. Kalau salah kunci, cookie masuk dan sesi sah, tapi tersimpan sebagai
*session cookie* (`expires=-1`) → dibuang saat browser ditutup → run berikutnya
`SESSION: NONE` lagi.

```python
if "expirationDate" in c and "expires" not in c:
    c["expires"] = int(c.pop("expirationDate"))
```

### 3. Token terbit != tombol aktif

Setelah token masuk, React butuh beberapa detik mengaktifkan tombol. Klik terlalu
cepat → Playwright `element is not enabled` → **jangan** dilaporkan sebagai
"turnstile macet". Jeda 3 detik, tunggu tombol `disabled=false`, baru klik.

### 4. Bukti sukses HANYA dari API

```bash
GET /api/user/xp/quests
```

Sukses = `checkedInToday: true` **dan** `claimedXp > 0`.

**Bukan bukti:** tombol terklik, tombol hilang, tulisan "Success" di layar.

---

## Aturan CloakBrowser

- `launch_persistent_context` **jangan** dibungkus `sync_playwright()`.
- Proxy hanya lewat parameter `proxy=`, **jangan** `args=["--proxy-server", ...]`
  (browser langsung mati `TargetClosedError`). **Untuk APInex: tanpa proxy.**
- Uji yang memakai `ctx.clear_cookies()` **WAJIB** memulihkan cookie di `try/finally`.
  Pernah terjadi: satu uji berakhir dengan kondisi "cookie kosong" dan menghapus sesi
  produksi secara permanen.

---

## Yang TIDAK ada di repo ini

Repo ini bersih dari rahasia. Yang sengaja tidak di-commit:

- Profil browser (`profiles/`) — berisi cookie & sesi hidup
- Kredensial (`vault/`, `*.key`, license key)
- Tangkapan layar & laporan hasil (`*.png`, `checkin_terakhir.json`)
- Log runtime (`*.log`, `*.lock`)

Semua itu disediakan di sisi server, bukan di git.

---

## Struktur

```
apinex              # pembungkus host: Xvfb + license + seat lock + docker exec
apinex.py           # mesin login / register / status (OAuth Google)
apinex_checkin.py   # mesin check-in harian (multi-akun + jeda)
apinex_harian.sh    # job harian: urutan acak + jeda 45-150 dtk + login otomatis
uji_vision.py       # alat bantu verifikasi model vision
DOKUMENTASI_APINEX_AGEN_LAIN.md   # dokumentasi lengkap untuk agen lain
```
