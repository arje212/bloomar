import json
import random
import io
import numpy as np
from PIL import Image
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# ─────────────────────────────────────────────
#  Page views
# ─────────────────────────────────────────────
def home(request):        return render(request, 'home.html')
def camera(request):      return render(request, 'camera.html')
def editor(request):      return render(request, 'editor.html')
def ar_preview(request):  return render(request, 'ar_preview.html')


# ─────────────────────────────────────────────
#  Flower definitions — (name, hue_ranges, sat_min, val_min, val_max, priority)
# ─────────────────────────────────────────────
FLOWER_COLORS = [
    ("Sunflower", [(25, 65)],              120, 120, 255, 10),
    ("Lily",      [(10, 28)],              120, 100, 255,  9),
    ("Rose",      [(0, 14), (346, 360)],   110,  50, 220,  8),
    ("Hibiscus",  [(0, 12), (348, 360)],   150,  30, 180,  7),
    ("Tulip",     [(300, 345)],             90,  80, 255,  6),
    ("Cosmos",    [(280, 320)],             80,  70, 255,  5),
    ("Orchid",    [(250, 280)],             70,  60, 255,  4),
]

FLOWER_MAP = {
    "Rose":       {"svg_file": "rose.svg",       "matched_color": "#FF5C8A", "dominant_color": "#E8507A"},
    "Hibiscus":   {"svg_file": "hibiscus.svg",   "matched_color": "#E53935", "dominant_color": "#C62828"},
    "Cosmos":     {"svg_file": "cosmos.svg",     "matched_color": "#AB47BC", "dominant_color": "#8E24AA"},
    "Tulip":      {"svg_file": "tulip.svg",      "matched_color": "#EF476F", "dominant_color": "#D63A5F"},
    "Sunflower":  {"svg_file": "sunflower.svg",  "matched_color": "#FFD166", "dominant_color": "#F0C050"},
    "Daisy":      {"svg_file": "daisy.svg",      "matched_color": "#FFFDE7", "dominant_color": "#F5F5DC"},
    "Orchid":     {"svg_file": "orchid.svg",     "matched_color": "#CE93D8", "dominant_color": "#BA68C8"},
    "Lily":       {"svg_file": "lily.svg",       "matched_color": "#FF8A65", "dominant_color": "#FF7043"},
    "Wildflower": {"svg_file": "wildflower.svg", "matched_color": "#8338EC", "dominant_color": "#7020D0"},
}

FALLBACK_RESULT = {
    "flower_type":    "Wildflower",
    "matched_color":  "#8338EC",
    "dominant_color": "#7020D0",
    "confidence":     0.35,
    "svg_file":       "wildflower.svg",
    "detected":       True,
    "notes":          "Hindi ma-identify. I-focus ang bulaklak sa gitna ng frame.",
}


# ─────────────────────────────────────────────
#  RGB → HSV (numpy only, no cv2)
# ─────────────────────────────────────────────
def rgb_to_hsv(p):
    """p: (H,W,3) float32 0-1. Returns hue 0-360, sat 0-255, val 0-255."""
    r, g, b   = p[:,:,0], p[:,:,1], p[:,:,2]
    maxc      = np.maximum(np.maximum(r, g), b)
    delta     = maxc - np.minimum(np.minimum(r, g), b)
    hue       = np.zeros_like(maxc)
    mr = (maxc == r) & (delta > 0)
    mg = (maxc == g) & (delta > 0)
    mb = (maxc == b) & (delta > 0)
    hue[mr]   = (60 * ((g[mr] - b[mr]) / delta[mr])) % 360
    hue[mg]   = (60 * ((b[mg] - r[mg]) / delta[mg]) + 120) % 360
    hue[mb]   = (60 * ((r[mb] - g[mb]) / delta[mb]) + 240) % 360
    sat       = np.where(maxc > 0, (delta / maxc) * 255, 0)
    val       = maxc * 255
    return hue, sat, val


