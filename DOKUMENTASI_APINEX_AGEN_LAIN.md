# Dokumentasi alat bersama: akses APInex.bond (register / login / sesi / CHECK-IN HARIAN)

**Pemilik**: Bos (Pacul TW) · **Dibuat**: 16 Nov 2026 · **Diuji ulang**: 16 Nov 2026 (7 skenario lulus)
**Alat**: `/opt/data/services/apinex-run/apinex` (pembungkus host) · `apinex.py` (login/register) · `apinex_checkin.py` (check-in harian)
**Skill pendamping**: `apinex-google-oauth-farm` (muat dengan `skill_view` sebelum kerja)

---

## 1. Apa ini

Tiga kemampuan dalam satu pembungkus:

1. **Login/register** ke `apinex.bond` memakai akun Google, sesi disimpan di profil browser persisten.
2. **Check-in harian** (klaim reward harian: **+25 juta token gratis & +40 XP**, terbukti 17 Nov 2026) untuk satu atau banyak akun, dengan jeda natural antar akun.
3. **Baca status** akun tanpa membuka interaksi.

Agen lain cukup memakai sesi yang sudah ada — **tidak perlu** menyentuh kredensial.

**Satu akun = satu folder profil.** Akun berbeda tidak saling menimpa sesi di Google.

---

## 2. Batas keras yang WAJIB dipatuhi agen lain

| Batas | Kenapa |
|---|---|
| **CloakBrowser Pro = 1 SEAT** | Hanya satu proses browser boleh hidup. Dua proses = `session limit reached`, seat terkunci 4–30 menit. Script sudah pakai lockfile otomatis. |
| **JANGAN paralelkan check-in** | 5 akun dijalankan BERGILIRAN. Menjalankan 2 proses `checkin` bersamaan = seat bentrok. Skrip sudah menolak lewat lock (exit 3). |
| **Jangan hapus / edit folder profil** | `vault/profiles/apinex_<user>` memuat cookie sesi Google + `.cloakbrowser-seed`. Rusak = login ulang manual + identitas browser baru. |
| **Jangan `write_file` ke `vault/`** | Folder protected. Pakai terminal heredoc. |
| **Jangan cetak password ke log/chat** | Kredensial di `vault/google_personal.json` (chmod 600). Rujuk saja. |
| **Jangan `pkill chrome` global** | Bisa membunuh sesi agen lain. Pakai `pkill -f user-data-dir=/opt/data/vault/profiles/apinex_<user>`. |
| **Jangan pindahkan folder profil** | Path diturunkan dari email; pindah = sesi hilang. |

---

## 3. Cara pakai

### 3a. Paling gampang — pakai pembungkus host

```bash
cd /opt/data/services/apinex-run

./apinex status                          # cek sesi (headless)
./apinex login                           # login akun satu-satunya di vault
./apinex login    --email a@gmail.com    # login akun tertentu
./apinex register --email b@gmail.com    # daftar akun yang belum terdaftar

./apinex checkin                         # CHECK-IN semua akun di vault
./apinex checkin --email a@gmail.com     # check-in satu akun saja
./apinex checkin --dry                   # baca status saja, TIDAK mengklaim
./apinex checkin --jeda 30               # jeda tetap 30 detik antar akun
```

Pembungkus sudah mengurus Xvfb `:97`, license key, `docker exec`, dan timeout
(5 menit untuk login/status, 60 menit untuk check-in).

### 3b. Manual lewat docker exec

```bash
docker exec -e HOME=/tmp/cbhome2 \
  -e CLOAKBROWSER_LICENSE_KEY="$(cat /opt/data/home/.cloakbrowser/license.key)" \
  hermes bash -c '
    pgrep Xvfb >/dev/null || (Xvfb :97 -screen 0 1920x1080x24 >/tmp/xvfb97.log 2>&1 &)
    sleep 2
    DISPLAY=:97 timeout 3600 /opt/data/services/cloakbrowser/.venv/bin/python3 \
      /opt/data/services/apinex-run/apinex_checkin.py
  '
```

### Subcommand

