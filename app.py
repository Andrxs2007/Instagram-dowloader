import os
import re
import shutil
import tempfile
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_file, after_this_request
import yt_dlp

app = Flask(__name__)

# Opcional: archivo cookies.txt (formato Netscape) para contenido que exige sesión.
COOKIES = "cookies.txt" if os.path.exists("cookies.txt") else None


def es_url_instagram(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in ("instagram.com", "www.instagram.com") and bool(
        re.search(r"/(reel|reels|p|tv)/", url)
    )


def opciones(extra=None):
    base = {"quiet": True, "no_warnings": True, "noplaylist": True}
    if COOKIES:
        base["cookiefile"] = COOKIES
    if extra:
        base.update(extra)
    return base


@app.get("/")
def inicio():
    return PAGINA


@app.post("/api/info")
def info():
    url = (request.json or {}).get("url", "").strip()
    if not es_url_instagram(url):
        return jsonify(error="Pega un enlace válido de un Reel o publicación de Instagram."), 400
    try:
        with yt_dlp.YoutubeDL(opciones()) as ydl:
            datos = ydl.extract_info(url, download=False)
    except Exception:
        return jsonify(error="No se pudo leer el video. Puede ser privado o el enlace no es público."), 422

    mejor = max(
        (f for f in datos.get("formats", []) if f.get("height")),
        key=lambda f: (f.get("height") or 0, f.get("tbr") or 0),
        default=None,
    )
    return jsonify(
        titulo=datos.get("title") or "Video de Instagram",
        miniatura=datos.get("thumbnail"),
        calidad=f"{mejor['width']}×{mejor['height']}" if mejor else "Máxima disponible",
        duracion=datos.get("duration"),
    )


@app.get("/api/descargar")
def descargar():
    url = request.args.get("url", "").strip()
    if not es_url_instagram(url):
        return jsonify(error="Enlace no válido."), 400

    carpeta = tempfile.mkdtemp()

    @after_this_request
    def limpiar(resp):
        shutil.rmtree(carpeta, ignore_errors=True)
        return resp

    try:
        # Mejor video + mejor audio, unidos en mp4 (requiere ffmpeg).
        ydl_opts = opciones(
            {
                "format": "bv*+ba/b",
                "merge_output_format": "mp4",
                "outtmpl": os.path.join(carpeta, "%(id)s.%(ext)s"),
            }
        )
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            datos = ydl.extract_info(url, download=True)
            ruta = os.path.splitext(ydl.prepare_filename(datos))[0] + ".mp4"
        return send_file(ruta, as_attachment=True, download_name=f"instagram_{datos['id']}.mp4")
    except Exception:
        return jsonify(error="La descarga falló. Intenta de nuevo."), 500


PAGINA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Descargar videos de Instagram</title>
<style>
  :root{--fondo:#faf7fb;--tinta:#1f1630;--suave:#6b6080;--linea:#e2d9ec;--acento:#7a3cff;--acento2:#ff4f81;--tarjeta:#fff}
  @media (prefers-color-scheme:dark){:root{--fondo:#150f21;--tinta:#f3eefb;--suave:#a99cc2;--linea:#32284a;--tarjeta:#1e1630}}
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:var(--fondo);color:var(--tinta);
       font:16px/1.5 "Trebuchet MS","Segoe UI",system-ui,sans-serif}
  main{width:100%;max-width:520px}
  h1{font-size:2rem;line-height:1.15;margin:0 0 8px;letter-spacing:-.02em}
  p.sub{margin:0 0 24px;color:var(--suave)}
  .caja{background:var(--tarjeta);border:1px solid var(--linea);border-radius:18px;padding:16px}
  input{width:100%;padding:14px;border:1px solid var(--linea);border-radius:12px;font:inherit;background:transparent;color:inherit}
  input:focus,button:focus-visible{outline:3px solid var(--acento);outline-offset:2px}
  button{width:100%;margin-top:12px;padding:14px;border:0;border-radius:12px;font:inherit;font-weight:700;color:#fff;
         background:linear-gradient(90deg,var(--acento),var(--acento2));cursor:pointer}
  button:disabled{opacity:.6;cursor:wait}
  #estado{margin-top:14px;min-height:1.4em;color:var(--suave)}
  #estado.error{color:#d6336c}
  #resultado{display:none;margin-top:16px;gap:12px;align-items:center}
  #resultado.activo{display:flex}
  #resultado img{width:72px;height:96px;object-fit:cover;border-radius:10px;background:var(--linea)}
  #titulo{font-weight:700;margin:0;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
  #calidad{margin:2px 0 8px;color:var(--suave);font-size:.9rem}
  #bajar{display:inline-block;padding:10px 16px;border-radius:10px;background:var(--tinta);color:var(--fondo);text-decoration:none;font-weight:700}
  small{display:block;margin-top:20px;color:var(--suave);font-size:.8rem}
</style>
</head>
<body>
<main>
  <h1>Descarga videos de Instagram en la mejor calidad</h1>
  <p class="sub">Pega el enlace de un Reel o publicación pública y descarga el archivo en MP4.</p>
  <div class="caja">
    <input id="url" type="url" placeholder="https://www.instagram.com/reel/..." autocomplete="off">
    <button id="buscar">Buscar video</button>
    <div id="estado" role="status"></div>
    <div id="resultado">
      <img id="mini" alt="">
      <div>
        <p id="titulo"></p>
        <p id="calidad"></p>
        <a id="bajar" href="#">Descargar MP4</a>
      </div>
    </div>
  </div>
  <small>Úsalo solo con videos tuyos o con permiso de su autor.</small>
</main>
<script>
const $ = id => document.getElementById(id);
$("buscar").onclick = async () => {
  const url = $("url").value.trim();
  $("resultado").classList.remove("activo");
  $("estado").className = "";
  if (!url) { $("estado").textContent = "Pega primero un enlace."; $("estado").className = "error"; return; }
  $("buscar").disabled = true; $("estado").textContent = "Buscando el video…";
  try {
    const r = await fetch("/api/info", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({url})});
    const d = await r.json();
    if (!r.ok) throw new Error(d.error);
    $("mini").src = d.miniatura || "";
    $("titulo").textContent = d.titulo;
    $("calidad").textContent = "Calidad: " + d.calidad;
    $("bajar").href = "/api/descargar?url=" + encodeURIComponent(url);
    $("resultado").classList.add("activo");
    $("estado").textContent = "";
  } catch (e) {
    $("estado").textContent = e.message || "Algo salió mal."; $("estado").className = "error";
  } finally { $("buscar").disabled = false; }
};
</script>
</body>
</html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
