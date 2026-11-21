#!/bin/bash
# ── SIAP DAFTAR APInex AKUN KE-3 (lewat 9proxy Indonesia) ──────────────
# Pakai:
#   bash /opt/data/services/apinex-run/daftar_akun3.sh <email@gmail.com>
#
# PRASYARAT yang TIDAK bisa diperiksa skrip ini:
#   1. email sudah ditambahkan ke /opt/data/vault/google_personal.json
#      (format: [{"email":"...","password":"..."}])
#   2. password benar (kalau salah: macet di halaman password Google)
#
# Yang skrip ini JAMIN sebelum menyentuh APInex:
#   - Xvfb hidup, lisensi CloakBrowser ter-set, HOME writable
#   - egress 9proxy = INDONESIA (kalau tidak, BATAL sebelum daftar)
set -u

EMAIL="${1:-}"
if [ -z "$EMAIL" ]; then
  echo "PAKAI: bash $0 <email@gmail.com>" >&2
  exit 1
fi

LIC="$(cat /opt/data/home/.cloakbrowser/license.key 2>/dev/null)"
if [ -z "$LIC" ]; then echo "FAIL_LISENSI license.key kosong" >&2; exit 1; fi

echo "=== DAFTAR APInex: $EMAIL (proxy 9proxy ID) ==="
docker exec -e HOME=/tmp/cbhome2 -e CLOAKBROWSER_LICENSE_KEY="$LIC" hermes bash -c \
  "cd /opt/data/services/apinex-run && timeout 600 xvfb-run -a -s '-screen 0 1920x1080x24' \
   /opt/data/services/cloakbrowser/.venv/bin/python3 apinex.py register \
   --email '$EMAIL' --proxy" 2>&1 | grep -vE "Update available"

echo "=== SELESAI. Screenshot: /opt/data/services/apinex-run/step_${EMAIL%%@*}.png ==="
