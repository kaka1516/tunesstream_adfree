#!/usr/bin/env python3
"""Generates Music Stream dancer art (original work, CC0 by the author for this project).
Outputs: parts/<char>/*.svg, characters/<char>/{character.json,moveset.json,preview.svg},
moves/*.json, rig.json, contact.html. Re-run safe. Pure stdlib."""
import json, math, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def W(p, s):
    p = os.path.join(ROOT, p); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w').write(s)

# ---------- rig (character space: hip=origin, y down, px at 1x) ----------
RIG = {
  "units": "px@1x, y down, hip at (0,0), ground y=+60",
  "angleConvention": "degrees, SVG clockwise-positive for L (screen-left) joints; *R joints are mirrored: renderer uses -angle so +value always means 'away from body / outward-up'. torso/head/root.rot: +clockwise (lean screen-right).",
  "bounds": {"x": [-110, 110], "y": [-178, 70]},
  "joints": {
    "root":  {"parent": None,    "pivot": [0, 0]},
    "torso": {"parent": "root",  "pivot": [0, 0]},
    "head":  {"parent": "torso", "pivot": [0, -58]},
    "uarmL": {"parent": "torso", "pivot": [-20, -50]}, "larmL": {"parent": "uarmL", "pivot": [0, 24]}, "handL": {"parent": "larmL", "pivot": [0, 22]},
    "uarmR": {"parent": "torso", "pivot": [20, -50], "mirror": True}, "larmR": {"parent": "uarmR", "pivot": [0, 24], "mirror": True}, "handR": {"parent": "larmR", "pivot": [0, 22], "mirror": True},
    "thighL": {"parent": "root", "pivot": [-11, 0]}, "shinL": {"parent": "thighL", "pivot": [0, 26]},
    "thighR": {"parent": "root", "pivot": [11, 0], "mirror": True}, "shinR": {"parent": "thighR", "pivot": [0, 26], "mirror": True}
  },
  "drawOrder": ["hair_back","acc_back","thighR","shinR","thighL","shinL","torso","uarmR","larmR","handR","head","face","hair_front","acc_front","uarmL","larmL","handL"],
  "zRules": ["if uarmR > 120: move uarmR/larmR/handR after acc_front (raised back arm in front of head)"],
  "partFiles": "parts/<char>/<part>.svg; L/R share one file (R drawn with scale(-1,1) at its pivot). Each file's viewBox is in part-local coords with the pivot at (0,0).",
  "partViewBox": {"torso": [-34,-66,68,72], "head": [-48,-86,96,92], "face": [-48,-86,96,92], "hair_back": [-60,-100,120,120],
                  "hair_front": [-60,-100,120,120], "uarm": [-10,-8,20,36], "larm": [-9,-4,18,30], "thigh": [-12,-4,24,34],
                  "shin": [-14,-4,30,40], "acc_back": [-60,-100,120,170], "acc_front": [-60,-100,120,170],
                  "hand_open": [-9,-3,18,16], "hand_fist": [-9,-3,18,14], "hand_point": [-9,-3,18,22], "hand_flick": [-11,-3,22,16]},
  "attach": {"hair_back": "head", "hair_front": "head", "face": "head", "acc_back": "torso", "acc_front": "torso"},
  "hands": ["open","fist","point","flick"], "faces": ["smile","grin","closed","wink"],
  "paletteSlots": ["--d-skin","--d-skin-sh","--d-hair","--d-main","--d-alt","--d-trim","--d-line","--d-eye","--d-blush"]
}
S = lambda var, fb: f"var({var},{fb})"
def svg(vb, body, title):
    x,y,w,h = vb
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {w} {h}" width="{w*2}" height="{h*2}">'
            f'<title>{title} — Music Stream dancer part (original, CC0)</title>'
            f'<g id="part" data-pivot="0,0" stroke-linejoin="round" stroke-linecap="round">{body}</g></svg>\n')

CHARS = {
 "tara": {"name":"Tara","home":"tollywood","tag":"Telugu-film mass-dance lead: high ponytail, mirror-dot cropped jacket, flared pants",
   "pal":{"--d-skin":"#c98b5f","--d-skin-sh":"#a86f48","--d-hair":"#1d1420","--d-main":"#e2384d","--d-alt":"#ffb627","--d-trim":"#f4d35e","--d-line":"#24161c","--d-eye":"#2a1a12","--d-blush":"#f08a7e"}},
 "kavi": {"name":"Kavi","home":"kollywood","tag":"Tamil-film kuthu dancer: curly mop, checked shirt, shoulder towel-scarf, shorts, sneakers",
   "pal":{"--d-skin":"#8d5a3b","--d-skin-sh":"#6f4329","--d-hair":"#120d0b","--d-main":"#1f8a70","--d-alt":"#f2e8cf","--d-trim":"#ff7f11","--d-line":"#140e0a","--d-eye":"#120d0b","--d-blush":"#c8705a"}},
 "rivo": {"name":"Rivo","home":"hollywood","tag":"Western pop/hip-hop/EDM dancer: spiky hair + visor, oversized hoodie, neck headphones, joggers",
   "pal":{"--d-skin":"#f0c9a6","--d-skin-sh":"#d9a882","--d-hair":"#6c3df0","--d-main":"#20232f","--d-alt":"#3df0c2","--d-trim":"#ff3d9a","--d-line":"#0e0f14","--d-eye":"#0e0f14","--d-blush":"#f39a9a"}},
}
L = S("--d-line","#222"); SK = S("--d-skin","#d9a07a"); SKS = S("--d-skin-sh","#b57f5a")
HAIR = S("--d-hair","#222"); MAIN = S("--d-main","#e33"); ALT = S("--d-alt","#fb2"); TRIM = S("--d-trim","#fd5")
EYE = S("--d-eye","#222"); BL = S("--d-blush","#f99")
st = lambda f, w=2.5: f'style="fill:{f};stroke:{L};stroke-width:{w}"'
nost = lambda f: f'style="fill:{f}"'