| Perintah | Kapan dipakai | Keluaran sukses |
|---|---|---|
| `status` | Cek cepat sesi (headless, tanpa interaksi) | `SESSION: VALID` + `ALREADY_LOGGED_IN` |
| `login` | Sesi mati / mau login akun yang sudah ada | `ALREADY_LOGGED_IN` atau `FINAL_SESSION: VALID` |
| `register` | Daftar akun yang belum terdaftar | `FINAL_SESSION: VALID` |
| `checkin` | Klaim XP harian | `SUKSES` / `SUDAH` per akun |

`register` **aman diulang**: script cek dashboard dulu; kalau sesi sudah valid, ia berhenti
dengan `ALREADY_LOGGED_IN` dan tidak membuat akun kedua.

`checkin` **aman diulang**: kalau hari itu sudah diklaim, keluar `SUDAH` tanpa klik apa pun.

### Exit code (untuk otomasi)

| Code | Arti | Tindakan agen |
|---|---|---|
| `0` | Sukses semua | lanjut |
| `1` | Ada akun gagal check-in | baca `checkin_terakhir.json`, lapor. Jangan retry beruntun. |
| `2` | Sesi gagal terbentuk (login/register) | lapor ke Bos, jangan retry beruntun |
| `3` | Seat dipakai agen lain | tunggu, coba lagi nanti. **JANGAN paksa** |
| `4` | Email belum ada di vault | tambahkan kredensial dulu (§4) |
| `5` | Ada akun yang sesinya mati | jalankan `./apinex login --email <email>` dulu |

### Variabel lingkungan

| Variabel | Bawaan | Fungsi |
|---|---|---|
| `APINEX_EMAIL` | akun pertama di vault | Akun yang dipakai kalau `--email` tidak diberi |
| `APINEX_PROFILE` | otomatis `vault/profiles/apinex_<user>` | Timpa folder profil (jarang perlu) |
| `APINEX_PROFILE_BASE` | `/opt/data/vault/profiles` | Induk folder profil |
| `APINEX_VAULT` | `/opt/data/vault/google_personal.json` | Daftar kredensial |
| `APINEX_SHOTS` | `/opt/data/services/apinex-run` | Tujuan tangkapan layar bukti |
| `APINEX_LOCK` | `.apinex-browser.lock` di folder script | Lockfile seat |
| `APINEX_JEDA_MIN` | `45` | Jeda minimum antar akun (detik) |
| `APINEX_JEDA_MAX` | `150` | Jeda maksimum antar akun (detik) |
| `APINEX_TURNSTILE_TIMEOUT` | `45` | Batas tunggu token Turnstile per akun |
| `APINEX_HASIL` | `checkin_terakhir.json` | Lokasi laporan JSON |

---

## 4. Mendaftarkan akun BARU (alur lengkap)

Script hanya bisa login/daftar untuk email yang **kredensialnya ada di vault**.

1. **Siapkan Gmail personal** — harus `@gmail.com`; Workspace/custom domain ditolak situs.
2. **Tambahkan ke vault**:
   ```bash
   python3 - <<'EOF'
   import json, os
   p = "/opt/data/vault/google_personal.json"
   d = json.load(open(p))
   d.append({"email": "akunbaru@gmail.com", "password": "ISI_PASSWORD",
             "type": "google", "note": ""})
   json.dump(d, open(p, "w"), indent=2)
   os.chmod(p, 0o600)
   EOF
   ```
3. **Jalankan**:
   ```bash
   /opt/data/services/apinex-run/apinex register --email akunbaru@gmail.com
   ```
4. **Verifikasi**: `FINAL_SESSION: VALID` + tangkapan layar
   `/opt/data/services/apinex-run/step_<user>.png`. Body dashboard harus memuat
   `API Keys` dan `Balance:`.

Profil browser dibuat otomatis di `/opt/data/vault/profiles/apinex_<user>` (titik pada
email diganti `_`).

**Ditangani otomatis oleh script**: account chooser Google → input email → reCAPTCHA
Enterprise (biasanya lolos sendiri karena CloakBrowser stealth) → password → consent
"Lanjutkan". Tidak perlu 2Captcha.

Kalau Google meminta verifikasi tambahan (kode SMS, "verifikasi ini kamu"), script berhenti
`FINAL_SESSION: FAILED` — laporkan ke Bos; jangan diulang terus.

---

## 5. CHECK-IN HARIAN (fitur utama)

### 5a. Apa yang terjadi di dalam

