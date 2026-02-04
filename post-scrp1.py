import pandas as pd
import json
import os
import sys
import re
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

def clean_float(val):
    """Limpia números que vienen como texto o null"""
    if val in (None, "", "null"): 
        return 0.0
    if isinstance(val, (int, float)): 
        return float(val)
    try:
        val = str(val).replace(',', '.').replace('$', '').replace('%', '').strip()
        return float(val)
    except:
        return 0.0

def extraer_info_html(html_raw):
    """Analiza la 'descripcion_larga' para sacar datos médicos"""
    if not html_raw or not isinstance(html_raw, str):
        return {}
    
    data = {}
    patterns = {
        "Proveedor": r"Proveedor:.*?><strong>(.*?)</strong>",
        "Acción": r"Acción Farmacológica:.*?><strong>(.*?)</strong>",
        "Especie": r"Especie:.*?><strong>(.*?)</strong>",
        "Presentación": r"Presentación:.*?><strong>(.*?)</strong>",
        "Laboratorio": r"Laboratorio:.*?><strong>(.*?)</strong>"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, html_raw, re.IGNORECASE | re.DOTALL)
        if match:
            clean_text = match.group(1).replace("&nbsp;", " ").strip()
            data[key] = clean_text
            
    return data

def generar_archivos():
    # CONFIGURACIÓN DE RUTAS
    project_root = Path(__file__).parent
    output_dir = project_root / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    json_path = project_root / "data/panacea_clicks_enriquecido.json"
    diccionario_path = project_root / "data/diccionario_panacea.json"
    
    excel_full_path = output_dir / "Panacea_Completo.xlsx"
    csv_simple_path = output_dir / "Panacea_Resumen_Precios.csv"
    csv_errores_path = output_dir / "Panacea_Mapeo_Errores.csv"

    print(f"[INFO] Procesando archivos en: {project_root}")

    # 1. CARGA DE DATOS
    if not json_path.exists():
        print(f"[ERROR] No se encontró: {json_path}")
        return

    try:
        content = json_path.read_text(encoding="utf-8")
        data = json.loads(content)
        productos = data.get("productos", [])
    except Exception as e:
        print(f"[ERROR] Error al leer JSON: {e}")
        return

    print(f"[INFO] Total productos: {len(productos)}")

    # 2. PROCESAMIENTO
    rows = []
    for p in productos:
        info_extra = extraer_info_html(p.get("descripcion_larga", ""))
        
        # Cálculos de Precios
        precio_base = clean_float(p.get("precio_base", 0))
        desc_esp = clean_float(p.get("descuento_especial", 0))
        if desc_esp > 1: desc_esp = desc_esp / 100.0
        bonif = clean_float(p.get("bonificacion", 0))
        if bonif > 1: bonif = bonif / 100.0
        desc_fin = clean_float(p.get("descuento_financiero", 0))
        if desc_fin > 1: desc_fin = desc_fin / 100.0
        mejor_precio_neto = clean_float(p.get("mejor_precio", 0))
        
        precio_calc = precio_base * (1 - bonif) * (1 - desc_esp) * (1 - desc_fin)
        precio_final_neto = mejor_precio_neto if mejor_precio_neto > 0 else precio_calc
        precio_final_iva = precio_final_neto * 1.21

        # Datos de Stock
        stock_actual = clean_float(p.get("stock", 0))
        stock_min = clean_float(p.get("stock_minimo", 0))
        vencimiento = p.get("fecha_vencimiento", "")
        if "0000" in str(vencimiento): vencimiento = ""
        dias_sin_stock = p.get("stock_dias_sin_stock", "0")

        rows.append({
            "ID": p.get("id_producto", ""),
            "Código": p.get("codigo", ""),
            "Descripción": p.get("descripcion", ""),
            "Tipo": p.get("producto_tipo", ""),
            "Proveedor/Lab": info_extra.get("Proveedor") or info_extra.get("Laboratorio") or p.get("producto_marca", ""),
            "Acción Farmacológica": info_extra.get("Acción", ""),
            "Especie": info_extra.get("Especie", ""),
            "Presentación": info_extra.get("Presentación", ""),
            "Vencimiento": vencimiento,
            "Stock Actual": int(stock_actual),
            "Stock Mínimo": int(stock_min),
            "Estado Stock": "CRÍTICO" if stock_actual <= stock_min else "OK",
            "Días s/Stock": dias_sin_stock,
            "Cant. Min. Compra": int(clean_float(p.get("cantidad_desde_optima", 1))),
            "Precio Lista": precio_base,
            "Bonif. %": bonif,
            "Desc. Esp. %": desc_esp,
            "Desc. Fin. %": desc_fin,
            "NETO (Unitario)": precio_final_neto,
            "FINAL c/IVA (Estimado)": precio_final_iva
        })

    df = pd.DataFrame(rows)

    cols_order = [
        "ID", "Código", "Descripción", "Tipo", 
        "Proveedor/Lab", "Acción Farmacológica", "Especie", "Presentación",
        "Vencimiento", "Stock Actual", "Stock Mínimo", "Estado Stock", "Días s/Stock",
        "Cant. Min. Compra", "Precio Lista", "Bonif. %", "Desc. Esp. %", "Desc. Fin. %",
        "NETO (Unitario)", "FINAL c/IVA (Estimado)"
    ]
    df = df[[c for c in cols_order if c in df.columns]]

    # 3. EXCEL COMPLETO
    print(f"[INFO] Generando Excel: {excel_full_path}")
    try:
        with pd.ExcelWriter(excel_full_path, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Stock y Precios')
            workbook = writer.book
            worksheet = writer.sheets['Stock y Precios']
            
            fmt_header = workbook.add_format({'bold': True, 'bg_color': '#4F81BD', 'font_color': 'white', 'border': 1})
            fmt_currency = workbook.add_format({'num_format': '$ #,##0.00'})
            fmt_pct = workbook.add_format({'num_format': '0.0%'})
            fmt_date = workbook.add_format({'num_format': 'dd/mm/yyyy', 'align': 'center'})
            fmt_alert_red = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
            fmt_alert_green = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
            
            worksheet.set_column('A:B', 10)
            worksheet.set_column('C:C', 40)
            worksheet.set_column('D:E', 20)
            worksheet.set_column('F:H', 25)
            worksheet.set_column('I:I', 12, fmt_date)
            worksheet.set_column('J:K', 10)
            worksheet.set_column('L:L', 12)
            worksheet.set_column('O:O', 12, fmt_currency)
            worksheet.set_column('P:R', 8, fmt_pct)
            worksheet.set_column('S:T', 15, fmt_currency)

            worksheet.conditional_format('L2:L5000', {'type': 'cell', 'criteria': 'equal to', 'value': '"CRÍTICO"', 'format': fmt_alert_red})
            worksheet.conditional_format('L2:L5000', {'type': 'cell', 'criteria': 'equal to', 'value': '"OK"', 'format': fmt_alert_green})

            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, fmt_header)
        
        print(f"[OK] Excel generado.")
    except Exception as e:
        print(f"[ERROR] Falló Excel: {e}")

    # 4. CSV CON GESTIÓN INTELIGENTE DE DUPLICADOS
    print(f"[INFO] Generando CSV con resolución de duplicados...")

    if not diccionario_path.exists():
        print(f"[ERROR] No se encontró diccionario: {diccionario_path}")
        return

    try:
        diccionario_contenido = diccionario_path.read_text(encoding="utf-8")
        mapping = json.loads(diccionario_contenido)

        # Estructuras para gestionar duplicados
        productos_por_id = defaultdict(list)
        errores = []

        # Primera pasada: recopilar todos los productos por ID
        for _, row in df.iterrows():
            nombre_origen = row["Descripción"]
            
            if nombre_origen in mapping:
                info_map = mapping[nombre_origen]
                mi_id = info_map.get("mi_id")
                mi_nombre = info_map.get("mi_nombre", nombre_origen)
                match_score = info_map.get("match_score", 0)
                estado = info_map.get("estado", "DESCONOCIDO")
                precio_neto = row["NETO (Unitario)"]
                
                # Factor de conversión (ajusta según tu necesidad)
                # Si este factor es correcto, déjalo; si no, cámbialo
                precio_final = precio_neto / 0.779 if precio_neto > 0 else 0

                if mi_id is not None and mi_id > 0:
                    productos_por_id[mi_id].append({
                        "nombre_panacea": nombre_origen,
                        "nombre_final": mi_nombre,
                        "precio": precio_final,
                        "precio_neto": precio_neto,
                        "match_score": match_score,
                        "estado": estado,
                        "stock": row["Stock Actual"],
                        "codigo": row["Código"]
                    })
            else:
                errores.append({
                    "nombre_panacea": nombre_origen,
                    "precio_neto": row["NETO (Unitario)"],
                    "stock": row["Stock Actual"],
                    "error": "Sin mapeo en diccionario"
                })

        # Segunda pasada: resolver duplicados con estrategia inteligente
        rows_mapped = []
        
        print(f"\n[INFO] Analizando {len(productos_por_id)} IDs únicos...")
        
        for mi_id, productos in productos_por_id.items():
            if len(productos) == 1:
                # Caso simple: un solo producto para este ID
                p = productos[0]
                rows_mapped.append({
                    "producto_id": mi_id,
                    "nombre": p['nombre_final'],
                    "precio": p['precio']
                })
            else:
                # DUPLICADOS: aplicar estrategia de resolución
                print(f"\n[WARN] ID {mi_id} tiene {len(productos)} productos:")
                
                # Filtrar por calidad de match
                buenos_matches = [p for p in productos if p['match_score'] >= 70]
                
                if not buenos_matches:
                    # Si ninguno es bueno, tomar el mejor disponible
                    mejor = max(productos, key=lambda x: x['match_score'])
                    print(f"  ⚠ Ningún match >70%. Usando mejor disponible: {mejor['nombre_panacea']} ({mejor['match_score']}%)")
                    
                    rows_mapped.append({
                        "producto_id": mi_id,
                        "nombre": mejor['nombre_final'],
                        "precio": mejor['precio']
                    })
                    
                    # Registrar como error
                    for p in productos:
                        errores.append({
                            "producto_id": mi_id,
                            "nombre_panacea": p['nombre_panacea'],
                            "precio": p['precio'],
                            "match_score": p['match_score'],
                            "stock": p['stock'],
                            "error": f"Duplicado - match bajo - descartado" if p != mejor else "Duplicado - seleccionado por match"
                        })
                else:
                    # Estrategia: 
                    # 1. Si hay productos con STOCK > 0, preferirlos
                    # 2. Entre productos con stock, elegir el de MAYOR PRECIO (más conservador)
                    # 3. Si no hay stock, elegir el de mayor match_score
                    
                    con_stock = [p for p in buenos_matches if p['stock'] > 0]
                    
                    if con_stock:
                        # Elegir el de MAYOR precio entre los que tienen stock
                        elegido = max(con_stock, key=lambda x: x['precio'])
                        criterio = "mayor precio con stock"
                    else:
                        # Elegir el de mejor match
                        elegido = max(buenos_matches, key=lambda x: x['match_score'])
                        criterio = "mejor match (sin stock)"
                    
                    print(f"  ✓ Seleccionado: {elegido['nombre_panacea']}")
                    print(f"    Criterio: {criterio} | Precio: ${elegido['precio']:.2f} | Match: {elegido['match_score']}%")
                    
                    rows_mapped.append({
                        "producto_id": mi_id,
                        "nombre": elegido['nombre_final'],
                        "precio": elegido['precio']
                    })
                    
                    # Registrar los descartados
                    for p in productos:
                        if p != elegido:
                            print(f"    ✗ Descartado: {p['nombre_panacea']} (${p['precio']:.2f} | {p['match_score']}%)")
                            errores.append({
                                "producto_id": mi_id,
                                "nombre_panacea": p['nombre_panacea'],
                                "nombre_final": p['nombre_final'],
                                "precio": p['precio'],
                                "match_score": p['match_score'],
                                "stock": p['stock'],
                                "error": f"Duplicado descartado - se eligió otro por {criterio}"
                            })

        # Crear DataFrame final
        df_simple = pd.DataFrame(rows_mapped)
        
        if df_simple.empty:
            print("[WARN] No se generaron registros para el CSV.")
        else:
            df_simple = df_simple[["producto_id", "nombre", "precio"]]
            df_simple = df_simple.sort_values('producto_id')
            
            df_simple.to_csv(
                csv_simple_path, 
                index=False, 
                sep=';', 
                decimal=',', 
                encoding='utf-8-sig'
            )
            print(f"\n[OK] CSV generado: {len(df_simple)} productos únicos")

        # Guardar reporte de errores
        if errores:
            df_errores = pd.DataFrame(errores)
            df_errores.to_csv(
                csv_errores_path,
                index=False,
                sep=';',
                decimal=',',
                encoding='utf-8-sig'
            )
            print(f"[INFO] Reporte de errores guardado: {len(errores)} registros")
            
        if sys.platform == 'win32':
            os.startfile(output_dir)

    except Exception as e:
        print(f"[ERROR] Falló CSV: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    generar_archivos()