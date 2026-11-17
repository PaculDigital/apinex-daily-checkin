#!/usr/bin/env bash
# APInex.bond — JOB HARIAN: semua akun, urutan acak, login kalau perlu, lalu check-in.
#
# SATU skrip untuk SEMUA akun. Menambah akun = tambahkan ke
# /opt/data/vault/google_personal.json (profil otomatis dibuat saat login).
# Tidak ada yang perlu diubah di sini.
#
# Yang diacak setiap hari:
#   1) urutan akun             (shuf)
#   2) jeda antar akun         (45-150 dtk, dari apinex_checkin.py / apinex.py)
#   3) jam mulai job           (dari cron: lihat cronjob "apinex-harian")
#
# Dipakai cron:
#   bash /opt/data/services/apinex-run/apinex_harian.sh
# Opsi:
#   --dry     bacakan status saja (tanpa check-in / tanpa OAuth)
#   --tanpa-login   jangan coba login otomatis kalau sesi mati
#
# Keluaran: ringkasan per akun. Log: /opt/data/services/apinex-run/harian_terakhir.log
# Exit: 0 semua beres · 1 ada akun gagal/butuh login · 3 seat dipakai agen lain
set -uo pipefail

DIR=/opt/data/services/apinex-run
VAULT=/opt/data/vault/google_personal.json
WRAP="$DIR/apinex"
LOG="$DIR/harian_terakhir.log"
DRY=""; AUTO_LOGIN=1

for a in "$@"; do
  case "$a" in
    --dry) DRY="--dry" ;;
    --tanpa-login) AUTO_LOGIN=0 ;;
  esac
done

: > "$LOG"
say() { echo "$*" | tee -a "$LOG"; }

# ── Daftar akun dari vault (email saja) ───────────────────────────────
mapfile -t AKUN < <(python3 - "$VAULT" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
d=d if isinstance(d,list) else [d]
for a in d:
    if a.get("email"): print(a["email"])
PY
)

if [ ${#AKUN[@]} -eq 0 ]; then
  say "FAIL_VAULT tidak ada akun di $VAULT"; exit 4
fi

# ── Urutan ACAK tiap hari (jangan selalu akun yang sama lebih dulu) ───
mapfile -t URUT < <(printf '%s\n' "${AKUN[@]}" | shuf)

say "=== APINEX HARIAN $(date -u '+%Y-%m-%d %H:%M:%S') UTC / $(TZ=Asia/Jakarta date '+%H:%M') WIB ==="
say "AKUN: ${#URUT[@]} · urutan: ${URUT[*]}"

# ── CATATAN JAM (16Nov26) ────────────────────────────────────────────
# Jam check-in APInex reset 00:00 UTC = 07:00 WIB. Cron sudah berbunyi
# tepat 00:00 UTC, jadi TIDAK ada penundaan yang perlu dipasang di sini.
# (Percobaan memasang "pagar jam" berbasis jam server TERBUKTI HIASAN:
#  awal-hari-UTC selalu <= sekarang, jadi kondisinya selalu lolos.
#  Jangan ulangi pola itu — penjaganya ada di sisi API, bukan jam.)
# Yang benar: apinex_checkin.py membaca GET /api/user/xp/quests lebih dulu
# dan hanya mengklaim kalau canClaim=true. Kalau APInex belum membuka
# check-in (canClaim=false / checkedInToday=false), skrip TIDAK memaksa.
NOW_WIB=$(TZ=Asia/Jakarta date '+%H:%M')
say "JAM: ${NOW_WIB} WIB (reset harian 07:00 WIB / 00:00 UTC)"

rc=0
login_dicoba=()
for i in "${!URUT[@]}"; do
  E="${URUT[$i]}"
  say ""
  say "--- [$((i+1))/${#URUT[@]}] $E ---"

  # 1) CHECK-IN (skrip checkin melaporkan BELUM_LOGIN lewat exit 5)
  out=$("$WRAP" checkin --email "$E" $DRY 2>&1); crc=$?
  echo "$out" | tee -a "$LOG" >/dev/null
  grep -E '^(SESSION|QUEST_CHECKIN|RINGKASAN|SUKSES|SUDAH|SIAP|BELUM_LOGIN|GAGAL|PERLU LOGIN)' <<<"$out" | sed 's/^/  /' | tee -a "$LOG"

  # 2) Sesi mati & bukan mode dry -> login otomatis, lalu check-in sekali lagi
  if [ "$crc" -eq 5 ] && [ "$AUTO_LOGIN" -eq 1 ] && [ -z "$DRY" ]; then
    say "  sesi mati -> LOGIN OTOMATIS"
    "$WRAP" login --email "$E" >>"$LOG" 2>&1; lrc=$?
    say "  login exit=$lrc"
    if [ "$lrc" -eq 2 ]; then rc=1; continue; fi
    login_dicoba+=("$E")
    out=$("$WRAP" checkin --email "$E" 2>&1); crc=$?
    echo "$out" | tee -a "$LOG" >/dev/null
    grep -E '^(SUKSES|SUDAH|SIAP|BELUM_LOGIN|GAGAL)' <<<"$out" | sed 's/^/  /' | tee -a "$LOG"
  fi

  case "$crc" in
    0) ;;
    3) say "  SEAT_DIPAKAI — hentikan job (agen lain memegang browser)"; rc=3; break ;;
    5) say "  PERLU_LOGIN manual: $WRAP login --email $E"; rc=1 ;;
    *) say "  ADA_KEGAGALAN exit=$crc"; rc=1 ;;
  esac

  # Seat = 1: skrip checkin sudah berjeda sendiri antarakun internal,
  # tapi karena kita panggil per akun, jeda di sini yang berlaku.
  if [ $((i+1)) -lt ${#URUT[@]} ] && [ "$crc" -ne 3 ]; then
    J=$(( RANDOM % 106 + 45 ))
    say "  jeda ${J}s"
    sleep "$J"
  fi
done

say ""
say "=== SELESAI $(date -u '+%H:%M:%S') UTC · exit=$rc ${login_dicoba[*]:-} ==="
exit "$rc"