def parts(cid):
    P = {}
    # --- shared anatomy ---
    P["head"] = (f'<path {st(SK)} d="M0,-4 L-6,-4 L-6,-10 L6,-10 L6,-4 Z"/>'  # neck
                 f'<ellipse cx="0" cy="-42" rx="38" ry="35" {st(SK,3)}/>'
                 f'<ellipse cx="-38" cy="-38" rx="6" ry="8" {st(SK)}/><ellipse cx="38" cy="-38" rx="6" ry="8" {st(SK)}/>')
    eyes = lambda kind: {
      "open": f'<ellipse cx="-14" cy="-36" rx="5.5" ry="7.5" {nost(EYE)}/><ellipse cx="14" cy="-36" rx="5.5" ry="7.5" {nost(EYE)}/>'
              f'<circle cx="-12" cy="-39" r="2.2" fill="#fff"/><circle cx="16" cy="-39" r="2.2" fill="#fff"/>',
      "closed": f'<path d="M-20,-36 Q-14,-30 -8,-36" style="fill:none;stroke:{EYE};stroke-width:2.6"/><path d="M8,-36 Q14,-30 20,-36" style="fill:none;stroke:{EYE};stroke-width:2.6"/>',
      "wink": f'<ellipse cx="-14" cy="-36" rx="5.5" ry="7.5" {nost(EYE)}/><circle cx="-12" cy="-39" r="2.2" fill="#fff"/><path d="M8,-35 L20,-37" style="fill:none;stroke:{EYE};stroke-width:2.8"/>'}[kind]
    blush = f'<ellipse cx="-22" cy="-24" rx="6" ry="3" {nost(BL)} opacity=".7"/><ellipse cx="22" cy="-24" rx="6" ry="3" {nost(BL)} opacity=".7"/>'
    mouths = {"smile": f'<path d="M-6,-20 Q0,-14 6,-20" style="fill:none;stroke:{L};stroke-width:2.2"/>',
              "grin": f'<path d="M-8,-21 Q0,-10 8,-21 Z" style="fill:#7a2230;stroke:{L};stroke-width:2"/>'}
    P["face_smile"] = eyes("open") + blush + mouths["smile"]
    P["face_grin"] = eyes("open") + blush + mouths["grin"]
    P["face_closed"] = eyes("closed") + blush + mouths["smile"]
    P["face_wink"] = eyes("wink") + blush + mouths["grin"]
    P["larm"] = f'<path {st(SK)} d="M-5,0 L5,0 L4.5,22 L-4.5,22 Z"/>'
    P["hand_open"] = f'<path {st(SK,2)} d="M-6,0 Q-8,8 -4,12 L-2,9 L0,13 L2,9 L4,12 Q8,8 6,0 Z"/>'
    P["hand_fist"] = f'<circle cx="0" cy="5" r="7" {st(SK,2)}/>'
    P["hand_point"] = f'<circle cx="0" cy="5" r="6.5" {st(SK,2)}/><path {st(SK,2)} d="M-2,9 L-2,18 Q0,20 2,18 L2,9 Z"/>'
    P["hand_flick"] = f'<path {st(SK,2)} d="M-6,0 Q-9,6 -9,10 L-3,8 L0,12 L3,8 L9,10 Q9,6 6,0 Z"/>'
    if cid == "tara":
        P["torso"] = (f'<path {st(ALT)} d="M-15,-2 L15,-2 L13,-30 L-13,-30 Z"/>'          # top / midriff band
                      f'<path {st(MAIN,3)} d="M-22,-58 Q0,-64 22,-58 L24,-30 Q0,-24 -24,-30 Z"/>'  # cropped jacket
                      f'<path d="M0,-60 L0,-28" style="stroke:{L};stroke-width:2"/>'
                      + ''.join(f'<circle cx="{x}" cy="{y}" r="2.2" {nost(TRIM)}/>' for x,y in [(-14,-48),(-8,-38),(-16,-36),(14,-48),(8,-38),(16,-36)])
                      + f'<path {st(MAIN)} d="M-18,-4 L18,-4 L19,4 L-19,4 Z"/>')   # waistband
        P["uarm"] = f'<path {st(MAIN)} d="M-7,-4 Q0,-8 7,-4 L6,26 L-6,26 Z"/><path d="M-6,22 L6,22" style="stroke:{TRIM};stroke-width:2.5"/>'
        P["thigh"] = f'<path {st(MAIN)} d="M-9,-2 L9,-2 L10,28 L-10,28 Z"/>'
        P["shin"] = (f'<path {st(MAIN)} d="M-10,0 L10,0 L14,24 L-14,24 Z"/><path d="M-13,20 L13,20" style="stroke:{TRIM};stroke-width:2.5"/>'
                     f'<path {st(ALT)} d="M-9,25 L11,25 Q14,32 8,33 L-9,33 Z"/>')
        P["hair_back"] = (f'<path {st(HAIR,3)} d="M-40,-40 Q-44,-84 0,-84 Q44,-84 40,-40 L36,-20 L-36,-20 Z"/>'
                          f'<path {st(HAIR,3)} d="M4,-82 Q30,-118 52,-96 Q60,-70 44,-46 Q52,-76 30,-90 Z"/>')   # high ponytail sweep
        P["hair_front"] = (f'<path {st(HAIR,3)} d="M-38,-48 Q-34,-82 0,-80 Q34,-82 38,-48 Q26,-62 14,-58 Q8,-70 -2,-60 Q-14,-70 -20,-56 Q-30,-62 -38,-48 Z"/>'
                           f'<circle cx="18" cy="-78" r="6" {st(TRIM,2)}/>')
        P["acc_back"] = ""
        P["acc_front"] = (f'<g transform="translate(0,-58)"><path d="M-38,-30 L-38,-20" style="stroke:{TRIM};stroke-width:2"/><path {st(TRIM,1.5)} d="M-43,-20 L-33,-20 L-38,-10 Z"/>'
                          f'<path d="M38,-30 L38,-20" style="stroke:{TRIM};stroke-width:2"/><path {st(TRIM,1.5)} d="M33,-20 L43,-20 L38,-10 Z"/></g>')  # drop earrings (head-relative offset baked)
    elif cid == "kavi":
        chk = ''.join(f'<path d="M{x},-58 L{x},-4" style="stroke:{ALT};stroke-width:2;opacity:.55"/>' for x in (-14,-5,5,14)) + \
              ''.join(f'<path d="M-22,{y} L22,{y}" style="stroke:{ALT};stroke-width:2;opacity:.55"/>' for y in (-46,-32,-18))
        P["torso"] = (f'<path {st(MAIN,3)} d="M-22,-58 Q0,-64 22,-58 L20,-2 L-20,-2 Z"/>' + chk +
                      f'<path {st(ALT,2)} d="M-6,-60 L0,-50 L6,-60 Z"/>'
                      f'<path {st(SKS,1.5)} d="M-20,-4 L20,-4 L21,4 L-21,4 Z"/>')
        P["uarm"] = f'<path {st(MAIN)} d="M-7,-4 Q0,-8 7,-4 L6,16 L-6,16 Z"/><path {st(SK)} d="M-5,16 L5,16 L5,26 L-5,26 Z"/>'  # rolled sleeve
        P["thigh"] = f'<path {st(ALT)} d="M-10,-2 L10,-2 L11,24 L-11,24 Z"/><path d="M-11,18 L11,18" style="stroke:{MAIN};stroke-width:3"/>'
        P["shin"] = (f'<path {st(SK)} d="M-5,-2 L5,-2 L5,24 L-5,24 Z"/>'
                     f'<path {st("#fafafa")} d="M-9,22 L11,22 Q15,32 8,33 L-9,33 Z"/><path d="M-8,29 L12,29" style="stroke:{TRIM};stroke-width:2.5"/>')
        P["hair_back"] = f'<path {st(HAIR,3)} d="M-42,-36 Q-50,-90 0,-88 Q50,-90 42,-36 Z"/>'
        P["hair_front"] = ''.join(f'<circle cx="{x}" cy="{y}" r="{r}" {st(HAIR,2.5)}/>' for x,y,r in
                                  [(-30,-62,12),(-14,-74,13),(4,-78,13),(22,-72,12),(34,-58,10),(-2,-64,9),(16,-62,8)])
        P["acc_back"] = ""
        P["acc_front"] = (f'<path {st(TRIM,2.5)} d="M-24,-60 Q-6,-66 14,-60 L10,-52 Q-6,-56 -18,-52 L-14,-14 L-24,-12 Z"/>'   # towel over shoulder
                          f'<path d="M-23,-20 L-15,-21 M-22,-16 L-14,-17" style="stroke:{ALT};stroke-width:2"/>')
    else:  # rivo
        P["torso"] = (f'<path {st(MAIN,3)} d="M-26,-58 Q0,-66 26,-58 L28,2 Q0,8 -28,2 Z"/>'
                      f'<path {st(ALT,2)} d="M-12,-30 L12,-30 L10,-14 L-10,-14 Z"/>'             # front pocket
                      f'<path d="M-6,-58 L-8,-40 M6,-58 L8,-40" style="stroke:{ALT};stroke-width:2"/>'
                      f'<path {st(MAIN,2)} d="M-28,-4 L28,-4 L28,4 L-28,4 Z"/>')
        P["uarm"] = f'<path {st(MAIN)} d="M-9,-5 Q0,-10 9,-5 L8,26 L-8,26 Z"/>'
        P["larm"] = f'<path {st(SK)} d="M-5,0 L5,0 L4.5,22 L-4.5,22 Z"/><path {st(MAIN)} d="M-8,-2 L8,-2 L7,8 L-7,8 Z"/><path d="M-7,8 L7,8" style="stroke:{ALT};stroke-width:2"/>'
        P["thigh"] = f'<path {st("#3a3f52")} d="M-10,-2 L10,-2 L9,28 L-9,28 Z"/><path d="M-9,4 L-8,26" style="stroke:{ALT};stroke-width:2"/>'
        P["shin"] = (f'<path {st("#3a3f52")} d="M-9,0 L9,0 L7,22 L-7,22 Z"/>'
                     f'<path {st(ALT)} d="M-11,20 L13,20 Q17,34 9,35 L-11,35 Z"/><path d="M-10,30 L15,30" style="stroke:{L};stroke-width:2"/>')
        P["hair_back"] = f'<path {st(HAIR,3)} d="M-40,-36 Q-46,-84 0,-86 Q46,-84 40,-36 Z"/>'
        P["hair_front"] = (f'<path {st(HAIR,3)} d="M-40,-52 L-46,-80 L-24,-72 L-20,-98 L-2,-80 L8,-102 L18,-78 L40,-92 L36,-66 L48,-58 L38,-50 Q0,-66 -40,-52 Z"/>'
                           f'<path {st(TRIM,2.5)} d="M-38,-56 Q0,-72 38,-56 L40,-50 Q0,-64 -40,-50 Z"/>')   # visor band
        P["acc_back"] = ""
        P["acc_front"] = (f'<path d="M-20,-60 Q0,-46 20,-60" style="fill:none;stroke:{L};stroke-width:4"/>'
                          f'<rect x="-27" y="-66" width="12" height="16" rx="5" {st(TRIM,2.5)}/><rect x="15" y="-66" width="12" height="16" rx="5" {st(TRIM,2.5)}/>')
    return P

