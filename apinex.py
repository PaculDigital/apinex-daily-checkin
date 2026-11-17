#!/usr/bin/env python3
"""APInex.bond — register & login via Google OAuth (CloakBrowser headed).

Pakai:
  python3 apinex.py status     # cek sesi hidup/mati (headless, tanpa interaksi)
  python3 apinex.py login      # login/lanjutkan sesi akun APINEX_EMAIL / --email
  python3 apinex.py register   # daftar akun baru (otomatis login kalau sudah ada)

Pilih akun:
  APINEX_EMAIL=someone@gmail.com python3 apinex.py register
  python3 apinex.py register --email someone@gmail.com
  (tanpa --email: pakai APINEX_EMAIL, atau akun PERTAMA di vault kalau cuma satu)

Akun baru = tambahkan dulu kredensialnya ke vault:
  /opt/data/vault/google_personal.json  ->  [{"email":..,"password":..}]
  lalu jalankan:  python3 apinex.py register --email someone@gmail.com
  Profil browser otomatis dibuat di /opt/data/vault/profiles/apinex_<prefix-email>.
  Profil terpisah = sesi Google tidak saling menimpa.

Exit code: 0 sukses · 2 sesi gagal · 3 seat dipakai agen lain · 4 akun tak ada di vault

Syarat jalan (DI DALAM container `hermes`, lihat skill apinex-google-oauth-farm):
  DISPLAY=:97 + Xvfb aktif + CLOAKBROWSER_LICENSE_KEY ter-set + HOME writable.

Kredensial dibaca dari vault; TIDAK pernah dicetak.
"""
import json
import os
import random
import sys
import time

from cloakbrowser import launch_persistent_context

# ── Konfigurasi ────────────────────────────────────────────────────────
SITE = "https://apinex.bond"
OAUTH_URL = f"{SITE}/api/user/auth/google?next=%2Foverview"
VAULT = os.environ.get("APINEX_VAULT", "/opt/data/vault/google_personal.json")
SHOT_DIR = os.environ.get("APINEX_SHOTS", "/opt/data/services/apinex-run")
PROFILE_BASE = os.environ.get("APINEX_PROFILE_BASE", "/opt/data/vault/profiles")
# Jeda acak antar akun (detik) — seat CloakBrowser Pro = 1, akun bergiliran.
JEDA_MIN = int(os.environ.get("APINEX_JEDA_MIN", "45"))
JEDA_MAX = int(os.environ.get("APINEX_JEDA_MAX", "150"))
# Lockfile: default di folder script (bukan /tmp) karena di container `hermes`
# /tmp dimiliki user lain -> PermissionError. Folder script selalu writable.
LOCK_PATH = os.environ.get(
    "APINEX_LOCK",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".apinex-browser.lock"))
LOCALE, TZ = "en-US", "Asia/Jakarta"

# Email boleh dari --email atau APINEX_EMAIL. Kalau kosong: akun pertama di vault.
ACCOUNT_EMAIL = os.environ.get("APINEX_EMAIL", "")
if "--email" in sys.argv:
    try:
        ACCOUNT_EMAIL = sys.argv[sys.argv.index("--email") + 1]
    except IndexError:
        sys.exit("FAIL_ARGS --email butuh nilai")


def load_vault():
    try:
        d = json.load(open(VAULT))
    except Exception as e:
        sys.exit(f"FAIL_VAULT tidak bisa baca {VAULT}: {type(e).__name__}")
    return d if isinstance(d, list) else [d]


def pick_account():
    """Akun yang dipakai. Tanpa --email/APINEX_EMAIL = SEMUA akun (bergiliran).

    Vault bisa berisi banyak akun; dulu ini menolak (FAIL_NO_EMAIL). Sekarang
    mengembalikan seluruh daftar supaya `login`/`status` bisa mengurus semua
    akun dalam satu panggilan — seat tetap 1, jadi diproses BERURUTAN.
    """
    global ACCOUNT_EMAIL
    accounts = load_vault()
    if not ACCOUNT_EMAIL:
        if not accounts:
            sys.exit(f"FAIL_VAULT {VAULT} kosong")
        return accounts            # semua akun, berurutan
    for a in accounts:
        if a.get("email") == ACCOUNT_EMAIL:
            return [a]
    print(f"FAIL_NO_ACCOUNT {ACCOUNT_EMAIL} tidak ada di {VAULT}", file=sys.stderr)
    print("Tambahkan dulu kredensialnya ke vault, lalu jalankan lagi.", file=sys.stderr)
    sys.exit(4)


