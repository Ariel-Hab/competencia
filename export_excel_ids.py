import pandas as pd
from sqlalchemy import text
from diccionario_manager import DiccionarioManager, TipoAlias

def exportar_traducciones():
    print("--- Iniciando exportación a Excel ---")
    
    manager = DiccionarioManager()
    
    # Query SQL
    query_str = f"""
        SELECT 
            pa.external_id AS "ID Panacea",
            pa.texto_original AS "Nombre Panacea",
            p.dfv_id AS "ID Nuestro",
            p.nombre_producto AS "Nombre Nuestro"
        FROM producto_alias pa
        LEFT JOIN productos p ON pa.producto_id = p.id
        WHERE pa.origen = '{TipoAlias.PROVEEDOR}'
        ORDER BY pa.texto_original ASC;
    """

    try:
        # CORRECCIÓN: Usamos una conexión explícita (context manager)
        # Esto soluciona el error 'immutabledict is not a sequence' en SQLAlchemy 2.0
        with manager.engine.connect() as conn:
            # Envolviendo en text() para mayor seguridad en SA 2.0 (aunque Pandas suele manejarlo)
            df = pd.read_sql(text(query_str), conn)

        if df.empty:
            print("⚠️ No se encontraron traducciones para exportar.")
            return

        output_file = "traducciones_panacea.xlsx"
        df.to_excel(output_file, index=False)
        
        print(f"✅ Exportación exitosa: {output_file}")
        print(f"📊 Total de filas exportadas: {len(df)}")

    except Exception as e:
        print(f"❌ Error durante la exportación: {e}")
        # Imprimimos el tipo de error para debug
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    exportar_traducciones()