# ---------- moves (pose JSON) ----------
def K(t, **j): j["t"] = t; return j
N = dict(torso=0, head=0, uarmL=12, larmL=-8, uarmR=12, larmR=-8, thighL=4, shinL=-2, thighR=4, shinR=-2)
def pose(t, ease="inOut", **over):
    p = dict(N); p.update(over); p["t"] = t; p["ease"] = ease; return p
bend = dict(thighL=14, shinL=-22, thighR=14, shinR=-22)  # front-view knee dip (pair with root.y +5)
MOVES = {
 # ----- Hollywood: western pop / hip-hop / EDM -----
 "hw_bounce_step": ("Bounce two-step", "hollywood", 2, [pose(0, rootY=0, rootX=-6, torso=-4, face="smile"), pose(.25, rootY=5, rootX=-3, **bend), pose(.5, rootY=0, rootX=6, torso=4), pose(.75, rootY=5, rootX=3, **bend)]),
 "hw_body_roll": ("Body roll wave", "hollywood", 2, [pose(0, torso=-10, head=6, rootX=-4), pose(.33, torso=0, head=-6, rootY=4, **bend), pose(.66, torso=10, head=6, rootX=4), pose(1, torso=-10, head=6, rootX=-4)]),
 "hw_arm_wave": ("Arm wave", "hollywood", 2, [pose(0, uarmL=90, larmL=20, uarmR=90, larmR=-20), pose(.25, uarmL=95, larmL=-20, uarmR=85, larmR=20, torso=-4), pose(.5, uarmL=90, larmL=20, uarmR=90, larmR=-20), pose(.75, uarmL=85, larmL=-20, uarmR=95, larmR=20, torso=4)]),
 "hw_fist_pump": ("Fist pump", "hollywood", 1, [pose(0, uarmR=150, larmR=10, gripR="fist", rootY=0, face="grin"), pose(.5, uarmR=120, larmR=60, gripR="fist", rootY=5, ease="snap", **bend)]),
 "hw_shuffle_kick": ("Shuffle kick", "hollywood", 1, [pose(0, thighL=30, shinL=-10, thighR=-6, rootX=-3, uarmL=30, uarmR=30, ease="snap"), pose(.5, thighR=30, shinR=-10, thighL=-6, rootX=3, uarmL=30, uarmR=30, ease="snap")]),
 "hw_step_clap": ("Step clap", "hollywood", 2, [pose(0, rootX=-6, uarmL=40, larmL=70, uarmR=40, larmR=70, gripL="open", gripR="open"), pose(.25, rootX=-6, uarmL=20, larmL=95, uarmR=20, larmR=95, ease="snap", rootY=3), pose(.5, rootX=6, uarmL=40, larmL=70, uarmR=40, larmR=70), pose(.75, rootX=6, uarmL=20, larmL=95, uarmR=20, larmR=95, ease="snap", rootY=3)]),
 "hw_shoulder_bop": ("Shoulder bop", "hollywood", 1, [pose(0, torso=-6, head=4, uarmL=20, uarmR=8, rootY=2), pose(.5, torso=6, head=-4, uarmL=8, uarmR=20, rootY=2)]),
 "hw_drop_point": ("Drop point (one-shot)", "hollywood", 2, [pose(0, rootY=8, **bend, uarmL=10, uarmR=10, face="closed"), pose(.3, uarmR=160, larmR=0, gripR="point", rootY=-4, face="grin", ease="snap"), pose(1, uarmR=160, larmR=0, gripR="point", face="grin")]),
 # ----- Tollywood: Telugu-film mass style (original generic poses) -----
 "tl_mass_stomp": ("Mass stomp", "tollywood", 2, [pose(0, thighL=28, shinL=-20, thighR=10, uarmL=30, larmL=40, uarmR=30, larmR=40, gripL="fist", gripR="fist", rootY=6, face="grin"), pose(.25, thighL=10, shinL=0, rootY=-2, ease="snap"), pose(.5, thighR=28, shinR=-20, thighL=10, uarmL=30, larmL=40, uarmR=30, larmR=40, gripL="fist", gripR="fist", rootY=6), pose(.75, thighR=10, shinR=0, rootY=-2, ease="snap")]),
 "tl_hook_loop": ("Hook loop (hand-over-head + hip bounce)", "tollywood", 2, [pose(0, uarmR=150, larmR=70, gripR="flick", uarmL=40, larmL=100, rootX=-5, torso=-6, face="wink"), pose(.25, uarmR=160, larmR=95, rootX=5, torso=6, rootY=4, uarmL=40, larmL=100, ease="snap"), pose(.5, uarmR=150, larmR=70, gripR="flick", uarmL=40, larmL=100, rootX=-5, torso=-6), pose(.75, uarmR=160, larmR=95, rootX=5, torso=6, rootY=4, uarmL=40, larmL=100, ease="snap")]),
 "tl_fast_footwork": ("Fast heel-toe footwork", "tollywood", 1, [pose(0, thighL=-10, shinL=12, thighR=18, shinR=-14, rootX=-2, uarmL=25, uarmR=25, ease="snap"), pose(.25, thighL=18, shinL=-14, thighR=-10, shinR=12, rootX=2, ease="snap"), pose(.5, thighL=-10, shinL=12, thighR=18, shinR=-14, rootX=-2, ease="snap"), pose(.75, thighL=18, shinL=-14, thighR=-10, shinR=12, rootX=2, ease="snap")]),
 "tl_shoulder_shake": ("Shoulder shake", "tollywood", 1, [pose(0, uarmL=28, uarmR=4, torso=-5, rootY=2, ease="snap"), pose(.25, uarmL=4, uarmR=28, torso=5, ease="snap"), pose(.5, uarmL=28, uarmR=4, torso=-5, rootY=2, ease="snap"), pose(.75, uarmL=4, uarmR=28, torso=5, ease="snap")]),
 "tl_collar_flick": ("Collar flick + point out", "tollywood", 2, [pose(0, uarmR=40, larmR=150, gripR="flick", head=-8, face="wink"), pose(.4, uarmR=110, larmR=0, gripR="point", head=6, rootX=4, ease="snap", face="grin"), pose(1, uarmR=110, larmR=0, gripR="point")]),
 "tl_slide_point": ("Side slide + point", "tollywood", 2, [pose(0, rootX=-10, thighL=24, uarmL=95, larmL=0, gripL="point", torso=-6), pose(.5, rootX=10, thighR=24, uarmR=95, larmR=0, gripR="point", torso=6)]),
 "tl_victory_v": ("Victory V hit (one-shot)", "tollywood", 2, [pose(0, rootY=8, **bend, face="closed"), pose(.25, uarmL=150, larmL=10, uarmR=150, larmR=10, gripL="fist", gripR="fist", thighL=20, thighR=20, rootY=0, face="grin", ease="snap"), pose(1, uarmL=150, larmL=10, uarmR=150, larmR=10, gripL="fist", gripR="fist", thighL=20, thighR=20, face="grin")]),
 # ----- Kollywood: Tamil-film kuthu / folk-inflected (original generic poses) -----
 "kl_kuthu_step": ("Kuthu knee-lift stomp", "kollywood", 2, [pose(0, thighL=-40, shinL=60, uarmL=50, larmL=70, uarmR=30, larmR=90, rootY=-2, torso=4, face="grin"), pose(.25, rootY=6, **bend, ease="snap"), pose(.5, thighR=-40, shinR=60, uarmR=50, larmR=70, uarmL=30, larmL=90, rootY=-2, torso=-4), pose(.75, rootY=6, **bend, ease="snap")]),
 "kl_drum_mime": ("Frame-drum mime", "kollywood", 1, [pose(0, uarmL=40, larmL=110, uarmR=35, larmR=60, gripL="fist", gripR="open", rootY=0), pose(.5, uarmL=35, larmL=60, uarmR=40, larmR=110, gripL="open", gripR="fist", rootY=4, ease="snap", **bend)]),
 "kl_folk_hip_sway": ("Folk hip sway + wrist flourish", "kollywood", 2, [pose(0, rootX=-7, torso=8, uarmL=70, larmL=60, uarmR=20, larmR=80, gripL="open", gripR="open", face="closed"), pose(.5, rootX=7, torso=-8, uarmL=20, larmL=80, uarmR=70, larmR=60, gripL="open", gripR="open"), pose(1, rootX=-7, torso=8, uarmL=70, larmL=60, uarmR=20, larmR=80, face="closed")]),
 "kl_wrist_flick": ("Overhead wrist flicks", "kollywood", 1, [pose(0, uarmL=150, larmL=40, uarmR=150, larmR=40, gripL="flick", gripR="flick", rootY=2), pose(.5, uarmL=145, larmL=70, uarmR=145, larmR=70, gripL="open", gripR="open", rootY=5, ease="snap")]),
 "kl_mass_entry": ("Mass entry stride (intro, half-time)", "kollywood", 4, [pose(0, rootX=-8, thighL=-18, thighR=14, uarmL=60, larmL=10, uarmR=60, larmR=10, head=-4, face="smile"), pose(.5, rootX=8, thighR=-18, thighL=14, uarmL=70, larmL=10, uarmR=70, larmR=10, head=4), pose(1, rootX=-8, thighL=-18, thighR=14, uarmL=60, larmL=10, uarmR=60, larmR=10, head=-4)]),
 "kl_heel_clap": ("Heel bounce clap", "kollywood", 1, [pose(0, uarmL=30, larmL=80, uarmR=30, larmR=80, rootY=0), pose(.5, uarmL=18, larmL=100, uarmR=18, larmR=100, rootY=4, **bend, ease="snap")]),
 "kl_scarf_twirl": ("Overhead twirl (scarf/hand circle)", "kollywood", 2, [pose(0, uarmR=160, larmR=0, gripR="open", torso=-4), pose(.25, uarmR=140, larmR=60, torso=0), pose(.5, uarmR=160, larmR=0, torso=4), pose(.75, uarmR=140, larmR=-50, torso=0)]),
 # ----- interaction: per-character tap reaction (cheer) + special (long-press / double-tap) -----
 "tara_tap_cheer": ("Tara tap cheer: hop + both-hand flick wave (one-shot)", "tollywood", 1, [pose(0, rootY=6, **bend, face="closed"), pose(.35, rootY=-10, uarmL=140, larmL=40, uarmR=140, larmR=40, gripL="flick", gripR="flick", face="grin", ease="snap"), pose(1, rootY=0, uarmL=120, larmL=60, uarmR=120, larmR=60, face="grin")]),
 "tara_special": ("Tara special: spin-out to mass point pose (one-shot)", "tollywood", 4, [pose(0, rootY=6, **bend), pose(.25, rootRot=-12, torso=-14, uarmL=90, uarmR=90, larmL=0, larmR=0, rootX=-8, ease="snap"), pose(.5, rootRot=12, torso=14, uarmL=90, uarmR=90, rootX=8), pose(.75, rootRot=0, torso=-6, thighL=30, shinL=-20, uarmR=120, larmR=0, gripR="point", uarmL=40, larmL=100, face="wink", ease="snap"), pose(1, torso=-6, thighL=30, shinL=-20, uarmR=120, larmR=0, gripR="point", uarmL=40, larmL=100, face="wink")]),
 "kavi_tap_cheer": ("Kavi tap cheer: double drum-hit + whistle grin (one-shot)", "kollywood", 1, [pose(0, uarmL=40, larmL=110, uarmR=40, larmR=110, gripL="fist", gripR="fist", face="grin"), pose(.25, uarmL=30, larmL=50, uarmR=30, larmR=50, rootY=5, **bend, ease="snap"), pose(.5, uarmL=40, larmL=110, uarmR=40, larmR=110, gripL="fist", gripR="fist"), pose(.75, uarmL=30, larmL=50, uarmR=30, larmR=50, rootY=5, **bend, ease="snap", face="wink")]),
 "kavi_special": ("Kavi special: towel swing overhead + knee-drop stomp finish (one-shot)", "kollywood", 4, [pose(0, uarmR=160, larmR=0, torso=-6), pose(.25, uarmR=140, larmR=70, torso=6, thighL=-40, shinL=60), pose(.5, uarmR=160, larmR=0, torso=-6, thighR=-40, shinR=60), pose(.75, rootY=12, thighL=30, shinL=-40, thighR=30, shinR=-40, uarmL=60, uarmR=60, larmL=0, larmR=0, gripL="open", gripR="open", face="grin", ease="snap"), pose(1, rootY=12, thighL=30, shinL=-40, thighR=30, shinR=-40, uarmL=60, uarmR=60, face="grin")]),
 "rivo_tap_cheer": ("Rivo tap cheer: headphone-tap nod + thumbs-up style fist (one-shot)", "hollywood", 1, [pose(0, uarmL=60, larmL=150, gripL="open", head=8, face="closed"), pose(.4, uarmL=60, larmL=150, head=-6, uarmR=70, larmR=90, gripR="fist", face="grin", ease="snap"), pose(1, uarmR=70, larmR=90, gripR="fist", face="wink")]),
 "rivo_special": ("Rivo special: freeze-hit robot sequence (one-shot)", "hollywood", 4, [pose(0, uarmL=90, larmL=90, uarmR=90, larmR=-90, ease="snap"), pose(.25, uarmL=90, larmL=-90, uarmR=90, larmR=90, head=10, ease="snap"), pose(.5, torso=10, uarmL=170, larmL=0, uarmR=20, larmR=0, rootX=6, ease="snap"), pose(.75, rootY=10, **bend, torso=-8, uarmR=160, larmR=0, gripR="point", face="grin", ease="snap"), pose(1, rootY=10, **bend, torso=-8, uarmR=160, larmR=0, gripR="point", face="grin")]),
 # ----- calm / shared (sad, devotional, low-confidence idle) -----
 "idle_sway": ("Idle sway (fallback groove)", "any", 4, [pose(0, rootX=-3, torso=-3, head=2), pose(.5, rootX=3, torso=3, head=-2), pose(1, rootX=-3, torso=-3, head=2)]),
 "calm_breathe": ("Calm breathe / folded hands", "any", 4, [pose(0, uarmL=25, larmL=120, uarmR=25, larmR=120, gripL="open", gripR="open", face="closed", rootY=0), pose(.5, uarmL=25, larmL=120, uarmR=25, larmR=120, face="closed", rootY=2, head=4), pose(1, uarmL=25, larmL=120, uarmR=25, larmR=120, face="closed", rootY=0)]),
}
MOVESETS = {
 "tara": {"tap": ["tara_tap_cheer"], "special": ["tara_special"], "idle": ["idle_sway"], "calm": ["calm_breathe","hw_body_roll"], "low": ["tl_shoulder_shake","hw_bounce_step"],
          "mid": ["tl_hook_loop","tl_slide_point","tl_collar_flick"], "high": ["tl_mass_stomp","tl_fast_footwork"], "accent": ["tl_victory_v"]},
 "kavi": {"tap": ["kavi_tap_cheer"], "special": ["kavi_special"], "idle": ["idle_sway"], "calm": ["calm_breathe","kl_folk_hip_sway"], "low": ["kl_heel_clap","kl_mass_entry"],
          "mid": ["kl_drum_mime","kl_folk_hip_sway","kl_scarf_twirl"], "high": ["kl_kuthu_step","kl_wrist_flick"], "accent": ["tl_victory_v"]},
 "rivo": {"tap": ["rivo_tap_cheer"], "special": ["rivo_special"], "idle": ["idle_sway"], "calm": ["calm_breathe","hw_body_roll"], "low": ["hw_shoulder_bop","hw_bounce_step"],
          "mid": ["hw_step_clap","hw_arm_wave","hw_body_roll"], "high": ["hw_fist_pump","hw_shuffle_kick"], "accent": ["hw_drop_point"]},
}
STYLE_BORROW = {"tollywood": ["tl_mass_stomp","tl_hook_loop","tl_fast_footwork","tl_shoulder_shake","tl_slide_point"],
                "kollywood": ["kl_kuthu_step","kl_drum_mime","kl_folk_hip_sway","kl_wrist_flick","kl_heel_clap"],
                "hollywood": ["hw_bounce_step","hw_step_clap","hw_arm_wave","hw_fist_pump","hw_shuffle_kick"]}

