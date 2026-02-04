# -*- coding: utf-8 -*-
import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from uuid import uuid4

# Librerías de ML y Data
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.feature_extraction.text import TfidfVectorizer # <--- FALTABA ESTE IMPORT

# SQLAlchemy Imports
from sqlalchemy import create_engine, text, func, Column, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.dialects.postgresql import UUID
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# DEFINICIÓN LOCAL DE MODELOS (Para no depender de src.core.models)
# ============================================================================
Base = declarative_base()

class TipoAlias:
    """Simulación de la clase o Enum que tenías en src"""
    PROVEEDOR = "PROVEEDOR"
    MANUAL = "MANUAL"

class Producto(Base):
    __tablename__ = 'productos'
    
    # Definimos solo los campos que usas en este script para no complicarnos
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    nombre_producto = Column(String)
    activo = Column(Boolean, default=True)
    # created_at/updated_at no son estrictamente necesarios para consultas de lectura

class ProductoAlias(Base):
    __tablename__ = 'producto_alias'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    producto_id = Column(UUID(as_uuid=True), ForeignKey('productos.id'))
    termino_busqueda = Column(String)  # El nombre normalizado
    texto_original = Column(String)    # El nombre que viene de Panacea
    origen = Column(String)            # 'PROVEEDOR'
    confianza = Column(Float, default=100.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    external_id = Column(String, nullable=True) 

# ============================================================================
# CLASE PRINCIPAL
# ============================================================================

class DiccionarioManager:
    """Gestor unificado para el diccionario de traducciones Panacea <-> Mi Sistema"""
    
    def __init__(self):
        print("--- [DEBUG] Iniciando DiccionarioManager (Modo Local) ---")
        
        # Configuración de base de datos
        # Al estar en Windows con .env, esto tomará localhost
        DB_HOST = os.getenv("DB_HOST", "localhost")
        DB_PORT = os.getenv("DB_PORT", "5435")
        DB_NAME = os.getenv("DB_NAME", "presupuestacion_db")
        DB_USER = os.getenv("DB_USER", "postgres")
        DB_PASS = os.getenv("DB_PASS", "password")
        
        self.db_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        
        # Ajuste para Docker (Por si lo vuelves a subir al contenedor)
        if "localhost" in self.db_url and os.path.exists("/.dockerenv"):
            self.db_url = self.db_url.replace("localhost", "db")
            print(f"--- [DEBUG] Docker detectado. Usando host interno: {self.db_url} ---")
        else:
            print(f"--- [DEBUG] Windows detectado. Usando: {self.db_url} ---")
        
        self.engine = create_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)
        
        # Test de conexión
        try:
            with self.engine.connect() as conn:
                res = conn.execute(text("SELECT 1")).scalar()
                print("--- [DEBUG] ✅ Conexión a BD exitosa ---")
        except Exception as e:
            print(f"--- [DEBUG] ❌ ERROR DE CONEXIÓN BD: {e}")
            print("Asegúrate de tener el puerto 5432 expuesto en Docker y el archivo .env creado.")
        
        self._productos_cache = None
        self._vectorizer = None
        self._nn_model = None
    
    # ------------------------------------------------------------------------
    # (El resto del código es idéntico al tuyo, solo he arreglado imports faltantes)
    # ------------------------------------------------------------------------

    def normalizar_texto(self, texto: str) -> str:
        if not texto: return ""
        texto = texto.upper().strip()
        texto = texto.replace(',', '.')
        texto = re.sub(r'\s*-\s*', '-', texto)
        
        traducciones = {
            'GOLD': 'DORADO', 'YELLOW': 'DORADO', 'PURPLE': 'PURPURA', 'VIOLET': 'PURPURA',
            'CARAMEL': 'CARAMELO', 'ORANGE': 'CARAMELO', 'TEAL': 'AZUL', 'BLUE': 'AZUL',
            'GREEN': 'VERDE', 'BROWN': 'MARRON'
        }
        for eng, esp in traducciones.items():
            texto = re.sub(rf'\b{eng}\b', esp, texto)
        
        # Normalizaciones médicas
        texto = re.sub(r'\b(ML|CC|CM3|MILILITROS?)\b', 'ML', texto)
        texto = re.sub(r'\b(GR|GRS|GRAM|GRAMOS?)\b', 'GR', texto)
        texto = re.sub(r'\b(KG|KGS|KILO|KILOS)\b', 'KG', texto)
        texto = re.sub(r'\b(MG|MGR|MILIGRAMOS?)\b', 'MG', texto)
        texto = re.sub(r'\b(COMP|COMPRIMIDOS?|CS|CAPS|CAPSULAS?|TAB|TABLETS?|TABLETAS?)\b', 'COMP', texto)
        texto = re.sub(r'\b(AMP|AMPOLLA|AMPOLLAS|FCO|FRASCO|FRASCOS|VIALES|VIAL)\b', 'AMP', texto)
        texto = re.sub(r'\b(INY|INYECTABLE|INYECCION)\b', 'INY', texto)
        texto = re.sub(r'\b(SUSP|SUSPENSION)\b', 'SUSP', texto)
        texto = re.sub(r'\b(SOL|SOLUCION)\b', 'SOL', texto)
        texto = re.sub(r'\b(GOT|GOTAS)\b', 'GOT', texto)
        texto = re.sub(r'\b(PALAT|PALATABLE|MASTICABLE|MASTICABLES)\b', 'PALAT', texto)
        
        texto = re.sub(r'\bPOR\b', 'X', texto)
        texto = re.sub(r'(?<=\d)\s*[xX×]\s*(?=\d)', ' X ', texto)
        texto = re.sub(r'\s+[xX×]\s+(?=\d)', ' X ', texto)
        texto = re.sub(r'\s+', ' ', texto)
        return texto.strip()
    
    def get_stats(self) -> Dict:
        try:
            with self.Session() as session:
                total_productos = session.query(func.count(Producto.id)).scalar()
                
                total_traducciones = session.query(func.count(ProductoAlias.id)).filter(
                    ProductoAlias.origen == TipoAlias.PROVEEDOR
                ).scalar()
                
                productos_traducidos = session.query(func.count(func.distinct(ProductoAlias.producto_id))).filter(
                    ProductoAlias.origen == TipoAlias.PROVEEDOR
                ).scalar()
                
                confianza_alta = session.query(func.count(ProductoAlias.id)).filter(
                    ProductoAlias.origen == TipoAlias.PROVEEDOR, ProductoAlias.confianza >= 90
                ).scalar()
                
                confianza_media = session.query(func.count(ProductoAlias.id)).filter(
                    ProductoAlias.origen == TipoAlias.PROVEEDOR, ProductoAlias.confianza >= 70, ProductoAlias.confianza < 90
                ).scalar()
                
                confianza_baja = session.query(func.count(ProductoAlias.id)).filter(
                    ProductoAlias.origen == TipoAlias.PROVEEDOR, ProductoAlias.confianza < 70
                ).scalar()
                
                return {
                    "total_productos": total_productos,
                    "total_traducciones": total_traducciones,
                    "productos_traducidos": productos_traducidos,
                    "productos_sin_traducir": (total_productos or 0) - (productos_traducidos or 0),
                    "confianza": {"alta": confianza_alta, "media": confianza_media, "baja": confianza_baja}
                }
        except Exception as e:
            print(f"--- [DEBUG] ERROR en get_stats: {e} ---")
            return {} # Retornar vacío en vez de romper
    
    def list_traducciones(self, page: int = 1, per_page: int = 50, filtro: str = 'todos', search: str = '') -> Dict:
        try:
            with self.Session() as session:
                query = session.query(ProductoAlias).filter(ProductoAlias.origen == TipoAlias.PROVEEDOR)
                
                if search:
                    query = query.filter(ProductoAlias.texto_original.ilike(f'%{search}%'))
                
                query = query.order_by(ProductoAlias.confianza.desc(), ProductoAlias.texto_original)
                total = query.count()
                offset = (page - 1) * per_page
                items = query.offset(offset).limit(per_page).all()
                
                resultados = []
                for alias in items:
                    producto = session.query(Producto).filter(Producto.id == alias.producto_id).first()
                    resultados.append({
                        "id": str(alias.id),
                        "external_id": alias.external_id,
                        "nombre_panacea": alias.texto_original,
                        "nombre_normalizado": alias.termino_busqueda,
                        "producto_id": str(alias.producto_id),
                        "nombre_producto": producto.nombre_producto if producto else "⚠️ Producto no encontrado",
                        "confianza": alias.confianza,
                        "created_at": alias.created_at.isoformat() if alias.created_at else None
                    })
                
                return {
                    "items": resultados, "total": total, "page": page, "per_page": per_page,
                    "total_pages": (total + per_page - 1) // per_page
                }
        except Exception as e:
            print(f"--- [DEBUG] ERROR en list_traducciones: {e} ---")
            return {"items": [], "total": 0}

    def search_productos(self, search: str, limit: int = 20) -> List[Dict]:
        try:
            with self.Session() as session:
                query = session.query(Producto).filter(Producto.nombre_producto.ilike(f'%{search}%')).limit(limit)
                return [{"id": str(p.id), "nombre": p.nombre_producto} for p in query.all()]
        except Exception as e:
            print(f"--- [DEBUG] ERROR en search_productos: {e} ---")
            return []

    def add_traduccion(self, nombre_panacea: str, producto_id: str, confianza: float = 100.0) -> Dict:
        with self.Session() as session:
            producto = session.query(Producto).filter(Producto.id == producto_id).first()
            if not producto: raise ValueError(f"Producto {producto_id} no encontrado")
            
            nombre_normalizado = self.normalizar_texto(nombre_panacea)
            alias_existente = session.query(ProductoAlias).filter(
                ProductoAlias.producto_id == producto_id, ProductoAlias.texto_original == nombre_panacea
            ).first()
            
            if alias_existente:
                alias_existente.termino_busqueda = nombre_normalizado
                alias_existente.confianza = confianza
                session.commit()
                return {"accion": "actualizado", "id": str(alias_existente.id), "nombre_panacea": nombre_panacea, "producto": producto.nombre_producto}
            else:
                nuevo_alias = ProductoAlias(
                    id=uuid4(), producto_id=producto_id, termino_busqueda=nombre_normalizado,
                    texto_original=nombre_panacea, origen=TipoAlias.PROVEEDOR, confianza=confianza
                )
                session.add(nuevo_alias)
                session.commit()
                return {"accion": "creado", "id": str(nuevo_alias.id), "nombre_panacea": nombre_panacea, "producto": producto.nombre_producto}

    def delete_traduccion(self, alias_id: str):
        with self.Session() as session:
            alias = session.query(ProductoAlias).filter(ProductoAlias.id == alias_id).first()
            if not alias: raise ValueError(f"Traducción {alias_id} no encontrada")
            session.delete(alias)
            session.commit()

    def _load_productos_cache(self):
        if self._productos_cache is not None: return
        try:
            with self.Session() as session:
                productos = session.query(Producto).all()
                self._productos_cache = pd.DataFrame([{
                    'id': str(p.id), 'nombre': p.nombre_producto, 'nombre_limpio': self.normalizar_texto(p.nombre_producto)
                } for p in productos])
            
            self._vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 5), max_features=6000, min_df=1, sublinear_tf=True)
            tfidf_matrix = self._vectorizer.fit_transform(self._productos_cache['nombre_limpio'])
            self._nn_model = NearestNeighbors(n_neighbors=5, metric='cosine', n_jobs=-1)
            self._nn_model.fit(tfidf_matrix)
            print(f"✅ Cache cargado: {len(self._productos_cache)} productos")
        except Exception as e:
             print(f"--- [DEBUG] Error en _load_productos_cache: {e} ---")
             raise e

    def get_sugerencias(self, nombre_panacea: str, top_n: int = 5) -> List[Dict]:
        self._load_productos_cache()
        nombre_limpio = self.normalizar_texto(nombre_panacea)
        vec = self._vectorizer.transform([nombre_limpio])
        distancias, indices = self._nn_model.kneighbors(vec)
        sugerencias = []
        for i in range(min(top_n, len(indices[0]))):
            idx = indices[0][i]
            confianza = (1 - distancias[0][i]) * 100
            row = self._productos_cache.iloc[idx]
            sugerencias.append({'producto_id': row['id'], 'nombre': row['nombre'], 'confianza': round(confianza, 2)})
        return sugerencias

    def auto_match(self, umbral: float = 80.0, limite: int = 100) -> Dict:
        try:
            self._load_productos_cache()
            json_path = Path("outputs/panacea_clicks_enriquecido.json")
            if not json_path.exists(): raise FileNotFoundError("No se encontró JSON de scraping")
            
            with open(json_path, 'r', encoding='utf-8') as f: data = json.load(f)
            productos_panacea = data.get("productos", [])
            
            with self.Session() as session:
                sin_traduccion = []
                for p in productos_panacea[:limite]:
                    nombre = p.get("descripcion", "").strip()
                    if not nombre: continue
                    if not session.query(ProductoAlias).filter(ProductoAlias.texto_original == nombre, ProductoAlias.origen == TipoAlias.PROVEEDOR).first():
                        sin_traduccion.append(nombre)
                
                insertados = 0
                for nombre_panacea in sin_traduccion:
                    nombre_limpio = self.normalizar_texto(nombre_panacea)
                    vec = self._vectorizer.transform([nombre_limpio])
                    distancias, indices = self._nn_model.kneighbors(vec, n_neighbors=1)
                    confianza = (1 - distancias[0][0]) * 100
                    
                    if confianza >= umbral:
                        idx = indices[0][0]
                        nuevo_alias = ProductoAlias(
                            id=uuid4(), producto_id=self._productos_cache.iloc[idx]['id'],
                            termino_busqueda=nombre_limpio, texto_original=nombre_panacea,
                            origen=TipoAlias.PROVEEDOR, confianza=confianza
                        )
                        session.add(nuevo_alias)
                        insertados += 1
                        print(f"MATCH: {nombre_panacea} ({confianza:.1f}%)")
                session.commit()
            return {"insertados": insertados}
        except Exception as e:
            print(f"[ERROR] auto_match: {e}")
            raise e

    def export_to_json(self) -> Path:
        output_path = Path("outputs/diccionario_panacea.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.Session() as session:
            alias_list = session.query(ProductoAlias).filter(ProductoAlias.origen == TipoAlias.PROVEEDOR).all()
            diccionario = {}
            for alias in alias_list:
                producto = session.query(Producto).filter(Producto.id == alias.producto_id).first()
                diccionario[alias.texto_original] = {
                    "mi_id": str(alias.producto_id), "mi_nombre": producto.nombre_producto if producto else "Desconocido",
                    "match_score": alias.confianza, "estado": "EXACTO" if alias.confianza >= 90 else "APROXIMADO"
                }
        with open(output_path, 'w', encoding='utf-8') as f: json.dump(diccionario, f, ensure_ascii=False, indent=2)
        return output_path

    def import_from_txt(self, filepath: Path) -> Dict:
        self._load_productos_cache()
        with open(filepath, 'r', encoding='utf-8') as f: lineas = [l.strip() for l in f if l.strip()]
        resultados = {"total": len(lineas), "insertados": 0}
        
        with self.Session() as session:
            for nombre_panacea in lineas:
                try:
                    if session.query(ProductoAlias).filter(ProductoAlias.texto_original == nombre_panacea, ProductoAlias.origen == TipoAlias.PROVEEDOR).first(): continue
                    
                    nombre_limpio = self.normalizar_texto(nombre_panacea)
                    vec = self._vectorizer.transform([nombre_limpio])
                    distancias, indices = self._nn_model.kneighbors(vec, n_neighbors=1)
                    confianza = (1 - distancias[0][0]) * 100
                    
                    session.add(ProductoAlias(
                        id=uuid4(), producto_id=self._productos_cache.iloc[indices[0][0]]['id'],
                        termino_busqueda=nombre_limpio, texto_original=nombre_panacea,
                        origen=TipoAlias.PROVEEDOR, confianza=confianza
                    ))
                    resultados["insertados"] += 1
                except: pass
            session.commit()
        return resultados