```
buka /overview          -> pastikan sesi masih VALID (API Keys + Balance:)
GET  /api/user/xp/quests -> baca canClaim / checkedInToday / currentStreak
   |- checkedInToday true  -> selesai, status "SUDAH" (tidak klik apa pun)
   |- canClaim false       -> selesai, status "SUDAH"
   '- canClaim true        -> lanjut klaim:
        buka /airdrop
        tutup popup promo ("Maybe later") kalau menutupi layar
        klik "Claim check-in"        -> modal DAILY CHECK-IN terbuka
        tunggu token Turnstile        (SYARAT MUTLAK: cookie apinex_user_session
                                       harus ada di profil — lihat §5f. Widget-nya
                                       INVISIBLE: tidak ada checkbox, tidak ada iframe
                                       yang bisa diklik. Cukup TUNGGU, token terbit
                                       sendiri ~20-23 detik.)
        klik "Check in & continue"    (disabled sampai token terbit — itu NORMAL)
        GET /api/user/xp/quests lagi  -> verifikasi checkedInToday true
        simpan tangkapan layar bukti
tutup browser (ctx.close) -> seat bebas untuk akun berikutnya
jeda acak 45-150 detik
akun berikutnya
```

### 5f. KENAPA TOKEN TURNSTILE TERBIT (atau tidak) — TERUKUR 17 Nov 2026

Ini akar masalah yang paling sering bikin agen buang waktu berjam-jam. **Bukan** IP,
**bukan** proxy, **bukan** fingerprint, **bukan** `cf_clearance`.

**Satu-satunya syarat: cookie `apinex_user_session` (domain `.apinex.bond`) harus ada
di profil browser.**

Uji pemisahan di **akun kedua** (profil sama, 4 kondisi berurutan):

| Kondisi | Cookie yang disuntik | Token Turnstile | Waktu |
|---|---|---|---|
| A | **tidak ada** (semua dibersihkan) | **0** (gagal) | 45 s habis |
| B | **hanya `apinex_user_session`** | **709 char** ✓ | 20 s |
| C | hanya `_ym_isad` + `_ym_d` + `_ym_uid` | **0** (gagal) | 45 s habis |
| D | `apinex_user_session` + `_ym_*` | **709 char** ✓ | 23 s |

Kesimpulan yang berlaku:

1. **`_ym_*` (Yandex Metrica) TIDAK diperlukan.** Kondisi C membuktikan tanpa sesi,
   `_ym_*` tidak menolong sama sekali. Kondisi D malah **3 detik lebih lambat** dari B.
2. **Tanpa sesi, token TIDAK AKAN PERNAH terbit** — ditunggu berapa lama pun.
   Naikkan `APINEX_TURNSTILE_TIMEOUT` **tidak menolong**.
3. **Widget-nya INVISIBLE.** DOM hanya punya `<input type="hidden"
   name="cf-turnstile-response">`. **Tidak ada checkbox, tidak ada iframe.** Jangan
   coba klik koordinat, jangan cari `input[type=checkbox]` — semua akan `TimeoutError`.
4. **Jangan buang waktu di IP/proxy/fingerprint.** Sudah diukur: 3 IP berbeda
   (Telkomsel 182.8.179.28, Jakarta 103.76.108.29, VPS langsung 103.186.30.230)
   menghasilkan `600010` yang sama saat sesi tidak ada. Fingerprint juga bersih
   (Win32, `webdriver=false`, WebGL RTX 3060 Ti, `Asia/Jakarta`).

### 5g. Kalau token tetap tidak terbit

Urutannya begini — jangan lompat ke proxy/IP:

1. **Cek cookie dulu.** `apinex_user_session` ada di profil? Kalau tidak ada → sesi
   mati, jalankan `./apinex login --email <email>`.
2. **Kalau ada tapi tetap gagal** → sesinya kedaluwarsa di sisi server. Login ulang.
3. **Baru setelah itu** curigai hal lain. Dan kalau mencurigai, **ukur** — jangan
   langsung ganti proxy.

Cara memastikan cepat tanpa buka browser: baca cookie dari profil (SQLite, di dalam
container karena folder profil milik root)

