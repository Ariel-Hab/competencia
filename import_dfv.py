import pandas as pd
import os
from sqlalchemy import text
from diccionario_manager import DiccionarioManager

def importar_dfv_ids_robusto(csv_file: str):
    print(f"--- 📂 Leyendo archivo: {csv_file} ---")
    
    if not os.path.exists(csv_file):
        print(f"❌ El archivo {csv_file} no existe.")
        return

    manager = DiccionarioManager()
    
    try:
        # Cargar CSV
        df = pd.read_csv(csv_file, encoding='utf-8', dtype={'ID': str})
        df.columns = [c.strip() for c in df.columns]

        if 'ID' not in df.columns or 'PRODUCTO' not in df.columns:
            print("❌ Faltan columnas 'ID' o 'PRODUCTO'")
            return

        print(f"📊 Procesando {len(df)} filas con confirmación individual...")
        
        updates = 0
        errores = 0

        # Abrimos la conexión SIN autocommit global
        with manager.engine.connect() as conn:
            
            # Query preparada
            sql_update = text("""
                UPDATE productos 
                SET dfv_id = :new_id 
                WHERE nombre_producto ILIKE :nombre_busqueda
            """)

            for index, row in df.iterrows():
                # Iniciamos una "mini transacción" por cada fila
                # Esto aísla los errores: si una fila falla, no afecta a las siguientes.
                trans = conn.begin()
                
                try:
                    raw_id = str(row['ID']).strip()
                    raw_nombre = str(row['PRODUCTO']).strip()
                    nombre_limpio = raw_nombre.lstrip('.').strip()

                    if not raw_id or not nombre_limpio:
                        trans.rollback() # Si no hay datos, cerramos limpio
                        continue
                    
                    # Ejecutar actualización
                    result = conn.execute(sql_update, {
                        "new_id": raw_id,
                        "nombre_busqueda": nombre_limpio
                    })
                    
                    # Si todo salió bien, guardamos (COMMIT)
                    trans.commit()

                    if result.rowcount > 0:
                        updates += result.rowcount
                        # print(f"✅ OK: {nombre_limpio[:20]}... -> {raw_id}")
                    
                except Exception as e:
                    # Si algo falla, revertimos (ROLLBACK) para limpiar la conexión
                    trans.rollback()
                    errores += 1
                    print(f"⚠️ Error REAL en fila {index} ({nombre_limpio}): {e}")

        print("-" * 30)
        print(f"🚀 Proceso terminado.")
        print(f"✅ Actualizados: {updates}")
        print(f"❌ Errores: {errores}")

    except Exception as global_e:
        print(f"❌ Error crítico de conexión: {global_e}")

if __name__ == "__main__":
    nombre_archivo = input("Ingresa el nombre del archivo CSV (ej: datos.csv): ").strip()
    nombre_archivo = nombre_archivo.replace('"', '').replace("'", "")
    importar_dfv_ids_robusto(nombre_archivo)