# ---------- reference composer (same math the runtime must use) ----------
JOINTS = RIG["joints"]
def sample(move, phase):
    keys = MOVES[move][3]; ks = keys + ([dict(keys[0], t=1.0)] if keys[-1]["t"] < 1 else [])
    for a, b in zip(ks, ks[1:]):
        if a["t"] <= phase <= b["t"]:
            u = (phase - a["t"]) / max(1e-6, b["t"] - a["t"])
            u = u*u*(3-2*u) if b.get("ease","inOut") == "inOut" else 1-(1-u)**3
            out = {}
            for k in set(a) | set(b):
                va, vb = a.get(k, N.get(k, 0)), b.get(k, N.get(k, 0))
                out[k] = va + (vb-va)*u if isinstance(va,(int,float)) and isinstance(vb,(int,float)) else (va if u < .5 else vb)
            return out
    return dict(keys[0])
def compose(cid, p, inline_parts):
    def ang(j):
        if j.startswith("hand"): j = "wrist"+j[-1]
        v = p.get(j, 0); v = v if isinstance(v,(int,float)) else 0
        return -v if JOINTS.get(j, JOINTS.get("hand"+j[-1], {})).get("mirror") else v
    def chain(j):
        out = []
        while j:
            px, py = JOINTS[j]["pivot"]
            if j == "root": out.append(f"translate({p.get('rootX',0)},{p.get('rootY',0)}) rotate({p.get('rootRot',0)})")
            else: out.append(f"translate({px},{py}) rotate({ang(j)})")
            j = JOINTS[j]["parent"]
        return " ".join(reversed(out))
    g = []; order = list(RIG["drawOrder"])
    for side in "R":   # z-swap: a raised back arm (>120deg) draws over the head, per rig.zRules
        if p.get("uarm"+side, 0) > 120:
            for s_ in ("uarmR","larmR","handR"): order.remove(s_); order.insert(order.index("acc_front")+1, s_)
    for slot in order:
        if slot in ("hair_back","hair_front","face"):
            j, part = "head", ("face_"+p.get("face","smile") if slot=="face" else slot)
        elif slot in ("acc_back","acc_front"): j, part = "torso", slot
        elif slot.startswith("hand"): j, part = slot, "hand_"+p.get("grip"+slot[-1], "open")
        else: j, part = slot, slot.rstrip("LR")
        body = inline_parts.get(part, "")
        if not body: continue
        mir = " scale(-1,1)" if JOINTS[j].get("mirror") and slot not in ("acc_front","acc_back") else ""
        g.append(f'<g data-part="{slot}" transform="{chain(j)}{mir}">{body}</g>')
    return "".join(g)

