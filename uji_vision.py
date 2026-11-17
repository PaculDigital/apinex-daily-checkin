import base64, json, time, urllib.request, sys

KEY = "sk-dc042321c94f2e3e-eqml46-bf9b749d"
URL = "http://172.17.0.1:20128/v1/chat/completions"
IMG = sys.argv[1] if len(sys.argv) > 1 else "/opt/data/cache/scratch/probe_checkin4.png"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "vision-eduai"

b64 = base64.b64encode(open(IMG, "rb").read()).decode()
payload = {
    "model": MODEL,
    "max_tokens": 1200,
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": (
                "Baca layar ini apa adanya. Jawab TERBATAS pada 4 butir, "
                "tanpa menebak: (1) judul modal yang terbuka, "
                "(2) ada widget Cloudflare Turnstile (kotak/checkbox) atau tidak, "
                "(3) tombol Claim berwarna penuh/AKTIF atau abu-abu/disabled, "
                "(4) ada teks error? sebutkan persisnya atau tulis TIDAK ADA."
            )},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
        ],
    }],
}
req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                             headers={"Authorization": f"Bearer {KEY}",
                                      "Content-Type": "application/json"})
t0 = time.time()
try:
    raw = urllib.request.urlopen(req, timeout=180).read().decode()
except Exception as e:
    print("GAGAL:", type(e).__name__, e)
    sys.exit(1)
dt = round(time.time() - t0, 1)
if raw.rstrip().endswith("data: [DONE]"):
    raw = raw[:raw.rindex("data: [DONE]")]
try:
    j = json.loads(raw)
except Exception as e:
    print("JSON_ERR:", e, raw[:500]); sys.exit(1)
ch = j.get("choices", [{}])[0].get("message", {})
print(f"MODEL={MODEL} WAKTU={dt}s")
print("USAGE:", j.get("usage"))
print("JAWABAN:")
print(ch.get("content") if isinstance(ch.get("content"), str) else json.dumps(ch, ensure_ascii=False)[:2000])
