import requests
import json
import time
import random
import os
import re
from datetime import datetime
from uuid import uuid4
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ==============================================================================
# 1. CONFIGURACIÓN
# ==============================================================================

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "presupuestacion_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "password")

DB_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

DIR_ACTUAL = os.path.dirname(os.path.abspath(__file__))
PATH_BACKUP_JSON = os.path.join(DIR_ACTUAL, "outputs", "backup_stock_panacea.json")

URL_API = "https://www.gc-sistemas.com.ar/crmcloud/panacea-api/api/v1/producto/producto_x_usuario2"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "es-419,es;q=0.9",
    "content-type": "application/json",
    "origin": "https://www.e-panacea.com.ar",
    "referer": "https://www.e-panacea.com.ar/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "x-api-key": "CZiCZCmPK71rREywvxusG52QEzOucJDu4kCgcyqdQ4Zr1nxuykphbipwetnFwaqqyn"
}
NOMBRE_COMPETIDOR = "Panacea"
ORIGEN_CARGA = "scraping_automatico_unificado"


# ==============================================================================
# 2. FUNCIONES AUXILIARES
# ==============================================================================

def limpiar_texto_simple(texto: str) -> str:
    if not texto: return ""
    texto = texto.upper()
    texto = re.sub(r'[^A-Z0-9\s\.]', ' ', texto)
    return ' '.join(texto.split())

