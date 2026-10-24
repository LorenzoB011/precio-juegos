"""
Precios de juegos en pesos argentinos — versión 2 (Steam + Epic + Game Pass)

Qué hace:
  1. Busca el dólar oficial del día.
  2. Trae las ofertas de Steam, los juegos gratis de Epic y el catálogo de Game Pass.
  3. Calcula el precio final en pesos (dólar oficial + IVA + Ingresos Brutos).
  4. Genera "index.html", una página con buscador lista para publicar.

Cómo se usa:
  python precios_juegos.py          -> datos reales
  python precios_juegos.py --demo   -> datos de ejemplo, para probar sin internet

No necesita instalar nada: usa solo librerías que ya vienen con Python.
"""

import datetime
import html
import json
import re
import sys
import urllib.request

# ---------------------------------------------------------------------------
# CONFIGURACIÓN — lo único que quizás quieras tocar
# ---------------------------------------------------------------------------
IVA = 0.21    # IVA sobre servicios digitales del exterior
IIBB = 0.02   # Ingresos Brutos: cambia según la provincia. Poné el de la tuya.
NOMBRE_SITIO = "Precio Gamer AR"

HEADERS = {"User-Agent": "Mozilla/5.0 (precios-juegos-ar)"}


# ---------------------------------------------------------------------------
# Funciones de ayuda
# ---------------------------------------------------------------------------
def get_json(url):
    """Descarga una URL y la devuelve como diccionario de Python."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def dolar_oficial():
    """Cotización del dólar oficial (valor de venta)."""
    data = get_json("https://dolarapi.com/v1/dolares/oficial")
    return float(data["venta"])


def a_pesos(usd, dolar):
    """Convierte dólares a pesos con impuestos incluidos."""
    return round(usd * dolar * (1 + IVA + IIBB))


# ---------------------------------------------------------------------------
# Tiendas
# ---------------------------------------------------------------------------
PAGINAS_STEAM = 5   # cada página trae hasta 100 ofertas


def ofertas_steam(dolar):
    """Todas las ofertas del buscador de Steam (Argentina), hasta 500 juegos."""
    juegos, vistos = [], set()
    for pagina in range(PAGINAS_STEAM):
        data = get_json(
            "https://store.steampowered.com/search/results/?query&specials=1"
            f"&cc=ar&l=spanish&infinite=1&count=100&start={pagina * 100}"
        )
        filas = re.findall(
            r'<a [^>]*data-ds-appid="(\d+)"[^>]*>(.*?)</a>',
            data.get("results_html", ""), re.S,
        )
        if not filas:
            break
        for appid, cuerpo in filas:
            titulo = re.search(r'<span class="title">(.*?)</span>', cuerpo, re.S)
            final = re.search(r'data-price-final="(\d+)"', cuerpo)
            desc = re.search(r'data-discount="(\d+)"', cuerpo)
            if appid in vistos or not (titulo and final and desc):
                continue
            descuento = int(desc.group(1))
            if descuento <= 0:
                continue
            vistos.add(appid)
            usd_final = int(final.group(1)) / 100
            usd_original = usd_final / (1 - descuento / 100) if descuento < 100 else 0
            juegos.append({
                "tienda": "Steam",
                "nombre": html.unescape(titulo.group(1).strip()),
                "imagen": f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
                "url": f"https://store.steampowered.com/app/{appid}",
                "descuento": descuento,
                "usd": usd_final,
                "ars": a_pesos(usd_final, dolar),
                "ars_original": a_pesos(usd_original, dolar),
            })
    # Si el buscador cambia de formato, usamos la lista corta de destacados
    return juegos or ofertas_steam_destacadas(dolar)


def ofertas_steam_destacadas(dolar):
    """Plan B: las ofertas destacadas de Steam (unas pocas)."""
    data = get_json(
        "https://store.steampowered.com/api/featuredcategories?cc=ar&l=spanish"
    )
    juegos, vistos = [], set()
    for item in data.get("specials", {}).get("items", []):
        if item["id"] in vistos or not item.get("discounted"):
            continue
        vistos.add(item["id"])
        usd_final = item["final_price"] / 100
        usd_original = item["original_price"] / 100
        juegos.append({
            "tienda": "Steam",
            "nombre": item["name"],
            "imagen": item.get("header_image") or item.get("large_capsule_image", ""),
            "url": f"https://store.steampowered.com/app/{item['id']}",
            "descuento": item.get("discount_percent", 0),
            "usd": usd_final,
            "ars": a_pesos(usd_final, dolar),
            "ars_original": a_pesos(usd_original, dolar),
        })
    return juegos


def gratis_epic():
    """Juegos que Epic regala esta semana."""
    data = get_json(
        "https://store-site-backend-static-ipv4.ak.epicgames.com/"
        "freeGamesPromotions?locale=es-ES&country=AR&allowCountries=AR"
    )
    elementos = data["data"]["Catalog"]["searchStore"]["elements"]
    juegos = []
    for e in elementos:
        promos = (e.get("promotions") or {}).get("promotionalOffers") or []
        ofertas = promos[0]["promotionalOffers"] if promos else []
        gratis_ahora = any(
            o["discountSetting"]["discountPercentage"] == 0 for o in ofertas
        )
        if not gratis_ahora:
            continue

        # Buscar el "slug" para armar el link a la tienda
        slug = None
        for m in (e.get("offerMappings") or []) + (
            (e.get("catalogNs") or {}).get("mappings") or []
        ):
            if m.get("pageSlug"):
                slug = m["pageSlug"]
                break
        slug = slug or e.get("productSlug")
        url = f"https://store.epicgames.com/es-ES/p/{slug}" if slug else \
            "https://store.epicgames.com/es-ES/free-games"

        imagen = ""
        for img in e.get("keyImages", []):
            if img.get("type") in ("OfferImageWide", "DieselStoreFrontWide"):
                imagen = img["url"]
                break
        if not imagen and e.get("keyImages"):
            imagen = e["keyImages"][0]["url"]

        hasta = ofertas[0].get("endDate", "")[:10] if ofertas else ""
        juegos.append({
            "tienda": "Epic",
            "nombre": e["title"],
            "imagen": imagen,
            "url": url,
            "descuento": 100,
            "usd": 0,
            "ars": 0,
            "ars_original": 0,
            "hasta": hasta,
        })
    return juegos


GAMEPASS_LISTAS = {
    "Consola": "f6f1f99f-9b49-4ccd-b3bf-4d9767a77f5e",
    "PC": "fdd9e2a7-0fee-49f6-ad69-4354098401ff",
}


def juegos_gamepass():
    """Catálogo de Game Pass (consola y PC) para Argentina."""
    plataformas = {}   # id del juego -> {"Consola", "PC"}
    for plataforma, lista in GAMEPASS_LISTAS.items():
        try:
            data = get_json(
                f"https://catalog.gamepass.com/sigls/v2?id={lista}"
                "&language=es-ar&market=AR"
            )
        except Exception as error:
            print(f"Game Pass {plataforma}: no se pudo leer ({error})")
            continue
        for item in data:
            if "id" in item:
                plataformas.setdefault(item["id"], set()).add(plataforma)
        print(f"Game Pass {plataforma}: {sum(1 for i in data if 'id' in i)} juegos")

    ids = list(plataformas)
    juegos = []
    for i in range(0, len(ids), 20):   # Microsoft acepta de a 20 por consulta
        data = get_json(
            "https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds="
            + ",".join(ids[i:i + 20]) + "&market=AR&languages=es-ar"
        )
        for prod in data.get("Products", []):
            pid = prod.get("ProductId", "")
            props = (prod.get("LocalizedProperties") or [{}])[0]
            nombre = props.get("ProductTitle")
            if not nombre:
                continue
            imagen = ""
            for tipo in ("SuperHeroArt", "BoxArt", "Poster"):
                for img in props.get("Images", []):
                    if img.get("ImagePurpose") == tipo:
                        imagen = "https:" + img["Uri"] if img["Uri"].startswith("//") else img["Uri"]
                        break
                if imagen:
                    break
            juegos.append({
                "tienda": "Game Pass",
                "nombre": nombre,
                "imagen": imagen,
                "url": f"https://www.xbox.com/es-AR/games/store/x/{pid}",
                "descuento": 0,
                "usd": 0,
                "ars": 0,
                "ars_original": 0,
                "plataforma": " y ".join(sorted(plataformas.get(pid, []))),
            })
    return juegos


def datos_demo():
    """Datos inventados para probar la página sin conexión."""
    dolar = 1500.0
    ejemplos = [
        ("Juego de ejemplo A", 19.99, 4.99, 75),
        ("Juego de ejemplo B", 29.99, 14.99, 50),
        ("Juego de ejemplo C", 9.99, 6.99, 30),
    ]
    juegos = [{
        "tienda": "Steam", "nombre": n, "imagen": "", "url": "#",
        "descuento": d, "usd": f, "ars": a_pesos(f, dolar),
        "ars_original": a_pesos(o, dolar),
    } for n, o, f, d in ejemplos]
    juegos.append({
        "tienda": "Epic", "nombre": "Juego gratis de ejemplo", "imagen": "",
        "url": "#", "descuento": 100, "usd": 0, "ars": 0, "ars_original": 0,
        "hasta": "2026-10-31",
    })
    juegos.append({
        "tienda": "Game Pass", "nombre": "Juego de Game Pass de ejemplo",
        "imagen": "", "url": "#", "descuento": 0, "usd": 0, "ars": 0,
        "ars_original": 0, "plataforma": "Consola y PC",
    })
    return dolar, juegos


# ---------------------------------------------------------------------------
# Página web
# ---------------------------------------------------------------------------
PLANTILLA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITULO__ — ofertas de juegos en pesos</title>
<meta name="description" content="Ofertas de Steam y juegos gratis de Epic con el precio final en pesos argentinos, impuestos incluidos. Se actualiza todos los días.">
<style>
  :root { --bg:#f6f7fb; --card:#fff; --txt:#16181d; --sub:#5b6170; --acento:#2f6fed; --verde:#14a05a; --borde:#e3e6ee; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0f1115; --card:#191c23; --txt:#eef0f4; --sub:#9aa1b2; --acento:#6b9bff; --verde:#3ccf85; --borde:#2a2e38; }
  }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--txt); }
  header { padding:24px 16px 8px; max-width:1100px; margin:auto; }
  h1 { margin:0 0 4px; font-size:1.6rem; }
  .info { color:var(--sub); font-size:.9rem; }
  .controles { display:flex; gap:8px; flex-wrap:wrap; padding:12px 16px; max-width:1100px; margin:auto; }
  input, select { font:inherit; padding:10px 12px; border-radius:10px; border:1px solid var(--borde); background:var(--card); color:var(--txt); }
  input { flex:1; min-width:180px; }
  main { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:14px; padding:8px 16px 40px; max-width:1100px; margin:auto; }
  .card { background:var(--card); border:1px solid var(--borde); border-radius:14px; overflow:hidden; text-decoration:none; color:inherit; display:flex; flex-direction:column; }
  .card img, .sinimg { width:100%; aspect-ratio:460/215; object-fit:cover; background:var(--borde); display:block; }
  .cuerpo { padding:12px; display:flex; flex-direction:column; gap:6px; flex:1; }
  .nombre { font-weight:600; line-height:1.25; }
  .fila { display:flex; align-items:center; gap:8px; margin-top:auto; }
  .tienda { font-size:.75rem; color:var(--sub); text-transform:uppercase; letter-spacing:.04em; }
  .desc { background:var(--verde); color:#fff; font-weight:700; font-size:.8rem; padding:2px 6px; border-radius:6px; }
  .precio { font-weight:700; font-size:1.1rem; }
  .gp { background:#107c10; }
  .tachado { text-decoration:line-through; color:var(--sub); font-size:.85rem; }
  footer { text-align:center; color:var(--sub); font-size:.8rem; padding:0 16px 30px; }
</style>
</head>
<body>
<header>
  <h1>__TITULO__</h1>
  <div class="info">Precio final en pesos con impuestos · Dólar oficial $__DOLAR__ · Actualizado __FECHA__</div>
</header>
<div class="controles">
  <input id="buscar" type="search" placeholder="Buscar juego…">
  <select id="tienda">
    <option value="">Todas las tiendas</option>
    <option>Steam</option>
    <option>Epic</option>
    <option>Game Pass</option>
  </select>
  <select id="orden">
    <option value="desc">Mayor descuento</option>
    <option value="barato">Más barato</option>
  </select>
</div>
<main id="lista"></main>
<footer>Precios orientativos: dólar oficial + IVA __IVA__% + IIBB __IIBB__%. Confirmá el precio final en la tienda.</footer>
<script id="datos" type="application/json">__DATOS__</script>
<script>
  const juegos = JSON.parse(document.getElementById("datos").textContent);
  const $ = id => document.getElementById(id);
  const pesos = n => "$" + n.toLocaleString("es-AR");
  const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

  function render() {
    const q = $("buscar").value.toLowerCase().trim();
    const t = $("tienda").value;
    let lista = juegos.filter(j => (!t || j.tienda === t) && j.nombre.toLowerCase().includes(q));
    lista.sort($("orden").value === "barato" ? (a,b) => a.ars - b.ars : (a,b) => b.descuento - a.descuento);
    $("lista").innerHTML = lista.map(j => `
      <a class="card" href="${esc(j.url)}" target="_blank" rel="noopener">
        ${j.imagen ? `<img src="${esc(j.imagen)}" alt="" loading="lazy">` : `<div class="sinimg"></div>`}
        <div class="cuerpo">
          <span class="tienda">${j.tienda}${j.hasta ? " · gratis hasta " + j.hasta : ""}${j.plataforma ? " · " + j.plataforma : ""}</span>
          <span class="nombre">${esc(j.nombre)}</span>
          <div class="fila">
            ${j.tienda === "Game Pass" ? `<span class="desc gp">Game Pass</span><span class="precio">Incluido</span>` : `
            <span class="desc">-${j.descuento}%</span>
            <span class="precio">${j.ars === 0 ? "GRATIS" : pesos(j.ars)}</span>`}
            ${j.ars_original > j.ars ? `<span class="tachado">${pesos(j.ars_original)}</span>` : ""}
          </div>
        </div>
      </a>`).join("") || "<p>No hay resultados.</p>";
  }
  ["buscar","tienda","orden"].forEach(id => $(id).addEventListener("input", render));
  render();
</script>
</body>
</html>
"""