```bash
docker exec hermes python3 -c "
import sqlite3
p='/opt/data/vault/profiles/apinex_<user>/Default/Cookies'
con=sqlite3.connect('file:'+p+'?mode=ro', uri=True)
for n,l in con.execute(\"select name,length(encrypted_value) from cookies where host_key like '%apinex%'\"):
    print(n,l)
"
```

Kalau `apinex_user_session` muncul → sesi ada. Kalau tidak → login dulu.


### 5b. Kenapa ada JEDA antar akun

Seat CloakBrowser Pro **hanya 1**, jadi akun memang harus bergiliran. Tapi jeda bukan cuma
soal teknis — ini soal **pola kunjungan terlihat natural**:

- Tanpa jeda: 5 akun check-in dalam 15 detik dari IP yang sama = pola bot yang kentara.
- Dengan jeda: kunjungan tersebar 4–12 menit, seperti orang membuka dashboard pagi hari.
- Jeda **acak** (bawaan 45–150 detik), bukan angka tetap yang berulang.
- Jeda **tidak** dipakai setelah akun terakhir (tidak ada gunanya menunggu di akhir).

Atur sendiri kalau perlu:
```bash
./apinex checkin --jeda 30          # tetap 30 detik (untuk uji cepat)
APINEX_JEDA_MIN=60 APINEX_JEDA_MAX=240 ./apinex checkin   # lebih longgar
```

### 5c. Waktu reset & jadwal yang disarankan

- Reset harian: **00:00 UTC = 07:00 WIB** (yang terbaca di situs `DAILY CHECK-IN UTC`).
- Jadwal yang disarankan: **07:05 WIB**, atau lebih baik **acak 07:00–09:00 WIB** agar tidak
  selalu jam yang sama persis.
- **Streak putus 1 hari = balik ke Day 1.** Jangan lewatkan hari.

### 5d. Membaca hasilnya

Ringkasan di stdout:
```
RINGKASAN CHECK-IN
SUKSES       a@gmail.com    streak=2 xp=30
SUDAH        b@gmail.com    sudah check-in hari ini
BELUM_LOGIN  c@gmail.com    sesi mati — jalankan apinex login --email c@gmail.com
GAGAL        d@gmail.com    token Turnstile tidak terbit dalam 45s

BERHASIL: 2/4
PERLU LOGIN: c@gmail.com
GAGAL: d@gmail.com
```

Laporan mesin: `/opt/data/services/apinex-run/checkin_terakhir.json`
```json
{
  "dijalankan": "2026-11-16T04:30:03+00:00",
  "dry": false,
  "hasil": [
    {"email": "a@gmail.com", "akun_ke": "1/2", "status": "SUKSES",
     "catatan": "streak=2 xp=30",
     "sebelum": {"canClaim": true, "checkedInToday": false, "currentStreak": 1, "day": 2},
     "sesudah": {"checkedInToday": true, "currentStreak": 2, "day": 2},
     "bukti": "/opt/data/services/apinex-run/checkin_a.png"}
  ]
}
```

Status yang mungkin muncul:

| Status | Arti | Tindakan agen |
|---|---|---|
| `SUKSES` | Baru diklaim hari ini | — |
| `SUDAH` | Sudah diklaim sebelumnya | — |
| `SIAP` | `--dry` + bisa diklaim | jalankan tanpa `--dry` |
| `BELUM_LOGIN` | Sesi mati / profil belum ada | `./apinex login --email X` |
| `GAGAL` | Klaim gagal (baca `catatan`) | lapor, jangan retry beruntun |

### 5e. Kalau mau pakai di skrip sendiri (tanpa pembungkus)

```python
import subprocess
r = subprocess.run(
    ["/opt/data/services/apinex-run/apinex", "checkin", "--email", "a@gmail.com"],
    capture_output=True, text=True, timeout=3600)
if r.returncode == 0:
    print("check-in beres")
elif r.returncode == 3:
    print("seat dipakai agen lain — tunggu")
elif r.returncode == 5:
    print("sesi mati — perlu apinex login")
```

**Jangan** memanggil `apinex_checkin.py` langsung tanpa lock. Pembungkus + lockfile yang
menjamin tidak ada dua browser hidup bersamaan.

---

## 6. Memakai SESINYA untuk tugas lain (bukan login)

Untuk baca/tulis di APInex (buat API key, cek saldo, ambil data dashboard), agen lain tetap
harus memakai CloakBrowser karena sesi hidup sebagai cookie di profil. Tidak ada token HTTP
terpisah di luar browser.