# ─────────────────────────────────────────────
#  Main detection function
# ─────────────────────────────────────────────
def detect_flower_by_color(image_bytes: bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # ── Crop center 55% — ignore edges (background, hands, clothing) ──────
    w, h   = img.size
    cx, cy = w // 2, h // 2
    cw, ch = int(w * 0.55), int(h * 0.55)
    img    = img.crop((cx - cw//2, cy - ch//2, cx + cw//2, cy + ch//2))
    img    = img.resize((150, 150), Image.LANCZOS)

    pixels = np.array(img, dtype=np.float32) / 255.0
    hue, sat, val = rgb_to_hsv(pixels)

    # ── Background / noise masks ──────────────────────────────────────────
    is_white = (sat < 45)  & (val > 185)                          # paper/white bg
    is_dark  =               (val < 25)                           # black/shadow
    is_green = (hue >= 65)  & (hue <= 165) & (sat > 35)          # leaves/grass
    is_skin  = (hue >= 5)   & (hue <= 25)  & (sat > 20) & (sat < 110) & (val > 150)
    is_blue  = (hue >= 185) & (hue <= 260) & (sat > 40)          # clothing/bg

    valid       = ~is_white & ~is_dark & ~is_green & ~is_skin & ~is_blue
    valid_count = int(np.sum(valid))

    print(f"[detect] valid px={valid_count} | white={int(np.sum(is_white))} "
          f"green={int(np.sum(is_green))} skin={int(np.sum(is_skin))} blue={int(np.sum(is_blue))}")

    if valid_count < 80:
        return None

    vh = hue[valid]
    vs = sat[valid]
    vv = val[valid]

    # ── Score each flower ─────────────────────────────────────────────────
    scores = {}
    for name, hue_ranges, sat_min, val_min, val_max, priority in FLOWER_COLORS:
        in_hue = np.zeros(valid_count, dtype=bool)
        for hmin, hmax in hue_ranges:
            in_hue |= (vh >= hmin) & (vh <= hmax)
        matched      = int(np.sum(in_hue & (vs >= sat_min) & (vv >= val_min) & (vv <= val_max)))
        ratio        = matched / valid_count
        scores[name] = (ratio * (1 + priority * 0.08), ratio, matched)

    top = sorted(scores.items(), key=lambda x: -x[1][0])[:4]
    print("[detect] scores:", {k: f"{v[0]:.3f}(r={v[1]:.3f},px={v[2]})" for k,v in top})

    best        = max(scores, key=lambda k: scores[k][0])
    best_score, best_ratio, best_px = scores[best]

    # Minimum threshold
    if best_ratio < 0.04 and best_px < 6:
        print(f"[detect] Score too low ({best_score:.3f}), fallback.")
        return None

    # ── Dominant color from valid pixels ──────────────────────────────────
    raw    = (pixels * 255).astype(np.uint8)
    flat_r = raw[:,:,0][valid]
    flat_g = raw[:,:,1][valid]
    flat_b = raw[:,:,2][valid]
    dom    = f"#{int(np.mean(flat_r)):02X}{int(np.mean(flat_g)):02X}{int(np.mean(flat_b)):02X}"

    conf = min(0.95, max(0.38, best_score * 3.2))
    print(f"[detect] ✅ {best} | conf={conf:.2f} | color={dom}")

    return {
        "flower_type":    best,
        "confidence":     round(conf, 2),
        "dominant_color": dom,
        "notes":          f"{best} detected based on petal color analysis.",
    }


# ─────────────────────────────────────────────
#  API: POST /api/detect/
# ─────────────────────────────────────────────
@csrf_exempt
@require_POST
def detect_flower(request):
    image_file = request.FILES.get("file")
    if not image_file:
        return JsonResponse({"error": "No image provided."}, status=400)

    image_bytes = image_file.read()

    try:
        result = detect_flower_by_color(image_bytes)

        if result is None:
            return JsonResponse(FALLBACK_RESULT)

        ftype = result["flower_type"]
        info  = FLOWER_MAP.get(ftype, FLOWER_MAP["Wildflower"])

        return JsonResponse({
            "detected":       True,
            "flower_type":    ftype,
            "confidence":     result["confidence"],
            "matched_color":  info["matched_color"],
            "dominant_color": result["dominant_color"],
            "svg_file":       info["svg_file"],
            "notes":          result["notes"],
        })

    except Exception as exc:
        import traceback; traceback.print_exc()
        print(f"[detect_flower] ❌ {exc}")
        return JsonResponse(FALLBACK_RESULT)


# ─────────────────────────────────────────────
#  Save bouquet
# ─────────────────────────────────────────────
@csrf_exempt
@require_POST
def save_bouquet(request):
    try:
        data = json.loads(request.body)
        return JsonResponse({"status": "saved", "id": f"bouquet-{random.randint(1000,9999)}"})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)
