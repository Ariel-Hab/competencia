# -*- coding: utf-8 -*-
import os, json, time, sys, select, threading
from pathlib import Path
from playwright.sync_api import sync_playwright
from scroller import auto_scroll_logic

sys.stdout.reconfigure(encoding='utf-8')

# === Configuración ===
LISTEN_SECONDS = 14400      
MAX_JSON_DEBUG = 80        
POLL_INTERVAL = 0.5        

def input_listener():
    """Hilo que espera comandos desde Flask por stdin"""
    for line in sys.stdin:
        cmd = line.strip()
        if cmd == 's':
            state["auto_scroll"] = not state["auto_scroll"]
            estado = "ACTIVADO" if state["auto_scroll"] else "PAUSADO"
            print(f"[INPUT] Comando recibido. Scroll: {estado}", flush=True)

# === Paths (MODIFICADO) ===
# Detectamos el directorio actual donde reside este archivo .py
BASE_DIR = Path(__file__).resolve().parent

# Configurar carpeta de outputs
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUTPUTS_DIR / "panacea_clicks_enriquecido.json"

# Configurar carpeta de debug
DEBUG_DIR = BASE_DIR / "panacea_debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# === Estado Global ===
state = {
    "by_id": {},
    "urls_seen": [],
    "debug_count": 0,
    "auto_scroll": False,
    "last_detail_ts": 0.0,
    "waiting_for_product": None  # ← NUEVO: Track del producto que estamos esperando
}

# === JS SPY ===
JS_SNIFFER_CODE = """
if (!window.__JSON_SPY_ACTIVE__) {
    window.__JSON_SPY_ACTIVE__ = true;
    window.__DATOS_CAPTURADOS__ = [];
    const originalParse = JSON.parse;
    JSON.parse = function(text, reviver) {
        const data = originalParse(text, reviver);
        try {
            const esLista = data && data.productos && Array.isArray(data.productos);
            const esArrayProd = Array.isArray(data) && data.length > 0 && data[0].id_producto;
            let tienePrecios = false;
            let payload = data;
            if (data && data.producto_precios_especificos) tienePrecios = true;
            else if (data && data.data && data.data.producto_precios_especificos) {
                tienePrecios = true;
                payload = data.data;
            }
            if (esLista || esArrayProd || tienePrecios) {
                window.__DATOS_CAPTURADOS__.push(payload);
            }
        } catch (e) {}
        return data;
    };
}
"""

# === Lógica de Procesamiento ===

def get_rec(pid):
    pid = str(pid)
    return state["by_id"].setdefault(pid, {
        "card": {"id_producto": pid},
        "bonificacion": None, "mejor_precio": None, "mejor_precio_usuario": None, 
        "cantidad_desde_optima": None, "producto_precios_especificos": [], 
        "producto_descuentos_financieros": [], "sources": []
    })

def es_valor_vacio(v):
    return v in (None, "", "0", 0, 0.0, "0.00", "0,00")

def merge_card_fields(rec, d):
    campos = [
        "id_producto", "codigo", "descripcion", "stock", "precio_base", 
        "precio_minimo", "url_imagen", "imagen"
    ]
    for k in campos:
        if k in d and d[k] not in (None, ""):
            rec["card"][k] = d[k]

def merge_precio_especifico(rec, payload, src_type):
    """AHORA actualiza el timestamp SIEMPRE que hay datos relevantes"""
    pid = rec["card"]["id_producto"]
    
    # ← CRÍTICO: Actualizar timestamp si este producto es el que esperamos
    if state["waiting_for_product"] == pid:
        state["last_detail_ts"] = time.time()
        print(f"[✓] Datos recibidos para producto {pid}", flush=True)
    
    if payload.get("mejor_precio") is not None:
        rec["mejor_precio"] = payload.get("mejor_precio")
    if payload.get("cantidad_desde_optima") is not None:
        rec["cantidad_desde_optima"] = payload.get("cantidad_desde_optima")

    ppes = payload.get("producto_precios_especificos")
    if isinstance(ppes, list):
        curr_dump = [json.dumps(x, sort_keys=True) for x in rec["producto_precios_especificos"]]
        for row in ppes:
            if json.dumps(row, sort_keys=True) not in curr_dump:
                rec["producto_precios_especificos"].append(row)
            
            b = row.get("bonificacion")
            if not es_valor_vacio(b): rec["bonificacion"] = b

    pdfs = payload.get("producto_descuentos_financieros")
    if isinstance(pdfs, list):
        for row in pdfs:
            if row not in rec["producto_descuentos_financieros"]:
                rec["producto_descuentos_financieros"].append(row)

    if src_type not in rec["sources"]: rec["sources"].append(src_type)