```python
from cloakbrowser import launch_persistent_context
import time

PROFILE = "/opt/data/vault/profiles/apinex_paculdigital02"   # folder SAMA, jangan disalin

ctx = launch_persistent_context(PROFILE, headless=False, humanize=True,
                                locale="en-US", timezone="Asia/Jakarta")
try:
    p = ctx.new_page()
    p.goto("https://apinex.bond/overview", wait_until="domcontentloaded")
    time.sleep(5)
    body = p.evaluate("() => document.body.innerText.slice(0,600)")
    if "API Keys" not in body or "Balance:" not in body:
        raise SystemExit("SESI_MATI: jalankan apinex login dulu")
    # ... kerjaan agen di sini ...
finally:
    ctx.close()      # WAJIB — lupa = seat terkunci, agen lain gagal
```

Aturan: **selesaikan urusan dalam satu sesi**. Jangan buka-tutup browser berulang.

---

## 7. Antrean antar agen

`apinex.py` dan `apinex_checkin.py` sudah mengambil lock otomatis (`flock` pada
`/opt/data/services/apinex-run/.apinex-browser.lock`, exit 3 kalau dipakai). Kalau agen
lain menulis skrip sendiri, tiru pola ini:

```bash
LOCK=/opt/data/services/apinex-run/.apinex-browser.lock
exec 9>"$LOCK"
flock -w 600 9 || { echo "FAIL_SEAT_DIPAKAI"; exit 3; }
# ... kerjaan ...
flock -u 9
```

Kalau lock gagal: **jangan** paksa, jangan bunuh proses orang lain. Lapor ke Bos.

---

## 8. Jebakan yang sudah memakan korban

| Gejala | Sebab | Tindakan |
|---|---|---|
| `FAIL_SEAT_DIPAKAI` (exit 3) | Seat dipegang proses lain | Tunggu; cek `pgrep -f user-data-dir=/opt/data/vault/profiles/apinex` |
| `session limit reached` | Seat dipegang proses mati | Tunggu 4–30 menit. Jangan retry beruntun. |
| `token Turnstile tidak terbit` | **Cookie `apinex_user_session` TIDAK ADA / kedaluwarsa di profil** — BUKAN Cloudflare lambat. Terukur 17 Nov 2026: tanpa cookie → token 0 selama 45 s; dengan cookie → token 709 dalam 20 s. | Cek cookie dulu (§5g). Kalau tidak ada → `./apinex login --email X`. **JANGAN** naikkan timeout, **JANGAN** ganti proxy — dua-duanya terbukti tidak menolong. |
| `Captcha error (600010)` | Muncul saat sesi tidak sah — Cloudflare menolak menerbitkan token. | Sama: benahi sesi. Sudah diuji di 3 IP berbeda (Telkomsel, Jakarta, VPS langsung) → `600010` identik. Jadi **bukan** soal IP. |
| Tombol **Check in & continue** abu-abu | Token Turnstile belum siap | **NORMAL.** Tunggu ~20-23 detik; skrip sudah menunggu sampai aktif. |
| `SESSION: NONE` padahal cookie baru disuntik, lalu sesi jalan sekali lalu mati lagi | **`add_cookies()` mengabaikan kunci `expirationDate`.** Playwright hanya mengenal **`expires`**. Cookie masuk dan sesi sah (`/api/user/me` 200), tapi tersimpan sebagai *session cookie* (`expires=-1`) → dibuang saat browser ditutup (terukur 17 Nov 2026 via CDP `Network.getCookies`: `expires=-1` untuk akun 2). | Konversi dulu: `c["expires"] = int(c.pop("expirationDate"))`. Setelah diperbaiki → `expires=1829450446`, bertahan 2 siklus buka-tutup. |
| Membaca `Default/Cookies` saat browser terbuka → cookie "TIDAK ADA" | **Chromium baru menulis DB profil saat `ctx.close()`.** DB yang dibaca di tengah sesi selalu tampak kosong. | Jangan simpulkan dari DB saat sesi berjalan. Verifikasi lewat CDP `Network.getCookies`; untuk uji persistensi, tutup context dulu (minimal 2 siklus buka-tutup). |
| `TOMBOL_MACET` walau token 709 char terbit | **React butuh beberapa detik** mengaktifkan tombol setelah token masuk. Klik terlalu cepat → Playwright `element is not enabled`. Dulu salah dilaporkan sebagai `TURNSTILE_MACET` / "periksa reputasi IP". | Jeda 3 detik, lalu tunggu `not btn.is_disabled()` (maks 20 detik), baru klik. Tombol siap: `button.checkin-claim`, 377×51, `disabled=false`, tidak tertutup elemen lain. |
| Modal offer "-20% Discount" menutupi layar | Promosi, bukan error | Skrip klik "Maybe later" sendiri. Aman diabaikan. |
| `EPIPE` / driver hang | Chrome lama masih memegang profil | Bunuh HANYA proses profil itu; hapus `SingletonLock`/`SingletonSocket`/`SingletonCookie` |
| Lock di `/tmp` → Permission denied | Di container `/tmp` dimiliki root | Lock sengaja di folder script. Jangan pindah ke `/tmp`. |
| Popup Google tak pernah terbuka | Tombol Google = `<a href>` biasa, bukan popup GIS | Script navigasi LANGSUNG ke `/api/user/auth/google?next=%2Foverview`. Jangan kembali ke klik-popup. |
| Layar "Lanjutkan" tak muncul lagi | Consent OAuth hanya sekali per aplikasi | Normal — Google melewatinya. |
| Login minta password padahal profil ada | Sesi Google kedaluwarsa | Normal; script mengisinya sendiri. |
| Folder profil tak bisa di-`rm` dari host | File dibuat proses browser di container | Hapus dari dalam: `docker exec hermes rm -rf /opt/data/vault/profiles/apinex_xxx` |
| Vault berisi >1 akun tanpa `--email` | Ambigu (khusus `login`/`register`) | Pakai `--email`; script menolak menebak. `checkin` tanpa `--email` = SEMUA akun (memang begitu maksudnya). |