def main():
    W("rig.json", json.dumps(RIG, indent=1))
    for mid,(name, style, beats, keys) in MOVES.items():
        W(f"moves/{mid}.json", json.dumps({"id": mid, "name": name, "style": style, "beats": beats, "loop": True,
          "oneShot": "one-shot" in name, "joints": "see rig.json; omitted joints = neutral", "keys": keys}, indent=1))
    cards = []
    for cid, c in CHARS.items():
        P = parts(cid); vb = RIG["partViewBox"]
        for name, body in P.items():
            if not body: continue
            key = "face" if name.startswith("face_") else name
            W(f"parts/{cid}/{name}.svg", svg(vb.get(key, [-60,-100,120,170]), body, f"{c['name']} {name}"))
        W(f"characters/{cid}/character.json", json.dumps({"id": cid, "name": c["name"], "homeStyle": c["home"], "about": c["tag"],
           "palette": c["pal"], "recolor": {"fromAlbumArt": ["--d-main","--d-alt","--d-trim"], "mix": 0.5, "neverFromArt": ["--d-skin","--d-skin-sh","--d-hair"]},
           "parts": sorted(n for n,b in P.items() if b), "moveset": "moveset.json", "license": "CC0-1.0 (original work for Music Stream)"}, indent=1))
        W(f"characters/{cid}/moveset.json", json.dumps({"character": cid, "homeStyle": c["home"], "bands": MOVESETS[cid],
           "borrowWhenStyleDiffers": STYLE_BORROW}, indent=1))
        style = ";".join(f"{k}:{v}" for k,v in c["pal"].items())
        neutral = dict(N, face="smile")
        W(f"characters/{cid}/preview.svg", f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-110 -178 220 248" width="400" height="440" style="{style}">'
          f'<title>{c["name"]} — assembled neutral pose (original, CC0)</title><ellipse cx="0" cy="62" rx="44" ry="6" fill="#000" opacity=".18"/>{compose(cid, neutral, P)}</svg>\n')
        row = []
        for mid in MOVESETS[cid]["mid"][:1] + MOVESETS[cid]["high"] + MOVESETS[cid]["accent"] + MOVESETS[cid]["special"]:
            ph = 0.8 if "special" in mid else (0.3 if "one-shot" in MOVES[mid][0] else 0.0)
            row.append((mid, compose(cid, sample(mid, ph), P)))
        cards.append((c, style, row))
    html = ['<html><body style="margin:0;background:#f3ead8;font:12px sans-serif"><div style="display:grid;grid-template-columns:repeat(5,200px);gap:6px;padding:10px">']
    for c, style, row in cards:
        for mid, g in row:
            html.append(f'<div style="background:#fffaf0;border:2px solid #222;border-radius:8px;text-align:center"><svg viewBox="-110 -178 220 248" width="196" height="216" style="{style}"><ellipse cx="0" cy="62" rx="44" ry="6" opacity=".18"/>{g}</svg><div>{c["name"]} · {mid}</div></div>')
    html.append('</div></body></html>')
    W("tools/contact.html", "".join(html))
main()