def obtener_datos_scraping():
    # Scraping de las 3 marcas solicitadas
    ids_marcas = [128, 145, 249] 
    
    payload = {
        "id_usuario": 2801,
        "id_producto": 0,
        "favorito": "N",
        "id_producto_linea": 0,
        "id_producto_marca": 0,
        "id_producto_tipo": 0,
        "descripcion": "",
        "descripcion_larga": "*",
        "destacado": "N",
        "id_oferta": 0,
        "pagina": 1
    }

    todos_los_productos = []
    session = requests.Session()
    session.headers.update(HEADERS)

    print(f"\n--- [FASE 1] Iniciando Scraping Multimarca: {ids_marcas} ---")

    for marca_id in ids_marcas:
        print(f"\n>>> PROCESANDO MARCA ID: {marca_id}")
        payload["id_producto_marca"] = marca_id
        pagina_actual = 1
        payload["pagina"] = pagina_actual
        
        contador_racha = 0
        limite_racha = random.randint(8, 15)
        hay_mas_datos = True

        while hay_mas_datos:
            print(f"   Pag {pagina_actual}...", end=" ")
            payload["pagina"] = pagina_actual
            
            try:
                response = session.post(URL_API, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    lista_a_procesar = []

                    if isinstance(data, list):
                        lista_a_procesar = data
                    elif isinstance(data, dict):
                        for key, value in data.items():
                            if isinstance(value, list):
                                lista_a_procesar = value
                                break
                    
                    if not lista_a_procesar:
                        print("\n   [INFO] Fin de resultados para esta marca.")
                        hay_mas_datos = False
                        break
                    
                    count = 0
                    for item in lista_a_procesar:
                        if isinstance(item, dict):
                            todos_los_productos.append({
                                "id": item.get("id_producto", "N/A"),
                                "producto": item.get("descripcion", "Sin Nombre"),
                                "stock": item.get("stock", "0")
                            })
                            count += 1
                    
                    print(f"-> {count} items", end=" ")
                    pagina_actual += 1
                    contador_racha += 1
                    
                    if contador_racha >= limite_racha:
                        tiempo_enfriamiento = random.uniform(15, 30)
                        print(f"\n     [☕] Pausa larga ({tiempo_enfriamiento:.1f}s)...")
                        time.sleep(tiempo_enfriamiento)
                        contador_racha = 0
                        limite_racha = random.randint(8, 15)
                    else:
                        wait_time = random.uniform(3, 60)
                        print(f"| {wait_time:.1f}s")
                        time.sleep(wait_time)
                else:
                    print(f"\n   [ERROR] Status {response.status_code}")
                    hay_mas_datos = False
            except Exception as e:
                print(f"\n   [ERROR CRÍTICO SCRAPING] {e}")
                hay_mas_datos = False
        
        print(f"   [OK] Marca {marca_id} finalizada. Esperando...")
        time.sleep(5)

    print(f"\n--- TOTAL RECOLECTADO: {len(todos_los_productos)} productos ---")
    return todos_los_productos

def cargar_mapa_alias_db(session):
    print(">> Cargando mapa de alias desde DB (tabla producto_alias)...")
    try:
        sql = text("SELECT texto_original, producto_id FROM producto_alias WHERE texto_original IS NOT NULL")
        result = session.execute(sql).fetchall()
        mapa = {row[0]: row[1] for row in result}
        return mapa
    except Exception as e:
        print(f"[ERROR] Cargando alias: {e}")
        return {}

def obtener_registros_hoy(session, competidor_id):
    sql = text("""
        SELECT producto_id 
        FROM stock_competencia 
        WHERE competidor_id = :cid 
          AND fecha_registro::date = current_date
    """)
    result = session.execute(sql, {"cid": competidor_id}).fetchall()
    return {row[0] for row in result}

def pedir_confirmacion_creacion(nombre_original):
    print(f"\n[?] No se encontró match en Diccionario ni Productos para: '{nombre_original}'")
    print("0. No, omitir este producto.")
    print("1. Sí, crear producto nuevo y guardar en diccionario.")
    while True:
        opcion = input(">> Seleccione una opción: ").strip()
        if opcion == "0": return False
        elif opcion == "1": return True
        else: print("Opción inválida.")

def guardar_en_base_datos(stock_data):
    print(f"\n--- [FASE 2] Guardando en Base de Datos ---")
    
    engine = None
    session = None
    
    try:
        engine = create_engine(DB_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        print(">> Conexión DB establecida.")

        mapa_alias = cargar_mapa_alias_db(session)

        sql_competidor = text("SELECT id FROM competidores WHERE nombre = :nombre")
        res_comp = session.execute(sql_competidor, {"nombre": NOMBRE_COMPETIDOR}).fetchone()
        
        if not res_comp:
            competidor_id = uuid4()
            session.execute(text("""
                INSERT INTO competidores (id, nombre, activo, es_manual, created_at, updated_at)
                VALUES (:id, :nombre, true, false, now(), now())
            """), {"id": competidor_id, "nombre": NOMBRE_COMPETIDOR})
            session.commit()
        else:
            competidor_id = res_comp[0]

        productos_ya_cargados_hoy = obtener_registros_hoy(session, competidor_id)

        sql_busqueda_prod_nombre = text("SELECT id FROM productos WHERE nombre_producto = :nombre")
        
        sql_insert_nuevo_producto = text("""
            INSERT INTO productos (id, nombre_producto, precio_lista, activo, created_at, updated_at)
            VALUES (:id, :nombre, 1, true, now(), now())
        """)

        sql_insert_alias = text("""
            INSERT INTO producto_alias (id, producto_id, termino_busqueda, texto_original, origen, confianza, created_at)
            VALUES (:id, :pid, :term, :orig, 'PROVEEDOR', 100.0, now())
        """)

        sql_insert_stock = text("""
            INSERT INTO stock_competencia (id, producto_id, competidor_id, stock, fecha_registro, origen_carga)
            VALUES (:id, :pid, :cid, :stock, :fecha, :origen)
        """)

        registros_insertados = 0
        productos_creados = 0
        registros_saltados = 0
        timestamp_ahora = datetime.utcnow()

        # Variable para controlar la respuesta masiva ("Sí a todos" / "No a todos")
        accion_duplicados_global = None 

        for item in stock_data:
            nombre_original = item.get("producto", "").strip()
            
            try:
                val_stock = str(item.get("stock", "0"))
                if val_stock.lower() == "consultar": val_stock = "0"
                stock_cantidad = int(float(val_stock))
            except:
                stock_cantidad = 0

            producto_id = None

            if nombre_original in mapa_alias:
                producto_id = mapa_alias[nombre_original]
            else:
                res_p = session.execute(sql_busqueda_prod_nombre, {"nombre": nombre_original}).fetchone()
                if res_p:
                    producto_id = res_p[0]
                else:
                    if pedir_confirmacion_creacion(nombre_original):
                        nuevo_id = uuid4()
                        nombre_nuevo = f"{nombre_original} (PANACEA)"
                        termino_busqueda = limpiar_texto_simple(nombre_original)
                        
                        session.execute(sql_insert_nuevo_producto, {
                            "id": nuevo_id, "nombre": nombre_nuevo
                        })
                        session.execute(sql_insert_alias, {
                            "id": uuid4(), "pid": nuevo_id, "term": termino_busqueda, "orig": nombre_original
                        })

                        producto_id = nuevo_id
                        productos_creados += 1
                        mapa_alias[nombre_original] = producto_id
                        print(f"   [+] Creado: {nombre_nuevo}")
                    else:
                        continue

            # --- VERIFICACIÓN DE DUPLICADOS CON PREGUNTA ---
            if producto_id:
                insertar = True
                
                if producto_id in productos_ya_cargados_hoy:
                    # Si ya hay una decisión global tomada (ST o NT)
                    if accion_duplicados_global == "SI_A_TODOS":
                        insertar = True
                    elif accion_duplicados_global == "NO_A_TODOS":
                        insertar = False
                    else:
                        # Preguntar al usuario
                        print(f"\n   [!] El producto '{nombre_original}' YA FUE CARGADO HOY.")
                        print(f"       Stock nuevo a cargar: {stock_cantidad}")
                        print("       Opciones: [S] Si / [N] No / [ST] Si a todos / [NT] No a todos")
                        
                        while True:
                            resp = input("       >> ¿Registrar igual? ").strip().upper()
                            if resp == 'S':
                                insertar = True
                                break
                            elif resp == 'N':
                                insertar = False
                                break
                            elif resp == 'ST':
                                insertar = True
                                accion_duplicados_global = "SI_A_TODOS"
                                print("       [INFO] Se registrarán todos los duplicados restantes sin preguntar.")
                                break
                            elif resp == 'NT':
                                insertar = False
                                accion_duplicados_global = "NO_A_TODOS"
                                print("       [INFO] Se omitirán todos los duplicados restantes sin preguntar.")
                                break
                            else:
                                print("       Opción no válida.")

                if insertar:
                    session.execute(sql_insert_stock, {
                        "id": uuid4(),
                        "pid": producto_id,
                        "cid": competidor_id,
                        "stock": stock_cantidad,
                        "fecha": timestamp_ahora,
                        "origen": ORIGEN_CARGA
                    })
                    registros_insertados += 1
                    # Agregar al set para que si vuelve a aparecer en este mismo array, detecte duplicado
                    productos_ya_cargados_hoy.add(producto_id)
                else:
                    registros_saltados += 1

        session.commit()
        print(f"\n>> CARGA FINALIZADA:")
        print(f"   - Stock insertado: {registros_insertados}")
        print(f"   - Productos creados: {productos_creados}")
        print(f"   - Omitidos: {registros_saltados}")

    except Exception as e:
        if session: session.rollback()
        print(f"[ERROR CRÍTICO DB] {e}")
    finally:
        if session: session.close()

# ==============================================================================
# 3. EJECUCIÓN PRINCIPAL
# ==============================================================================

def menu_principal():
    existe_backup = os.path.exists(PATH_BACKUP_JSON)
    print("\n" + "="*40)
    print("       PANEL DE CONTROL DE STOCK")
    print("="*40)
    print("1. [NUEVO] Iniciar Scraping desde cero")
    if existe_backup:
        fecha_mod = datetime.fromtimestamp(os.path.getmtime(PATH_BACKUP_JSON))
        print(f"2. [BACKUP] Usar archivo guardado ({fecha_mod.strftime('%d/%m/%Y %H:%M:%S')})")
    else:
        print("2. [BACKUP] (No disponible)")
    print("3. Salir")
    print("-" * 40)
    
    while True:
        opcion = input(">> Seleccione una opción: ").strip()
        if opcion == "1": return "scrap"
        elif opcion == "2" and existe_backup: return "backup"
        elif opcion == "3": return "salir"
        else: print("Opción inválida.")

def main():
    accion = menu_principal()
    datos = []

    if accion == "salir": return

    elif accion == "scrap":
        datos = obtener_datos_scraping()
        if datos:
            try:
                os.makedirs(os.path.dirname(PATH_BACKUP_JSON), exist_ok=True)
                with open(PATH_BACKUP_JSON, "w", encoding="utf-8") as f:
                    json.dump(datos, f, indent=2, ensure_ascii=False)
                print(f"-> Backup actualizado: {PATH_BACKUP_JSON}")
            except Exception as e:
                print(f"[WARN] Error guardando backup: {e}")
        else:
            print("[FIN] Sin datos.")
            return

    elif accion == "backup":
        print(f"-> Cargando backup: {PATH_BACKUP_JSON}")
        try:
            with open(PATH_BACKUP_JSON, 'r', encoding='utf-8') as f:
                datos = json.load(f)
            print(f"-> {len(datos)} productos cargados.")
        except Exception as e:
            print(f"[ERROR] Error leyendo backup: {e}")
            return

    if datos:
        guardar_en_base_datos(datos)
    else:
        print("[INFO] No hay datos para procesar.")

if __name__ == "__main__":
    main()