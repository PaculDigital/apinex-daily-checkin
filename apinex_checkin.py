#!/usr/bin/env python3
"""APInex.bond — CHECK-IN HARIAN (daily check-in) untuk banyak akun.

Dijalankan DI DALAM container `hermes`, lewat pembungkus host:
  ./apinex checkin                 # semua akun di vault
  ./apinex checkin --email a@gmail.com
  ./apinex checkin --dry           # hanya baca status, tanpa mengklaim
  ./apinex checkin --jeda 45       # detik acak antar akun (bawaan 45-150)

Kenapa ada JEDA:
  Seat CloakBrowser Pro cuma 1 -> akun WAJIB diproses BERGILIRAN.
  Jeda acak + jam kerja acak membuat pola kunjungan terlihat seperti manusia,
  bukan bot yang menembak 5 akun berurutan dalam 10 detik.

Endpoint yang dipakai (terbukti 16 Nov 2026):
  GET  /api/user/xp/quests     -> status check-in (canClaim, streak, checkedInToday)
  POST /api/user/xp/checkin    -> klaim, body {"turnstileToken": "<token>"}

Turnstile: widget dimuat otomatis saat modal check-in dibuka. Token terbit
~10-12 detik (mode invisible, tidak perlu klik apa pun). Modal DAILY CHECK-IN
sudah terbuka sendiri di /airdrop. Tombolnya bernama "Check in & continue"
(terukur 17 Nov 2026) dan DISABLED selama token belum siap — itu normal.

Exit code: 0 semua beres/berhasil · 1 ada akun gagal · 3 seat dipakai agen lain
           4 email tak ada di vault · 5 sesi mati (perlu `apinex login`)
Hasil JSON: /opt/data/services/apinex-run/checkin_terakhir.json
"""
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone

from cloakbrowser import launch_persistent_context

# ── Konfigurasi ────────────────────────────────────────────────────────
SITE = "https://apinex.bond"
VAULT = os.environ.get("APINEX_VAULT", "/opt/data/vault/google_personal.json")
PROFILE_BASE = os.environ.get("APINEX_PROFILE_BASE", "/opt/data/vault/profiles")
SHOT_DIR = os.environ.get("APINEX_SHOTS", "/opt/data/services/apinex-run")
HASIL_JSON = os.environ.get(
    "APINEX_HASIL", "/opt/data/services/apinex-run/checkin_terakhir.json")
LOCK_PATH = os.environ.get(
    "APINEX_LOCK",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".apinex-browser.lock"))
LOCALE, TZ = "en-US", "Asia/Jakarta"

# Jeda antar akun (detik). Acak supaya tidak berpola mesin.
JEDA_MIN = int(os.environ.get("APINEX_JEDA_MIN", "45"))
JEDA_MAX = int(os.environ.get("APINEX_JEDA_MAX", "150"))
# Batas tunggu token Turnstile per akun.
TURNSTILE_TIMEOUT = int(os.environ.get("APINEX_TURNSTILE_TIMEOUT", "45"))

# ── CATATAN: PROXY SUDAH DICABUT (17 Nov 2026) ─────────────────────────
# Dulu di sini ada APINEX_PROXY (9proxy residensial) dengan alasan "Cloudflare
# menolak IP VPS". ALASAN ITU TERBUKTI SALAH lewat uji pemisahan: yang membuat
# token Turnstile terbit adalah cookie `apinex_user_session` di profil, BUKAN
# IP keluar. Tiga IP berbeda (Telkomsel, Jakarta, VPS langsung) memberi hasil
# identik. Jangan pasang kembali proxy dari sini — perbaiki sesinya.

# ── Argumen ────────────────────────────────────────────────────────────
ARGS = sys.argv[1:]
DRY = "--dry" in ARGS

if "--email" in ARGS:
    try:
        HANYA = [ARGS[ARGS.index("--email") + 1]]
    except IndexError:
        sys.exit("FAIL_ARGS --email butuh nilai")
elif os.environ.get("APINEX_EMAIL"):
    HANYA = [os.environ["APINEX_EMAIL"]]
