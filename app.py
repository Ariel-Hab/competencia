# -*- coding: utf-8 -*-
import subprocess
import threading
import os
import sys
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file

from diccionario_manager import DiccionarioManager

app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')

# Asegurar que se vean bien los caracteres en consola de Windows
sys.stdout.reconfigure(encoding='utf-8')

# Estado del scraper
SCRAPER_STATE = {
    "process": None,
    "log": [],
    "running": False,
    "task": None,
    "auto_scroll": False
}

# Instancia del gestor de diccionario
diccionario_mgr = DiccionarioManager()

# ============================================================================
# FUNCIONES AUXILIARES - SCRAPER
# ============================================================================

def run_process(command, label):
    SCRAPER_STATE["running"] = True
    SCRAPER_STATE["task"] = label
    SCRAPER_STATE["log"].append(f"=== {label} INICIADO ===")
    
    if len(SCRAPER_STATE["log"]) > 1000:
        SCRAPER_STATE["log"] = SCRAPER_STATE["log"][-500:]

    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace'
        )
        SCRAPER_STATE["process"] = proc

        for line in proc.stdout:
            line_clean = line.strip()
            if line_clean:
                SCRAPER_STATE["log"].append(line_clean)

        proc.wait()
        SCRAPER_STATE["log"].append(f"=== {label} FINALIZADO ===")

    except Exception as e:
        SCRAPER_STATE["log"].append(f"[ERROR CRÍTICO] {e}")

    finally:
        SCRAPER_STATE["process"] = None
        SCRAPER_STATE["running"] = False
        SCRAPER_STATE["task"] = None
        SCRAPER_STATE["auto_scroll"] = False


# ============================================================================
# RUTAS - PÁGINA PRINCIPAL
# ============================================================================

@app.route("/")
def home():
    return render_template("index.html")


# ============================================================================
# RUTAS - SCRAPER
# ============================================================================