def infer_product_id(node):
    """Intenta extraer el ID del producto de varias formas"""
    # Método 1: Directo en el nodo
    if "id_producto" in node:
        return str(node["id_producto"])
    
    # Método 2: En producto_precios_especificos
    if "producto_precios_especificos" in node:
        lista = node["producto_precios_especificos"]
        if isinstance(lista, list) and len(lista) > 0:
            if "id_producto" in lista[0]:
                return str(lista[0]["id_producto"])
    
    # Método 3: En producto_descuentos_financieros
    if "producto_descuentos_financieros" in node:
        lista = node["producto_descuentos_financieros"]
        if isinstance(lista, list) and len(lista) > 0:
            if "id_producto" in lista[0]:
                return str(lista[0]["id_producto"])
    
    return None

def process_payload(data, source_label):
    # Caso 1: Lista de productos (Catálogo general)
    if isinstance(data, dict) and isinstance(data.get("productos"), list):
        for d in data["productos"]:
            if isinstance(d, dict) and "id_producto" in d:
                rec = get_rec(d["id_producto"])
                merge_card_fields(rec, d)
        return

    # Caso 2: DFS para encontrar detalles anidados
    stack = [data]
    
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            pid = infer_product_id(node)

            if pid:
                rec = get_rec(pid)
                merge_card_fields(rec, node)
                
                # Si tiene precios específicos, procesarlos
                if any(k in node for k in ("producto_precios_especificos", "producto_descuentos_financieros", "mejor_precio")):
                    merge_precio_especifico(rec, node, source_label)
            
            for v in node.values():
                if isinstance(v, (dict, list)): stack.append(v)
        
        elif isinstance(node, list):
            for v in node:
                stack.append(v)

# === Handlers ===
def on_response(resp):
    try:
        if resp.request.resource_type in ["image", "font", "stylesheet"]: return
        try:
            data = resp.json()
        except: return

        state["urls_seen"].append(resp.url)
        
        # Procesamos
        process_payload(data, "NETWORK")
        
        # Guardamos debug si parece importante
        if state["debug_count"] < MAX_JSON_DEBUG:
            dump = json.dumps(data)
            if "producto" in dump:
                (DEBUG_DIR / f"net_{state['debug_count']:03d}.json").write_text(
                    json.dumps({"url": resp.url, "data": data}, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                state["debug_count"] += 1
    except Exception as e:
        print(f"[ERROR ON_RESPONSE] {e}", flush=True)

def check_memory_spy(page):
    try:
        items = page.evaluate("() => { let d = window.__DATOS_CAPTURADOS__ || []; window.__DATOS_CAPTURADOS__ = []; return d; }")
        if items:
            for item in items:
                process_payload(item, "MEMORY_CACHE")
    except: pass

# === Main ===
def save_json():
    try:
        items = []
        for pid, rec in state["by_id"].items():
            unique_ppes = {json.dumps(x, sort_keys=True): x for x in rec["producto_precios_especificos"]}
            rec["producto_precios_especificos"] = list(unique_ppes.values())

            items.append({
                "id_producto": pid,
                **rec["card"],
                "bonificacion": rec["bonificacion"],
                "mejor_precio": rec["mejor_precio"],
                "producto_precios_especificos": rec["producto_precios_especificos"],
                "source_urls": list(set(rec["sources"]))
            })

        result = {"count": len(items), "generated_at": time.ctime(), "productos": items}
        
        # Nota: OUT_JSON ya es un objeto Path, así que .with_suffix funciona correctamente
        temp = OUT_JSON.with_suffix(".tmp")
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if temp.exists(): os.replace(temp, OUT_JSON)
        
        print(f"[IO] Guardado JSON con {len(items)} productos en: {OUT_JSON}", flush=True)
        
    except Exception as e:
        print(f"[ERROR SAVE] {e}", flush=True)

def main():
    print(f"[INFO] Scraper v3.5 (Local Paths)", flush=True)
    print(f"[INFO] Carpeta base: {BASE_DIR}", flush=True)
    print(f"[INFO] Control desde interfaz web: http://127.0.0.1:5000", flush=True)
    
    t_input = threading.Thread(target=input_listener, daemon=True)
    t_input.start()
    
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp("http://localhost:9222", timeout=10000)
            except:
                print("[ERROR] Chrome no detectado en puerto 9222.", flush=True)
                print("[AYUDA] Asegúrate de presionar 'Abrir Chrome' primero.", flush=True)
                return

            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            
            context.on("response", on_response)
            try: page.evaluate(JS_SNIFFER_CODE)
            except: pass

            print("[✓] Conectado al navegador correctamente", flush=True)
            print("[INFO] Usa los botones de la interfaz web para controlar", flush=True)
            
            t0 = time.time()
            last_save, last_poll = t0, t0
            
            while time.time() - t0 < LISTEN_SECONDS:
                now = time.time()
                
                if now - last_save > 10: save_json(); last_save = now
                if now - last_poll > POLL_INTERVAL: check_memory_spy(page); last_poll = now
                
                if state["auto_scroll"]: 
                    auto_scroll_logic(page, state, save_callback=save_json)
                else: 
                    time.sleep(0.1)

            save_json()
            print("[INFO] Tiempo límite alcanzado. Scraper finalizado.", flush=True)
    except Exception as e:
        print(f"[FATAL] {e}", flush=True)

if __name__ == "__main__":
    main()