else:
    HANYA = []          # kosong = semua akun di vault

if "--jeda" in ARGS:
    try:
        JEDA_MIN = JEDA_MAX = int(ARGS[ARGS.index("--jeda") + 1])
    except (IndexError, ValueError):
        sys.exit("FAIL_ARGS --jeda butuh angka detik")


# ── Utilitas ───────────────────────────────────────────────────────────
def load_vault():
    try:
        d = json.load(open(VAULT))
    except Exception as e:
        sys.exit(f"FAIL_VAULT tidak bisa baca {VAULT}: {type(e).__name__}")
    return d if isinstance(d, list) else [d]


def profil(email):
    """Satu akun = satu folder profil (seed sidik jari ikut di dalamnya)."""
    if os.environ.get("APINEX_PROFILE"):
        return os.environ["APINEX_PROFILE"]
    return os.path.join(
        PROFILE_BASE, "apinex_" + email.split("@")[0].replace(".", "_"))


def take_lock():
    import fcntl
    fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("FAIL_SEAT_DIPAKAI agen lain sedang memakai browser "
              f"(lock {LOCK_PATH}).", file=sys.stderr)
        sys.exit(3)
    return fh


def release_lock(fh):
    try:
        import fcntl
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()
    except Exception:
        pass


def jeda_natural():
    """Jeda acak + sedikit 'tarikan napas' manusia antara dua akun."""
    d = random.randint(JEDA_MIN, JEDA_MAX)
    print(f"JEDA {d}s sebelum akun berikutnya (meniru jeda manusia)")
    time.sleep(d)


def api_quests(page):
    """Baca status check-in dari endpoint asli (bukan tebak dari teks)."""
    try:
        return page.evaluate("""async () => {
            const r = await fetch('/api/user/xp/quests', {credentials: 'include'});
            if (!r.ok) return {err: 'HTTP ' + r.status};
            return await r.json();
        }""")
    except Exception as e:
        return {"err": f"{type(e).__name__}: {e}"}


def ambil_checkin(q):
    """Cari objek check-in di mana pun letaknya di dalam JSON quests."""
    if not isinstance(q, dict):
        return {}
    for kunci in ("checkin", "checkIn", "dailyCheckin", "daily_checkin"):
        v = q.get(kunci)
        if isinstance(v, dict):
            return v
    # fallback: telusuri satu tingkat
    for v in q.values():
        if isinstance(v, dict):
            for kunci in ("checkin", "checkIn", "dailyCheckin"):
                if isinstance(v.get(kunci), dict):
                    return v[kunci]
    # fallback terakhir: cari apa pun yang punya canClaim
    def cari(o, dalam=0):
        if dalam > 3 or not isinstance(o, dict):
            return {}
        if "canClaim" in o or "checkedInToday" in o:
            return o
        for v in o.values():
            r = cari(v, dalam + 1)
            if r:
                return r
        return {}
    return cari(q)


def sesi_valid(page):
    try:
        page.goto(f"{SITE}/overview", wait_until="domcontentloaded")
        time.sleep(5)
        b = page.evaluate("() => document.body.innerText.slice(0,600)")
        return (("API Keys" in b or "Balance:" in b) and "/overview" in page.url), b
    except Exception as e:
        return False, f"ERR {type(e).__name__}"


def teks_modal_checkin(page):
    """Teks modal check-in yang sedang terbuka ('' kalau tidak ada).

    Modal terbuka SENDIRI di /airdrop. Diukur: tinggi > 100px, memuat kata
    'check in' dan salah satu dari reward/continue.
    """
    try:
        return page.evaluate("""() => {
            const kandidat = [...document.querySelectorAll('[role=dialog],[class*=modal],[class*=Modal]')]
              .filter(e => e.getBoundingClientRect().height > 100);
            for (const e of kandidat) {
                const t = (e.innerText || '');
                if (/check.?in/i.test(t) && /(continue|reward|free tokens)/i.test(t)) return t;
            }
            return '';
        }""")
    except Exception:
        return ""