def profile_for(email):
    """Satu akun = satu folder profil supaya sesi Google tidak saling menimpa."""
    if os.environ.get("APINEX_PROFILE"):
        return os.environ["APINEX_PROFILE"]
    return os.path.join(PROFILE_BASE, "apinex_" + email.split("@")[0].replace(".", "_"))


def take_lock():
    """Seat CloakBrowser Pro hanya SATU. Cegah rebutan antar agen."""
    import fcntl
    fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("FAIL_SEAT_DIPAKAI agen lain sedang memakai browser "
              f"(lock {LOCK_PATH}). Coba lagi nanti.", file=sys.stderr)
        sys.exit(3)
    return fh


def release_lock(fh):
    try:
        import fcntl
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()
    except Exception:
        pass


def body(el, n=800):
    try:
        return el.evaluate(
            "() => document.body.innerText.slice(0,%d)" % n).replace("\n", " | ")
    except Exception:
        return ""


def logged_in(p):
    """Dashboard APInex hanya muncul kalau sesi valid."""
    try:
        p.goto(f"{SITE}/overview", wait_until="domcontentloaded")
        time.sleep(5)
        b = body(p, 400)
        ok = ("API Keys" in b or "Balance:" in b) and "/overview" in p.url
        return ok, b
    except Exception as e:
        return False, f"ERR {type(e).__name__}"


def oauth_flow(page, A):
    """Navigasi LANGSUNG ke endpoint OAuth (popup GIS tidak terbentuk di stealth).
    Menangani: account chooser -> email -> reCAPTCHA Enterprise -> password -> consent."""
    page.goto(OAUTH_URL, wait_until="domcontentloaded")
    time.sleep(6)

    gp = page
    for _ in range(8):
        if "accounts.google.com" in gp.url:
            break
        time.sleep(2)
    print("AT_GOOGLE:", gp.url[:120])
    b = body(gp)

    # 1) account chooser (sesi Google lama tersimpan di profil)
    if "accountchooser" in gp.url or "Choose an account" in b or "Pilih akun" in b:
        gp.get_by_text(ACCOUNT_EMAIL.split("@")[0], exact=False).first.click(timeout=10000)
        print("ACCOUNT_PICKED")
        time.sleep(8)
        b = body(gp)

    # 2) input email manual (profil bersih / sesi habis)
    if "Email or phone" in b or "Email atau telepon" in b:
        em = gp.locator("input#identifierId, input[type=email]").first
        em.wait_for(timeout=10000)
        em.type(A["email"], delay=70)
        time.sleep(2)
        gp.locator("button:has-text('Next'), button:has-text('Berikutnya'), "
                   "button[type=submit]").first.click()
        time.sleep(6)
        b = body(gp)
        print("EMAIL_SUBMITTED:", gp.url[:110])

    # 3) challenge robot Google (reCAPTCHA Enterprise) — stealth biasanya lolos
    if "recaptcha" in gp.url or "robot" in b.lower():
        try:
            gp.frame_locator("iframe[src*='recaptcha']").first.locator(
                "#recaptcha-anchor, .rec-checkbox-span").first.click(timeout=8000)
            print("ANCHOR_CLICKED")
            time.sleep(8)
            b = body(gp)
        except Exception as e:
            print("ANCHOR_FAIL:", type(e).__name__, "(lanjut; mungkin auto-pass)")

    # 4) password
    pw = gp.locator("input[type=password]").first
    try:
        pw.wait_for(timeout=8000)
        pw.type(A["password"], delay=70)
        time.sleep(2)
        gp.locator("button:has-text('Next'), button:has-text('Berikutnya'), "
                   "button[type=submit]").first.click()
        print("PW_SUBMITTED")
        time.sleep(10)
    except Exception:
        print("NO_PW_FIELD (sesi Google masih hidup — langsung consent)")

    # 5) consent APInex -> Lanjutkan/Continue
    for i in range(4):
        b = body(gp)
        if SITE in gp.url and "auth" not in gp.url:
            break
        try:
            btn = gp.locator("#approve-consent-button, button:has-text('Lanjutkan'), "
                             "button:has-text('Continue')").last
            btn.wait_for(state="visible", timeout=12000)
            btn.click(timeout=10000)
            print("CONSENT_APPROVED")
            time.sleep(12)
            break
        except Exception as e:
            print(f"CONSENT_WAIT{i}: {gp.url[:100]} | {b[:150]}")
            time.sleep(4)
    print("OAUTH_END:", gp.url[:130])


