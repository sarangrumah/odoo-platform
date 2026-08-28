"""Generate the placeholder Lottie mascot.

Four segments on one timeline at 60fps, so the widget can jump between them
with playSegments() and the designer's file only has to keep the same marker
frames to drop in as a replacement:

    idle       0 -  59
    listening 60 - 119
    thinking 120 - 179
    talking   180 - 239
"""
import json

FR = 60
SEGMENTS = [("idle", 0), ("listening", 60), ("thinking", 120), ("talking", 180)]
OP = 240
W = H = 200

INDIGO = [0.353, 0.353, 0.867, 1]      # reads on both light and dark surfaces
INDIGO_DARK = [0.243, 0.243, 0.694, 1]
WHITE = [1, 1, 1, 1]
NEAR_BLACK = [0.11, 0.11, 0.18, 1]


def val(k):
    return {"a": 0, "k": k}


def anim(frames):
    """frames: [(t, value), ...] with a smooth ease between them."""
    out = []
    for i, (t, v) in enumerate(frames):
        kf = {"t": t, "s": v if isinstance(v, list) else [v]}
        if i < len(frames) - 1:
            kf["i"] = {"x": [0.4], "y": [1]}
            kf["o"] = {"x": [0.6], "y": [0]}
        out.append(kf)
    return {"a": 1, "k": out}


def ellipse(size, pos, colour, extra=None):
    it = [
        {"ty": "el", "p": val(pos), "s": val(size) if isinstance(size, list) else size, "nm": "e"},
        {"ty": "fl", "c": val(colour), "o": val(100), "r": 1, "nm": "f"},
        {"ty": "tr", "p": val([0, 0]), "a": val([0, 0]), "s": val([100, 100]),
         "r": val(0), "o": val(100)},
    ]
    if extra:
        it[2].update(extra)
    return {"ty": "gr", "it": it, "nm": "g"}


def rect(size, pos, colour, radius=0):
    return {"ty": "gr", "nm": "g", "it": [
        {"ty": "rc", "p": val(pos), "s": size if isinstance(size, dict) else val(size),
         "r": val(radius), "nm": "r"},
        {"ty": "fl", "c": val(colour), "o": val(100), "r": 1, "nm": "f"},
        {"ty": "tr", "p": val([0, 0]), "a": val([0, 0]), "s": val([100, 100]),
         "r": val(0), "o": val(100)},
    ]}


def layer(ind, name, shapes, *, pos=[100, 100, 0], scale=None, rot=None,
          opacity=None, ip=0, op=OP, anchor=[0, 0, 0]):
    return {
        "ddd": 0, "ind": ind, "ty": 4, "nm": name, "sr": 1, "ao": 0, "bm": 0,
        "ks": {
            "o": opacity or val(100),
            "r": rot or val(0),
            "p": pos if isinstance(pos, dict) else val(pos),
            "a": val(anchor),
            "s": scale or val([100, 100, 100]),
        },
        "shapes": shapes, "ip": ip, "op": op, "st": 0,
    }


layers = []
ind = 0


def add(*args, **kwargs):
    global ind
    ind += 1
    layers.append(layer(ind, *args, **kwargs))


# --- talking: mouth, only on its own segment ---------------------------------
add("mouth", [ellipse([34, 34], [0, 0], NEAR_BLACK)],
    pos=[100, 126, 0], ip=180, op=OP,
    scale=anim([(180, [100, 20, 100]), (190, [100, 90, 100]), (200, [100, 30, 100]),
                (210, [100, 100, 100]), (220, [100, 25, 100]), (232, [100, 80, 100]),
                (239, [100, 20, 100])]))

# a closed, resting mouth for every other segment
add("mouth-rest", [rect([34, 6], [0, 0], NEAR_BLACK, radius=3)],
    pos=[100, 126, 0], ip=0, op=180)

# --- thinking: three dots orbiting above the head ----------------------------
for i, dx in enumerate((-18, 0, 18)):
    add(f"think-{i}", [ellipse([12, 12], [0, 0], INDIGO_DARK)],
        pos=[100 + dx, 34, 0], ip=120, op=180,
        scale=anim([(120 + i * 6, [60, 60, 100]), (135 + i * 6, [130, 130, 100]),
                    (150 + i * 6, [60, 60, 100]), (165 + i * 6, [110, 110, 100]),
                    (179, [60, 60, 100])]),
        opacity=anim([(120, 0), (128, 100), (172, 100), (179, 0)]))

# --- eyes --------------------------------------------------------------------
# One blink per idle loop, and wide-open during listening.
for i, dx in enumerate((-24, 24)):
    add(f"eye-{i}", [ellipse([20, 22], [0, 0], NEAR_BLACK)],
        pos=[100 + dx, 96, 0],
        scale=anim([(0, [100, 100, 100]), (40, [100, 100, 100]), (44, [100, 8, 100]),
                    (48, [100, 100, 100]), (60, [100, 118, 100]), (119, [100, 118, 100]),
                    (120, [100, 100, 100]), (150, [100, 100, 100]), (154, [100, 12, 100]),
                    (158, [100, 100, 100]), (239, [100, 100, 100])]))

# --- listening: antenna tips forward -----------------------------------------
add("antenna-tip", [ellipse([16, 16], [0, 0], INDIGO_DARK)],
    pos=anim([(0, [100, 40, 0]), (30, [100, 36, 0]), (60, [100, 40, 0]),
              (75, [112, 34, 0]), (95, [88, 34, 0]), (119, [100, 40, 0]),
              (239, [100, 40, 0])]))
add("antenna-stem", [rect([5, 22], [0, 11], INDIGO_DARK, radius=2)],
    pos=[100, 40, 0], anchor=[0, 22, 0],
    rot=anim([(0, 0), (60, 0), (75, 12), (95, -12), (119, 0), (239, 0)]))

# --- body: breathing squash, a bounce when talking ---------------------------
add("body", [ellipse([120, 112], [0, 0], INDIGO)],
    pos=[100, 108, 0],
    scale=anim([(0, [100, 100, 100]), (30, [103, 97, 100]), (60, [100, 100, 100]),
                (90, [102, 98, 100]), (119, [100, 100, 100]), (120, [100, 100, 100]),
                (150, [98, 102, 100]), (179, [100, 100, 100]), (195, [104, 96, 100]),
                (215, [98, 103, 100]), (239, [100, 100, 100])]))

doc = {
    "v": "5.7.4", "fr": FR, "ip": 0, "op": OP, "w": W, "h": H,
    "nm": "Cockpit mascot", "ddd": 0, "assets": [],
    "layers": layers,
    "markers": [{"tm": t, "cm": name, "dr": 60} for name, t in SEGMENTS],
}

with open("public/mascot/mascot.json", "w") as fh:
    json.dump(doc, fh, separators=(",", ":"))
    fh.write("\n")
print("layers:", len(layers))