def klaim_lewat_ui(page):
    """Buka /airdrop, tunggu token Turnstile, klik 'Check in & continue'.

    Kembalikan (status, catatan). status: True = berhasil, False = gagal,
    atau string status khusus ("BUTUH_DISELIDIKI", "TURNSTILE_MACET").
    """
    # 1) Buka /airdrop
    page.goto(f"{SITE}/airdrop", wait_until="domcontentloaded")
    time.sleep(5)

    # 2) Tutup modal promosi kalau menutupi layar (tombol "Maybe later")
    try:
        later = page.locator(
            "button:has-text('Maybe later'), button:has-text('Nanti saja')").first
        if later.is_visible(timeout=2500):
            later.click(timeout=5000)
            print("POPUP_PROMO_DITUTUP")
            time.sleep(1.5)
    except Exception:
        pass

    # 3) Modal check-in SUDAH TERBUKA SENDIRI di /airdrop (terukur 17Nov26 lewat
    #    probe DOM). JANGAN mencari tombol pembuka — tombol pembuka tidak ada,
    #    dan kegagalan mencarinya dulu berakhir jadi kesimpulan palsu
    #    "mungkin sudah diklaim hari ini".
    modal = teks_modal_checkin(page)
    if not modal:
        # halaman mungkin belum render; beri satu kesempatan render ulang
        time.sleep(3)
        modal = teks_modal_checkin(page)
    if modal:
        print(f"MODAL_CHECKIN_TERBUKA (teks {len(modal)} char)")
    else:
        return ("BUTUH_DISELIDIKI",
                "modal check-in tidak terlihat di /airdrop "
                "(bukan berarti sudah diklaim)")

    # 4) Tunggu token Turnstile terbit, lalu tombol jadi aktif.
    #    JANGAN menggantungkan pembacaan pada keberadaan iframe Cloudflare —
    #    terukur 17Nov26: iframe TIDAK ADA SAMA SEKALI (0) padahal script
    #    Turnstile tetap dimuat. Syarat iframe = loop tidak pernah jalan.
    t0 = time.time()
    tok = ""
    while time.time() - t0 < TURNSTILE_TIMEOUT:
        try:
            tok = page.evaluate(
                "() => (document.querySelector("
                "  'input[name=\"cf-turnstile-response\"]')?.value || ''"
                "  ).replace(/\\s/g, '')"
            )
            if tok:
                print(f"TURNSTILE_TOKEN_OK ({len(tok)} char, "
                      f"{round(time.time()-t0,1)}s)")
                break
        except Exception:
            pass
        time.sleep(1.5)
    else:
        return ("TURNSTILE_MACET",
                f"token Turnstile tidak terbit dalam {TURNSTILE_TIMEOUT}s — "
                "Cloudflare menahan token untuk sesi/IP ini (reputasi/PST), "
                "bukan masalah selektor")

    # 5) Klik tombol klaim. Nama tombol yang BENAR (diukur 17Nov26):
    #    "Check in & continue" — di dalam modal, disabled sampai Turnstile terbit.
    #
    #    PENTING (terukur 17Nov26, akun anikeramadhan011): token terbit != tombol
    #    langsung aktif. React butuh beberapa detik untuk mengaktifkan tombol
    #    sesudah token masuk. Kalau diklik terlalu cepat, Playwright melempar
    #    "element is not enabled" dan skrip menyimpulkan PALSU "turnstile macet".
    #    Beri jeda 3 detik dulu, lalu TUNGGU sampai tombol benar-benar enabled
    #    (maks 20 detik) sebelum mengklik.
    time.sleep(3)

    klik = False
    btn = page.locator("button.checkin-claim, button:has-text('Check in & continue')").first
    try:
        btn.wait_for(state="visible", timeout=10000)
        for _ in range(20):                       # maks 20 detik menunggu aktif
            try:
                if not btn.is_disabled():
                    break
            except Exception:
                pass
            time.sleep(1)
        if not btn.is_disabled():
            try:
                btn.click(timeout=8000)
            except Exception:
                # cadangan: klik lewat JS (mis. kalau tertutup animasi/overlay)
                page.evaluate("""() => {
                    const b = document.querySelector('button.checkin-claim')
                           || [...document.querySelectorAll('button')]
                                .find(x => /check in & continue/i.test(x.innerText));
                    if (b) b.click();
                }""")
            klik = True
            print("TOMBOL_CLAIM_DIKLIK")
    except Exception as e:
        print(f"TOMBOL_GAGAL: {type(e).__name__} {e}")

    if not klik:
        return ("TOMBOL_MACET",
                f"tombol 'Check in & continue' tidak bisa diklik walau token "
                f"terbit ({len(tok)} char) — periksa DOM tombol, BUKAN reputasi IP")

    # 6) Tunggu request check-in selesai & baca ulang status
    time.sleep(6)
    q = api_quests(page)
    ci = ambil_checkin(q)
    if ci.get("checkedInToday") or ci.get("claimedToday"):
        return True, (f"streak={ci.get('currentStreak', ci.get('streak', '?'))} "
                      f"xp={ci.get('claimedXp', ci.get('xp', '?'))}")
    return False, f"klik terkirim tapi status belum berubah: {json.dumps(ci)[:180]}"