@app.route("/scraper/open-chrome", methods=["POST"])
def open_chrome():
    """Lanza Chrome con puerto de depuración"""
    
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
    ]
    
    chrome_path = None
    for c in candidates:
        if os.path.exists(c):
            chrome_path = c
            break
            
    if not chrome_path:
        return jsonify({"ok": False, "msg": "No se encontró chrome.exe"}), 404

    try:
        subprocess.Popen([
            chrome_path,
            "--remote-debugging-port=9222",
            r"--user-data-dir=C:\chrome_dev_profile",
            "https://www.e-panacea.com.ar/login" 
        ])
        SCRAPER_STATE["log"].append("[CHROME] Navegador abierto. Logueate manualmente.")
        return jsonify({"ok": True, "msg": "Chrome abierto"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/scraper/run", methods=["POST"])
def run_scraper():
    if SCRAPER_STATE["running"]:
        return jsonify({"ok": False, "msg": "Ya hay un proceso corriendo"}), 409

    t = threading.Thread(
        target=run_process,
        args=(["python", "scraper.py"], "SCRAPER MEMORIA+RED"),
        daemon=True
    )
    t.start()
    return jsonify({"ok": True})


@app.route("/scraper/excel", methods=["POST"])
def run_excel():
    if SCRAPER_STATE["running"]:
        return jsonify({"ok": False, "msg": "Ya hay un proceso corriendo"}), 409

    script_name = "post-scrp1.py" if os.path.exists("post-scrp1.py") else "generar_excel.py"
    
    t = threading.Thread(
        target=run_process,
        args=(["python", script_name], "GENERAR EXCEL"),
        daemon=True
    )
    t.start()
    return jsonify({"ok": True})


@app.route("/scraper/enter", methods=["POST"])
def send_enter():
    """Envía un Enter al proceso activo"""
    proc = SCRAPER_STATE.get("process")
    
    if not proc or proc.poll() is not None:
        return jsonify({"ok": False, "msg": "No hay proceso activo"}), 400
    
    try:
        proc.stdin.write("\n")
        proc.stdin.flush()
        SCRAPER_STATE["log"].append("[INPUT] ⏎ Enter enviado al proceso")
        return jsonify({"ok": True, "msg": "Enter enviado"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/scraper/toggle-scroll", methods=["POST"])
def toggle_scroll():
    if not SCRAPER_STATE["running"]:
        return jsonify({"ok": False, "msg": "Scraper no activo"}), 400
    
    SCRAPER_STATE["auto_scroll"] = not SCRAPER_STATE["auto_scroll"]
    proc = SCRAPER_STATE.get("process")
    
    if proc and proc.poll() is None:
        try:
            proc.stdin.write("s\n")
            proc.stdin.flush()
            status = "ACTIVADO" if SCRAPER_STATE["auto_scroll"] else "PAUSADO"
            SCRAPER_STATE["log"].append(f"[CONTROL] Scroll automático {status}")
            return jsonify({"ok": True, "active": SCRAPER_STATE["auto_scroll"]})
        except Exception as e:
            return jsonify({"ok": False, "msg": str(e)}), 500
            
    return jsonify({"ok": False, "msg": "Proceso no responde"}), 400


@app.route("/scraper/stop", methods=["POST"])
def stop_scraper():
    proc = SCRAPER_STATE.get("process")
    if proc and proc.poll() is None:
        proc.terminate()
        SCRAPER_STATE["log"].append("[STOP] Detenido por usuario")
        SCRAPER_STATE["auto_scroll"] = False
        return jsonify({"ok": True})

    return jsonify({"ok": False, "msg": "No hay proceso para detener"}), 400


@app.route("/scraper/status")
def scraper_status():
    return jsonify({
        "running": SCRAPER_STATE["running"],
        "task": SCRAPER_STATE["task"],
        "auto_scroll": SCRAPER_STATE["auto_scroll"],
        "log": SCRAPER_STATE["log"][-200:]
    })


# ============================================================================
# RUTAS - DICCIONARIO
# ============================================================================

@app.route("/diccionario/stats")
def diccionario_stats():
    """Obtiene estadísticas del diccionario"""
    try:
        stats = diccionario_mgr.get_stats()
        return jsonify({"ok": True, "data": stats})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/diccionario/list")
def diccionario_list():
    """Lista traducciones con filtros y paginación"""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    filtro = request.args.get('filtro', 'todos')  # todos, con_traduccion, sin_traduccion
    search = request.args.get('search', '')
    
    try:
        result = diccionario_mgr.list_traducciones(
            page=page,
            per_page=per_page,
            filtro=filtro,
            search=search
        )
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/diccionario/productos-db")
def productos_db():
    """Lista productos disponibles en la BD para autocompletar"""
    search = request.args.get('search', '')
    limit = int(request.args.get('limit', 20))
    
    try:
        productos = diccionario_mgr.search_productos(search, limit)
        return jsonify({"ok": True, "data": productos})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/diccionario/add", methods=["POST"])
def diccionario_add():
    """Añade o actualiza una traducción"""
    data = request.json
    
    nombre_panacea = data.get('nombre_panacea')
    producto_id = data.get('producto_id')
    confianza = float(data.get('confianza', 100.0))
    
    if not nombre_panacea or not producto_id:
        return jsonify({"ok": False, "msg": "Faltan datos requeridos"}), 400
    
    try:
        result = diccionario_mgr.add_traduccion(
            nombre_panacea=nombre_panacea,
            producto_id=producto_id,
            confianza=confianza
        )
        return jsonify({"ok": True, "msg": "Traducción guardada", "data": result})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/diccionario/delete/<alias_id>", methods=["DELETE"])
def diccionario_delete(alias_id):
    """Elimina una traducción"""
    try:
        diccionario_mgr.delete_traduccion(alias_id)
        return jsonify({"ok": True, "msg": "Traducción eliminada"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/diccionario/auto-match", methods=["POST"])
def diccionario_auto_match():
    """Ejecuta el matching automático para productos sin traducción"""
    data = request.json
    umbral = float(data.get('umbral', 80.0))
    limite = int(data.get('limite', 100))
    
    try:
        result = diccionario_mgr.auto_match(umbral=umbral, limite=limite)
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/diccionario/sugerencias/<nombre_panacea>")
def diccionario_sugerencias(nombre_panacea):
    """Obtiene sugerencias de productos para un nombre de Panacea"""
    try:
        sugerencias = diccionario_mgr.get_sugerencias(nombre_panacea, top_n=5)
        return jsonify({"ok": True, "data": sugerencias})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/diccionario/export")
def diccionario_export():
    """Exporta el diccionario a JSON"""
    try:
        filepath = diccionario_mgr.export_to_json()
        return send_file(filepath, as_attachment=True, download_name="diccionario_panacea.json")
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/diccionario/import", methods=["POST"])
def diccionario_import():
    """Importa traducciones desde archivo TXT"""
    if 'file' not in request.files:
        return jsonify({"ok": False, "msg": "No se envió archivo"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"ok": False, "msg": "Archivo vacío"}), 400
    
    try:
        # Guardar temporalmente
        temp_path = Path("temp_import.txt")
        file.save(temp_path)
        
        # Procesar
        result = diccionario_mgr.import_from_txt(temp_path)
        
        # Limpiar
        temp_path.unlink()
        
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


# ============================================================================
# INICIO DE LA APLICACIÓN
# ============================================================================

if __name__ == "__main__":
    # Crear carpetas necesarias
    Path("templates").mkdir(exist_ok=True)
    Path("static").mkdir(exist_ok=True)
    Path("outputs").mkdir(exist_ok=True)
    
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)