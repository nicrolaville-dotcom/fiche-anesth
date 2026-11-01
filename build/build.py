#!/usr/bin/env python3
"""Découpe le Word des fiches (styles Titre 1/2/3) en une PWA statique hors ligne.

Usage : python3 build/build.py word/fiches.docx site/
Dépendances : pandoc, Pillow, et LibreOffice (pour convertir les images EMF/WMF).
"""
import hashlib, html, json, os, re, shutil, subprocess, sys, tempfile, unicodedata
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"

# Titre 1 du Word -> (branche, domaine). Clés comparées sans accents/casse/ponctuation.
H1_MAP = {
    "anesthesie": ("Adulte", "Anesthésie"),
    "reanimation": ("Adulte", "Réanimation"),
    "reanimation usc": ("Adulte", "Réanimation"),
    "infectiologie": ("Adulte", "Infectiologie"),
    "anesthesie pediatrique": ("Pédiatrie", "Anesthésie"),
    "reanimation pediatrique": ("Pédiatrie", "Réanimation"),
}
BRANCH_ORDER = ["Pédiatrie", "Adulte", "Autres"]
DOMAIN_ORDER = ["Anesthésie", "Réanimation", "Infectiologie"]
MAX_IMG_W = 1600


def norm(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def slug(s):
    return norm(s).replace(" ", "-")[:60] or "x"


def clean_title(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[.\-–\s]+", "", s)
    s = re.sub(r"[\s:.]+$", "", s)
    return s


def inline_text(xs):
    out = []
    for i in xs:
        t, c = i["t"], i.get("c")
        if t == "Str":
            out.append(c)
        elif t in ("Space", "SoftBreak", "LineBreak"):
            out.append(" ")
        elif t in ("Superscript", "Subscript", "Note"):
            pass  # appels de note / références bibliographiques
        elif t in ("Emph", "Strong", "Underline", "Strikeout", "SmallCaps"):
            out.append(inline_text(c))
        elif t in ("Span", "Link"):
            out.append(inline_text(c[1]))
        elif t == "Quoted":
            out.append(inline_text(c[1]))
        elif t == "Code":
            out.append(c[1])
    return "".join(out)


def nested_h2(block):
    """Titre 2 placé à l'intérieur d'un tableau : le renvoie et le vide dans le tableau."""
    found = []

    def walk(x):
        if isinstance(x, dict):
            if x.get("t") == "Header" and x["c"][0] == 2 and not found:
                found.append(clean_title(inline_text(x["c"][2])))
                x["t"], x["c"] = "Plain", []
                return
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(block)
    return found[0] if found else None


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def convert_images(media_dir, out_img):
    """Convertit toutes les images extraites en WebP compressées. Renvoie {chemin_source: nom_web}."""
    out_img.mkdir(parents=True, exist_ok=True)
    mapping = {}
    vectors = [p for p in media_dir.rglob("*") if p.suffix.lower() in (".emf", ".wmf", ".svg")]
    raster_from_vec = {}
    if vectors:
        tmp = Path(tempfile.mkdtemp())
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        for v in vectors:
            if not soffice:
                print(f"  ! LibreOffice absent, image ignorée : {v.name}")
                continue
            try:
                run([soffice, "--headless", "--convert-to", "png", "--outdir", str(tmp), str(v)], timeout=300)
                png = tmp / (v.stem + ".png")
                if png.exists():
                    raster_from_vec[v] = png
            except Exception as e:  # noqa
                print(f"  ! conversion impossible {v.name}: {e}")
    for p in sorted(media_dir.rglob("*")):
        if not p.is_file():
            continue
        src = raster_from_vec.get(p, p)
        try:
            im = Image.open(src)
            im.load()
        except Exception:
            print(f"  ! image illisible : {p.name}")
            continue
        if im.mode in ("P", "LA", "RGBA") or "transparency" in im.info:
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            bg.alpha_composite(im)
            im = bg.convert("RGB")
        else:
            im = im.convert("RGB")
        bbox = Image.eval(im, lambda x: 255 - x).getbbox()  # rogne les marges blanches
        if bbox:
            im = im.crop(bbox)
        if im.width > MAX_IMG_W:
            im = im.resize((MAX_IMG_W, round(im.height * MAX_IMG_W / im.width)), Image.LANCZOS)
        name = p.stem + ".webp"
        im.save(out_img / name, "WEBP", quality=78, method=5)
        mapping[str(p)] = name
    return mapping


def blocks_to_html(blocks, api):
    doc = {"pandoc-api-version": api, "meta": {}, "blocks": blocks}
    r = run(["pandoc", "-f", "json", "-t", "html5", "--wrap=none"], input=json.dumps(doc).encode())
    return r.stdout.decode()


def strip_tags(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


def main(docx, out):
    docx, out = Path(docx), Path(out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(APP, out)
    work = Path(tempfile.mkdtemp())
    media = work / "media"
    print("1/4 pandoc docx -> json")
    run(["pandoc", str(docx), "-t", "json", "-o", str(work / "doc.json"), f"--extract-media={media}"])
    d = json.loads((work / "doc.json").read_text())
    api = d["pandoc-api-version"]

    print("2/4 images")
    imgmap = convert_images(media, out / "img") if media.exists() else {}

    print("3/4 découpage")
    chapters, cur, h1 = [], None, None
    for b in d["blocks"]:
        if b["t"] == "Header" and b["c"][0] == 1:
            t = clean_title(inline_text(b["c"][2]))
            if norm(t) not in H1_MAP and h1 and t:
                # Titre 1 inconnu après un domaine connu = fiche importée d'un niveau trop haut :
                # elle devient un chapitre du domaine courant, ses Titre 2 deviennent des sections.
                cur = {**h1, "title": t, "blocks": [], "promoted": True}
                chapters.append(cur)
                continue
        if cur and cur.get("promoted") and not (b["t"] == "Header" and b["c"][0] == 1):
            if b["t"] == "Header":
                b["c"][0] += 1
            cur["blocks"].append(b)
            continue
        if b["t"] == "Table" and h1:
            t = nested_h2(b)
            if t:
                cur = {**h1, "title": t, "blocks": []}
                chapters.append(cur)
        if b["t"] == "Header" and b["c"][0] == 1:
            t = clean_title(inline_text(b["c"][2]))
            branch, domain = H1_MAP.get(norm(t), ("Autres", t))
            h1 = {"branch": branch, "domain": domain}
            cur = None
            continue
        if b["t"] == "Header" and b["c"][0] == 2:
            t = clean_title(inline_text(b["c"][2]))
            if t and h1:
                cur = {**h1, "title": t, "blocks": []}
                chapters.append(cur)
                continue
            if not t:
                continue  # Titre 2 vide : on garde le contenu dans le chapitre courant
        if h1 is None:
            continue
        if cur is None:  # contenu avant le premier Titre 2
            cur = {**h1, "title": "Généralités", "blocks": []}
            chapters.append(cur)
        cur["blocks"].append(b)

    used, index, nav = set(), [], {}
    (out / "c").mkdir()
    for ch in chapters:
        base = slug(f"{ch['branch']}-{ch['domain']}-{ch['title']}")
        cid, n = base, 2
        while cid in used:
            cid, n = f"{base}-{n}", n + 1
        used.add(cid)
        ch["id"] = cid
        sections, k = [], 0
        for b in ch["blocks"]:
            if b["t"] == "Header":
                lvl = max(2, b["c"][0] - 1)  # Titre 3 -> h2 dans la page
                t = clean_title(inline_text(b["c"][2]))
                if not t:
                    b["t"], b["c"] = "Null", None
                    continue
                k += 1
                sid = f"s{k}"
                b["c"][0] = lvl
                b["c"][1] = [sid, [], []]
                if lvl == 2:
                    sections.append({"id": sid, "title": t})
        ch["blocks"] = [b for b in ch["blocks"] if b["t"] != "Null"]
        h = blocks_to_html(ch["blocks"], api)

        def fix_img(m):
            src = html.unescape(m.group(1))
            name = imgmap.get(src) or imgmap.get(str(Path(src)))
            if not name:
                return ""
            return f'<img loading="lazy" src="img/{name}" alt="">'

        h = re.sub(r'<img[^>]*src="([^"]+)"[^>]*>', fix_img, h)
        h = re.sub(r'<embed[^>]*>', "", h)
        h = h.replace("<table", '<div class="tw"><table').replace("</table>", "</table></div>")
        h = re.sub(r' style="[^"]*"', "", h)
        h = re.sub(r"<thead>\s*<tr[^>]*>\s*<th[^>]*>\s*</th>\s*</tr>\s*</thead>", "", h)
        h = re.sub(r"<colgroup>.*?</colgroup>", "", h, flags=re.S)
        (out / "c" / f"{cid}.html").write_text(h)

        # index de recherche : un enregistrement par section (Titre 3)
        parts = re.split(r'(<h2 id="(s\d+)"[^>]*>.*?</h2>)', h, flags=re.S)
        index.append({"c": cid, "s": "", "t": ch["title"], "x": strip_tags(parts[0])})
        for i in range(1, len(parts), 3):
            index.append({"c": cid, "s": parts[i + 1], "t": strip_tags(parts[i]),
                          "x": strip_tags(parts[i] + (parts[i + 2] if i + 2 < len(parts) else ""))})
        nav.setdefault(ch["branch"], {}).setdefault(ch["domain"], []).append(
            {"id": cid, "title": ch["title"], "sections": sections})

    def order(lst, ref):
        return sorted(lst, key=lambda x: ref.index(x) if x in ref else len(ref))

    tree = [{"name": b, "domains": [{"name": dm, "chapters": nav[b][dm]} for dm in order(nav[b], DOMAIN_ORDER)]}
            for b in order(nav, BRANCH_ORDER)]
    (out / "data").mkdir(exist_ok=True)
    (out / "data" / "nav.json").write_text(json.dumps(tree, ensure_ascii=False))
    (out / "data" / "search.json").write_text(json.dumps(index, ensure_ascii=False))

    print("4/4 service worker")
    files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file() and p.name != "sw.js")
    hsh = hashlib.sha1()
    for f in files:
        hsh.update(f.encode()); hsh.update((out / f).read_bytes())
    version = hsh.hexdigest()[:10]
    sw = (out / "sw.js").read_text()
    sw = sw.replace("__VERSION__", version).replace("__FILES__", json.dumps(["./"] + files))
    (out / "sw.js").write_text(sw)
    (out / "data" / "version.json").write_text(json.dumps({"version": version, "source": docx.name}))
    (out / ".nojekyll").write_text("")
    size = sum((out / f).stat().st_size for f in files) / 1e6
    print(f"OK : {len(chapters)} chapitres, {len(imgmap)} images, {size:.1f} Mo, version {version}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