def proses_akun(A, idx, total):
    """Check-in satu akun. Kembalikan dict hasil."""
    email = A["email"]
    hasil = {"email": email, "akun_ke": f"{idx}/{total}",
             "waktu": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "status": "GAGAL", "catatan": ""}
    print(f"\n=== AKUN {idx}/{total}: {email} ===")

    prof = profil(email)
    if not os.path.isdir(prof):
        hasil["catatan"] = f"profil belum ada ({prof}) — jalankan apinex login dulu"
        hasil["status"] = "BELUM_LOGIN"
        return hasil
    print(f"PROFILE: {prof}")

    ctx = None
    try:
        # Argumen launch. JANGAN pakai args ["--proxy-server", ...] kalau suatu
        # saat perlu proxy: browser MATI saat launch (TargetClosedError).
        # Terukur 16 Nov 2026 (fact 343). Proxy TIDAK perlu untuk check-in —
        # lihat catatan "PROXY SUDAH DICABUT" di atas.
        opsi_launch = dict(headless=False, humanize=True,
                           locale=LOCALE, timezone=TZ)
        ctx = launch_persistent_context(prof, **opsi_launch)
        page = ctx.new_page()

        ok, b = sesi_valid(page)
        print("SESSION:", "VALID" if ok else "NONE")
        if not ok:
            hasil["status"] = "BELUM_LOGIN"
            hasil["catatan"] = "sesi mati — jalankan apinex login --email " + email
            return hasil

        q = api_quests(page)
        ci = ambil_checkin(q)
        print("QUEST_CHECKIN:", json.dumps(ci, ensure_ascii=False)[:300])
        hasil["sebelum"] = {k: ci.get(k) for k in
                            ("canClaim", "checkedInToday", "currentStreak", "day")}

        if ci.get("checkedInToday") or ci.get("claimedToday"):
            hasil["status"] = "SUDAH"
            hasil["catatan"] = "sudah check-in hari ini"
            return hasil

        if DRY:
            hasil["status"] = "SIAP" if ci.get("canClaim") else "TIDAK_BISA"
            hasil["catatan"] = "mode --dry, tidak mengklaim"
            return hasil

        # ── PENJAGA: jangan paksa klaim kalau APInex belum membuka cek-in ──
        # Ini yang dulu bikin "sudah lewat 07.00 tapi cek-in belum muncul":
        # skrip tetap masuk ke UI & gagal, padahal tombolnya memang belum ada.
        # Sekarang: coba beberapa kali (situs kadang telat beberapa menit),
        # kalau tetap belum siap -> status TIDAK_BISA (jujur, bukan GAGAL palsu).
        if not ci.get("canClaim"):
            for tunggu in (20, 45, 90, 180):
                print(f"BELUM_BUKA: canClaim=false, cek ulang {tunggu}s lagi")
                time.sleep(tunggu)
                ci = ambil_checkin(api_quests(page))
                if ci.get("checkedInToday") or ci.get("claimedToday"):
                    hasil["status"] = "SUDAH"
                    hasil["catatan"] = "sudah check-in (terdeteksi saat menunggu)"
                    return hasil
                if ci.get("canClaim"):
                    print("CEKIN_DIBUKA setelah menunggu")
                    break
            else:
                hasil["status"] = "TIDAK_BISA"
                hasil["catatan"] = (
                    "APInex belum membuka check-in (canClaim=false) setelah "
                    "menunggu ~5,5 menit — bukan gagal, coba lagi nanti: "
                    f"{json.dumps(ci, ensure_ascii=False)[:150]}")
                return hasil

        klaim, catatan = klaim_lewat_ui(page)
        # klaim bisa True (sukses), False (gagal), atau status khusus string:
        # BUTUH_DISELIDIKI / TURNSTILE_MACET — JANGAN ditelan jadi "GAGAL".
        if klaim is True:
            hasil["status"] = "SUKSES"
        elif isinstance(klaim, str):
            hasil["status"] = klaim
        else:
            hasil["status"] = "GAGAL"
        hasil["catatan"] = catatan

        q2 = api_quests(page)
        ci2 = ambil_checkin(q2)
        hasil["sesudah"] = {k: ci2.get(k) for k in
                            ("checkedInToday", "currentStreak", "day")}

        shot = os.path.join(SHOT_DIR, f"checkin_{email.split('@')[0]}.png")
        try:
            page.screenshot(path=shot)
            hasil["bukti"] = shot
        except Exception:
            pass
        return hasil
    except Exception as e:
        hasil["catatan"] = f"{type(e).__name__}: {str(e)[:160]}"
        return hasil
    finally:
        if ctx is not None:
            try:
                ctx.close()     # WAJIB: 1 seat, sesi menggantung = lockout
            except Exception:
                pass