def generar_html(juegos, dolar):
    ahora = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=-3))
    ).strftime("%d/%m/%Y %H:%M")
    datos = json.dumps(juegos, ensure_ascii=False).replace("</", "<\\/")
    pagina = (PLANTILLA
              .replace("__TITULO__", html.escape(NOMBRE_SITIO))
              .replace("__DOLAR__", f"{dolar:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
              .replace("__FECHA__", ahora)
              .replace("__IVA__", str(round(IVA * 100)))
              .replace("__IIBB__", str(round(IIBB * 100)))
              .replace("__DATOS__", datos))
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(pagina)


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
def main():
    if "--demo" in sys.argv:
        dolar, juegos = datos_demo()
    else:
        dolar = dolar_oficial()
        juegos = []
        # Si una tienda falla, seguimos con las otras
        for nombre, funcion in [("Steam", lambda: ofertas_steam(dolar)),
                                ("Epic", gratis_epic),
                                ("Game Pass", juegos_gamepass)]:
            try:
                encontrados = funcion()
                print(f"{nombre}: {len(encontrados)} juegos")
                juegos += encontrados
            except Exception as error:
                print(f"{nombre}: no se pudo leer ({error})")

    generar_html(juegos, dolar)
    print(f"Listo: index.html con {len(juegos)} juegos (dólar ${dolar})")


if __name__ == "__main__":
    main()