---

## 9. Verifikasi keberhasilan (jangan tertipu)

- **Login sukses** bukan "URL berubah jadi /overview". Harus ada `API Keys` **dan**
  `Balance:` di `document.body.innerText`.
- **Check-in sukses** bukan "tombol sudah diklik", dan **bukan juga** "tombolnya hilang
  setelah diklik". Dua-duanya bisa menipu.

  Bukti sah = balasan `GET /api/user/xp/quests` **sesudah** klik:

  ```json
  {"checkin": {"dayKey": "2026-11-17", "checkedInToday": true,
               "currentStreak": 2, "rewardXp": 40, "claimedXp": 40,
               "multiplier": 1.1, "canClaim": false}}
  ```

  Yang wajib benar: **`checkedInToday: true`** dan **`claimedXp` > 0**. Kalau
  `checkedInToday` masih `false` → klaim TIDAK terjadi, walau tombol sudah hilang dari
  layar.

  Skrip menyimpan pembanding `sebelum` vs `sesudah` di `checkin_terakhir.json`.

- **Endpoint yang BENAR** (jangan tebak — ini sudah diverifikasi dari lalu lintas jaringan):
  - `GET /api/user/xp/quests` → status check-in (`checkin.*`) + quest harian
  - `GET /api/user/me` → identitas + `status` akun (`"active"`)
  - `GET /api/user/xp/leaderboard` → papan peringkat XP

  Yang **404** (jangan dipakai lagi): `/api/user/xp/status`, `/api/user/xp/checkin`,
  `/api/user/airdrop/status`.

---

## 10. Berkas terkait

### 10a. Jalur CloakBrowser yang BENAR (jangan salah)

| Keperluan | Jalur |
|---|---|
| Python **venv** (WAJIB ini, bukan `python3` biasa) | `/opt/data/services/cloakbrowser/.venv/bin/python3` |
| Paket `cloakbrowser` | `/opt/data/services/cloakbrowser/.venv/lib/python3.13/site-packages/cloakbrowser` |
| License key (mode 600, pemilik `hermes`) | `/opt/data/home/.cloakbrowser/license.key` |
| Cara impor | `from cloakbrowser import launch_persistent_context` |

Syarat jalan di dalam container: user `hermes`, `HOME=/tmp/cbhome2`, `DISPLAY=:97`
(Xvfb `1920x1080x24`), dan `CLOAKBROWSER_LICENSE_KEY` dibaca dari berkas di atas.