def main():
    akun = load_vault()
    if HANYA:
        akun = [a for a in akun if a.get("email") in HANYA]
        if not akun:
            print(f"FAIL_NO_ACCOUNT {HANYA[0]} tidak ada di {VAULT}", file=sys.stderr)
            sys.exit(4)

    total = len(akun)
    print(f"CHECKIN MULAI: {total} akun · dry={DRY} · jeda {JEDA_MIN}-{JEDA_MAX}s")
    print(f"WAKTU UTC: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    lock = take_lock()
    semua = []
    try:
        for i, A in enumerate(akun, 1):
            semua.append(proses_akun(A, i, total))
            # Jeda natural antar akun — TIDAK setelah akun terakhir.
            if i < total:
                jeda_natural()
    finally:
        release_lock(lock)

    # ── Ringkasan ──
    print("\n" + "=" * 52)
    print("RINGKASAN CHECK-IN")
    print("=" * 52)
    for h in semua:
        print(f"{h['status']:<12} {h['email']:<30} {h.get('catatan','')[:60]}")

    sukses = sum(1 for h in semua if h["status"] in ("SUKSES", "SUDAH"))
    print(f"\nBERHASIL: {sukses}/{total}")
    belum_login = [h["email"] for h in semua if h["status"] == "BELUM_LOGIN"]
    gagal = [h["email"] for h in semua if h["status"] == "GAGAL"]
    if belum_login:
        print("PERLU LOGIN:", ", ".join(belum_login))
    if gagal:
        print("GAGAL:", ", ".join(gagal))

    try:
        json.dump({"dijalankan": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "dry": DRY, "hasil": semua},
                  open(HASIL_JSON, "w"), indent=2, ensure_ascii=False)
        print(f"HASIL_JSON: {HASIL_JSON}")
    except Exception as e:
        print(f"WARN tidak bisa tulis {HASIL_JSON}: {type(e).__name__}")

    if belum_login:
        sys.exit(5)
    if gagal:
        sys.exit(1)


if __name__ == "__main__":
    main()