def per_akun(A, mode):
    """Satu akun: buka profil, cek sesi, (opsional) login/register. True=sesi valid."""
    profile = profile_for(A["email"])
    os.makedirs(profile, exist_ok=True)
    print(f"\nACCOUNT: {A['email']}")
    print(f"PROFILE: {profile}")

    ctx = launch_persistent_context(profile, headless=(mode == "status"),
                                    humanize=True, locale=LOCALE, timezone=TZ)
    try:
        page = ctx.new_page()
        ok, b = logged_in(page)
        print("SESSION:", "VALID" if ok else "NONE")
        print("DASH:", b[:250])

        if ok and mode != "register":
            print("ALREADY_LOGGED_IN")
            return True

        if mode == "status":
            print("NOT_LOGGED_IN")
            return False

        if mode == "register":
            page.goto(f"{SITE}/register", wait_until="domcontentloaded")
            time.sleep(4)
            # Klik checkbox ToS via JS (aman walau elemen tak ada)
            try:
                page.evaluate("() => document.querySelector('input[type=checkbox]').click()")
            except Exception:
                pass

        oauth_flow(page, A)

        ok, b = logged_in(page)
        shot = os.path.join(SHOT_DIR, f"step_{A['email'].split('@')[0]}.png")
        try:
            page.screenshot(path=shot)
        except Exception:
            pass
        print("FINAL_SESSION:", "VALID" if ok else "FAILED")
        print("FINAL_DASH:", b[:400])
        return ok
    except Exception as e:
        print(f"FAIL_AKUN {type(e).__name__}: {str(e)[:160]}")
        return False
    finally:
        ctx.close()   # WAJIB: plan Pro = 1 seat; sesi menggantung = lockout 4-30 mnt


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = (args[0] if args else "status").lower()
    if mode not in ("register", "login", "status"):
        sys.exit(f"FAIL_MODE '{mode}' — pakai: register | login | status")

    # pick_account() DULU: kalau akun tak ada di vault, keluar exit 4 TANPA
    # membuka browser (hemat seat + tidak pernah kena timeout jaringan).
    akun = pick_account()
    os.makedirs(SHOT_DIR, exist_ok=True)

    lock = None
    if mode != "status":
        lock = take_lock()

    hasil = {}
    try:
        for i, A in enumerate(akun, 1):
            if len(akun) > 1:
                print(f"\n=== AKUN {i}/{len(akun)} ({mode}) ===")
            hasil[A["email"]] = per_akun(A, mode)
            # Seat = 1: beri jeda supaya browser lama benar-benar lepas.
            if i < len(akun):
                jeda = random.randint(JEDA_MIN, JEDA_MAX)
                print(f"JEDA {jeda}s sebelum akun berikutnya")
                time.sleep(jeda)
    finally:
        if lock:
            release_lock(lock)

    if len(hasil) > 1:
        print("\nRINGKASAN")
        for email, ok in hasil.items():
            print(f"{'VALID' if ok else 'TIDAK_VALID':<12} {email}")

    if not all(hasil.values()):
        sys.exit(2)


if __name__ == "__main__":
    main()