⚠️ **ATURAN CloakBrowser:**

- `launch_persistent_context` **JANGAN** dibungkus `sync_playwright()`.
- Proxy **hanya** lewat parameter `proxy=`, **JANGAN** `args=["--proxy-server", ...]`
  (browser langsung mati `TargetClosedError`). Untuk APInex: **tanpa proxy sama sekali**.

### 10b. Penyimpanan AKUN — folder profil, bukan tabel database

Satu akun = satu folder profil Chromium:

```
/opt/data/vault/profiles/apinex_paculdigital02/        <- akun 1 (Jizenji)
/opt/data/vault/profiles/apinex_anikeramadhan011/      <- akun 2 (Anike Ramadhan)
```

Cookie & sesi tersimpan di dalam folder itu:

```
<folder profil>/Default/Cookies      <- SQLite, 36864 byte, 28 cookie
```

Per 17 Nov 2026, tiap profil berisi **7 cookie `apinex.*`**:

| Cookie | Ukuran | Peran |
|---|---|---|
| `apinex_user_session` | **115 byte** | **KUNCI SESI** — satu-satunya yang menentukan token Turnstile terbit |
| `apinex_first_touch_v1` | 387 | atribusi iklan, tidak penting |
| `_ga`, `_ga_BK4NBJJJRP` | 67 / 83 | Google Analytics |
| `_ym_uid`, `_ym_d`, `_ym_isad` | 67 / 51 / 51 | Yandex Metrica, **tidak dipakai** |

**Dua jebakan membaca DB (keduanya nyata, terukur):**

1. **`Default/` milik `root`, mode 700** → dari host `Permission denied`.
   Baca lewat `docker exec hermes ...`.
2. **DB baru ditulis saat `ctx.close()`.** Membaca `Cookies` selagi browser
   terbuka → tabel kosong / `no such table: cookies`. Itu **normal**, bukan
   kerusakan. Verifikasi cookie hidup lewat CDP `Network.getCookies`.

### 10c. Berkas lain

- `/opt/data/services/apinex-run/apinex` — pembungkus host (Xvfb + license + docker exec)
- `/opt/data/services/apinex-run/apinex.py` — mesin login/register/status
- `/opt/data/services/apinex-run/apinex_checkin.py` — mesin check-in harian (multi-akun + jeda)
- `/opt/data/services/apinex-run/checkin_terakhir.json` — laporan check-in terakhir (dibuat saat jalan)
- `/opt/data/services/apinex-run/bukti/` — tangkapan layar bukti check-in
- `/opt/data/services/apinex-run/uji_vision.py` — alat tes model vision 9router
- `/opt/data/services/apinex-run/.apinex-browser.lock` — lockfile seat
- `/opt/data/vault/google_personal.json` — kredensial (chmod 600)
- `/opt/data/vault/accounts/` — catatan akun per situs
- Skill `apinex-google-oauth-farm` — ringkasan operasional

### 10d. Pintu masuk yang disarankan untuk agen lain

Agen lain **tidak perlu** menyentuh venv atau folder profil. Cukup:

```
/opt/data/services/apinex-run/apinex checkin --email <alamat>
```

Pembungkus itu sudah mengurus Xvfb, license, lock seat, dan `docker exec`.

---

## 11. Ringkasan satu paragraf untuk agen yang buru-buru

Kamu tidak perlu menyentuh kredensial Google. Untuk login: jalankan
`/opt/data/services/apinex-run/apinex login --email <email>` (atau `register` untuk akun
baru yang sudah ada di vault), tunggu `FINAL_SESSION: VALID`. Untuk check-in harian:
jalankan `/opt/data/services/apinex-run/apinex checkin` (semua akun, jeda natural otomatis)
atau tambahkan `--email <email>` untuk satu akun, lalu baca `checkin_terakhir.json`.
Sukses check-in = `checkedInToday: true` sesudah klaim, bukan sekadar tombol terklik.
Untuk tugas lain, pakai `launch_persistent_context` pada folder profil akun itu dan
**selalu** `ctx.close()` di `finally`. Exit code 3 = seat dipakai agen lain, bukan bug.
**Jangan pernah menjalankan dua proses check-in bersamaan** — seat cuma 1.
