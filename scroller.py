# -*- coding: utf-8 -*-
import time
import random
import re

# === Configuración de scrolleo dinámico ===
SCROLL_CARDS_PER_ITERATION = 3  # Cuántas cards scrollear cada vez
MODAL_TIMEOUT = 8.0
DATA_WAIT = 0.5
POLL_FREQ = 0.05
MIN_VISIBILITY_THRESHOLD = 0.80  # 80% de visibilidad mínima para hacer click

def extract_product_id_from_card(card_element, page):
    """Intenta extraer el ID del producto desde el elemento de la card."""
    try:
        parent = card_element.locator("xpath=ancestor::*[contains(@class, 'card') or contains(@class, 'producto')]").first
        
        if parent.count() > 0:
            attrs = page.evaluate("""(el) => {
                return {
                    id: el.id,
                    dataset: {...el.dataset},
                    className: el.className
                }
            }""", parent.element_handle())
            
            for key, value in attrs.get('dataset', {}).items():
                if 'producto' in key.lower() or 'id' in key.lower():
                    if value and value.isdigit():
                        return value
        
        link = card_element.locator("xpath=ancestor::a").first
        if link.count() > 0:
            href = link.get_attribute("href") or ""
            match = re.search(r'/producto[s]?/(\d+)|[?&]id=(\d+)', href)
            if match:
                return match.group(1) or match.group(2)
        
        img = card_element.locator("xpath=ancestor::*//img").first
        if img.count() > 0:
            src = img.get_attribute("src") or ""
            match = re.search(r'/(\d{3,})', src)
            if match:
                return match.group(1)
                
    except Exception as e:
        print(f"   [DEBUG] Error extrayendo ID: {e}", flush=True)
    
    return None

def wait_for_flutter_modal(page, timeout=MODAL_TIMEOUT):
    """
    Detecta el modal de Flutter usando múltiples estrategias.
    """
    t_start = time.time()
    
    print(f"   -> Buscando modal Flutter...", flush=True)
    
    while time.time() - t_start < timeout:
        try:
            # MÉTODO 1: Detectar el backdrop oscuro
            backdrop_found = page.evaluate("""() => {
                const glass = document.querySelector('flt-glass-pane');
                if (!glass || !glass.shadowRoot) return false;
                
                const backdrops = glass.shadowRoot.querySelectorAll('draw-rect');
                for (let rect of backdrops) {
                    const bg = rect.style.backgroundColor;
                    if (bg && bg.includes('0.54')) {
                        return true;
                    }
                }
                return false;
            }""")
            
            if backdrop_found:
                elapsed = time.time() - t_start
                print(f"   -> [✓] Modal detectado (BACKDROP) en {elapsed:.2f}s", flush=True)
                return True
            
            # MÉTODO 2: Detectar el modal blanco con shadow
            modal_found = page.evaluate("""() => {
                const glass = document.querySelector('flt-glass-pane');
                if (!glass || !glass.shadowRoot) return false;
                
                const clips = glass.shadowRoot.querySelectorAll('flt-clip[clip-type="physical-shape"]');
                for (let clip of clips) {
                    const style = clip.style;
                    if (style.backgroundColor === 'rgb(255, 255, 255)' && 
                        style.boxShadow && 
                        style.boxShadow.includes('rgba')) {
                        const width = parseFloat(style.width);
                        const height = parseFloat(style.height);
                        if (width > 400 && height > 500) {
                            return true;
                        }
                    }
                }
                return false;
            }""")
            
            if modal_found:
                elapsed = time.time() - t_start
                print(f"   -> [✓] Modal detectado (CONTAINER) en {elapsed:.2f}s", flush=True)
                return True
            
            # MÉTODO 3: Detectar por contenido específico del modal
            content_found = page.evaluate("""() => {
                const glass = document.querySelector('flt-glass-pane');
                if (!glass || !glass.shadowRoot) return false;
                
                const paragraphs = glass.shadowRoot.querySelectorAll('p');
                for (let p of paragraphs) {
                    const text = p.textContent || '';
                    if (text.includes('Mejor precio:') || text.includes('Cantidad desde')) {
                        return true;
                    }
                }
                return false;
            }""")
            
            if content_found:
                elapsed = time.time() - t_start
                print(f"   -> [✓] Modal detectado (CONTENT) en {elapsed:.2f}s", flush=True)
                return True
                
        except Exception as e:
            print(f"   [DEBUG] Error verificando modal: {e}", flush=True)
        
        time.sleep(POLL_FREQ)
    
    return False

def get_viewport_info(page):
    """
    Obtiene información dinámica del viewport incluyendo áreas obstruidas por headers/footers.
    """
    return page.evaluate("""() => {
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        
        // Detectar headers pegajosos
        let headerHeight = 0;
        const headerSelectors = [
            'header',
            '[role="banner"]',
            '.header',
            '.navbar',
            '.nav-bar',
            '.top-bar',
            '.site-header'
        ];
        
        for (const selector of headerSelectors) {
            const elements = document.querySelectorAll(selector);
            for (const el of elements) {
                const style = window.getComputedStyle(el);
                const position = style.position;
                
                if ((position === 'fixed' || position === 'sticky') && 
                    el.getBoundingClientRect().top <= 10) {
                    const rect = el.getBoundingClientRect();
                    headerHeight = Math.max(headerHeight, rect.bottom);
                }
            }
        }
        
        // Detectar footers pegajosos
        let footerHeight = 0;
        const footerSelectors = [
            'footer',
            '[role="contentinfo"]',
            '.footer',
            '.site-footer',
            '.bottom-bar'
        ];
        
        for (const selector of footerSelectors) {
            const elements = document.querySelectorAll(selector);
            for (const el of elements) {
                const style = window.getComputedStyle(el);
                const position = style.position;
                
                if ((position === 'fixed' || position === 'sticky')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.bottom >= viewportHeight - 10) {
                        footerHeight = Math.max(footerHeight, viewportHeight - rect.top);
                    }
                }
            }
        }
        
        const safeAreaTop = headerHeight;
        const safeAreaBottom = viewportHeight - footerHeight;
        const safeAreaHeight = safeAreaBottom - safeAreaTop;
        
        return {
            width: viewportWidth,
            height: viewportHeight,
            headerHeight: headerHeight,
            footerHeight: footerHeight,
            safeArea: {
                top: safeAreaTop,
                bottom: safeAreaBottom,
                height: safeAreaHeight
            }
        };
    }""")

def get_element_visibility(page, element):
    """
    Calcula el porcentaje de visibilidad de un elemento dentro del viewport.
    """
    try:
        return page.evaluate("""(el) => {
            const rect = el.getBoundingClientRect();
            const viewportHeight = window.innerHeight;
            
            const visibleTop = Math.max(0, rect.top);
            const visibleBottom = Math.min(viewportHeight, rect.bottom);
            const visibleHeight = Math.max(0, visibleBottom - visibleTop);
            
            const elementHeight = rect.height;
            const visibilityRatio = elementHeight > 0 ? visibleHeight / elementHeight : 0;
            
            return {
                visibility: visibilityRatio,
                top: rect.top,
                bottom: rect.bottom,
                height: rect.height,
                centerY: rect.top + rect.height / 2,
                isFullyVisible: rect.top >= 0 && rect.bottom <= viewportHeight,
                isPartiallyVisible: visibleHeight > 0
            };
        }""", element.element_handle())
    except Exception as e:
        print(f"   [DEBUG] Error calculando visibilidad: {e}", flush=True)
        return None

def calculate_dynamic_scroll_amount(page, viewport_info):
    """
    Calcula dinámicamente cuántos píxeles scrollear basándose en el tamaño de las cards visibles.
    """
    try:
        scroll_amount = page.evaluate("""() => {
            const cardSelectors = [
                '[class*="card"]',
                '[class*="producto"]',
                '[class*="item"]',
                'article'
            ];
            
            let avgCardHeight = 0;
            let cardCount = 0;
            
            for (const selector of cardSelectors) {
                const cards = document.querySelectorAll(selector);
                for (const card of cards) {
                    const rect = card.getBoundingClientRect();
                    if (rect.height > 100 && rect.height < 1000 && 
                        rect.top < window.innerHeight && rect.bottom > 0) {
                        avgCardHeight += rect.height;
                        cardCount++;
                        if (cardCount >= 5) break;
                    }
                }
                if (cardCount >= 5) break;
            }
            
            if (cardCount > 0) {
                avgCardHeight = avgCardHeight / cardCount;
                return Math.round(avgCardHeight * 1.1);
            }
            
            return Math.round(window.innerHeight * 0.7);
        }""")
        
        return scroll_amount * SCROLL_CARDS_PER_ITERATION
        
    except Exception as e:
        print(f"   [DEBUG] Error calculando scroll: {e}", flush=True)
        return viewport_info['height'] * 0.7

def get_clickeable_cards_in_viewport(page, viewport_info):
    """
    Obtiene todas las cards clickeables que están completamente visibles en el área segura.
    Retorna una lista de diccionarios con la información de cada card.
    """
    fichas = page.locator("text=/Ficha T.cnica/i")
    count = fichas.count()
    
    safe_top = viewport_info['safeArea']['top']
    safe_bottom = viewport_info['safeArea']['bottom']
    
    clickeable_items = []
    seen_products = set()  # Para deduplicar en esta iteración
    
    for i in range(count):
        try:
            target_text = fichas.nth(i)
            if not target_text.is_visible():
                continue
            
            # Targeting: preferir imagen sobre texto
            target_img = target_text.locator("xpath=preceding::img[1]")
            target_final = target_img if target_img.is_visible() else target_text
            
            # Obtener visibilidad
            visibility_info = get_element_visibility(page, target_final)
            if not visibility_info or not visibility_info['isPartiallyVisible']:
                continue
            
            element_center = visibility_info['centerY']
            
            # Verificar que esté en área segura con buena visibilidad
            if not (element_center >= safe_top and 
                    element_center <= safe_bottom and
                    visibility_info['visibility'] >= MIN_VISIBILITY_THRESHOLD):
                continue
            
            # Extraer ID del producto
            product_id = extract_product_id_from_card(target_final, page)
            
            # Crear clave única: product_id + posición redondeada
            pos_y = round(element_center / 10) * 10
            unique_key = f"{product_id}_{pos_y}"
            
            # Solo agregar si no lo hemos visto en esta iteración
            if unique_key not in seen_products:
                seen_products.add(unique_key)
                clickeable_items.append({
                    'element': target_final,
                    'tipo': "IMG" if target_img.is_visible() else "TXT",
                    'product_id': product_id,
                    'center_y': element_center,
                    'visibility': visibility_info['visibility']
                })
                
        except Exception as e:
            print(f"   [DEBUG] Error evaluando item {i}: {e}", flush=True)
            continue
    
    # Ordenar por posición vertical
    clickeable_items.sort(key=lambda x: x['center_y'])
    
    return clickeable_items

def auto_scroll_logic(page, state, save_callback=None):
    try:
        print("[SCROLL] Analizando viewport y geometría del grid...", flush=True)
        
        # === Configuración de Zona Segura ===
        SAFE_AREA_TOP = 180
        # Ajustamos dinámicamente según la ventana si es posible, o usamos fijo
        SAFE_AREA_HEIGHT = 800 
        SAFE_AREA_BOTTOM = SAFE_AREA_TOP + SAFE_AREA_HEIGHT
        
        # Localizar elementos
        fichas_locator = page.locator("text=/Ficha T.cnica/i") 
        count = fichas_locator.count()
        
        candidates = []
        
        # 1. ESCANEO Y MEDICIÓN
        if count > 0:
            for i in range(count):
                try:
                    element = fichas_locator.nth(i)
                    if not element.is_visible(): continue
                        
                    target_img = element.locator("xpath=preceding::img[1]")
                    target_final = target_img if target_img.is_visible() else element
                    tipo = "IMG" if target_img.is_visible() else "TXT"

                    box = target_final.bounding_box()
                    if not box: continue
                    
                    c_x = box["x"] + box["width"] / 2
                    c_y = box["y"] + box["height"] / 2
                    c_h = box["height"] # Guardamos la altura real
                    
                    # Filtro de Zona Segura
                    if c_y < SAFE_AREA_TOP or c_y > SAFE_AREA_BOTTOM:
                        continue
                        
                    candidates.append({
                        "index": i,
                        "element": target_final,
                        "x": c_x,
                        "y": c_y,
                        "h": c_h,
                        "tipo": tipo
                    })
                except:
                    continue

        # 2. ORDENAMIENTO (Filas y Columnas)
        # Ordenamos por Y (agrupando en filas de aprox 40px) y luego por X
        candidates.sort(key=lambda k: (int(k["y"] / 40), k["x"]))
        
        clicks_hechos = 0
        scroll_calculado = 0
        
        if candidates:
            # Cálculos para scroll dinámico basados en lo encontrado
            min_y = min(c["y"] for c in candidates) # Tope del bloque procesado
            max_y = max(c["y"] for c in candidates) # Fondo del bloque procesado
            avg_h = sum(c["h"] for c in candidates) / len(candidates) # Altura promedio card
            
            # La lógica es: Bajamos desde el primer item hasta el último + un margen (la altura de una card)
            # Esto hace que la fila que estaba debajo de todo, pase a estar arriba
            scroll_calculado = (max_y - min_y) + avg_h + 20 # 20px de gap extra
            
            print(f"[GRID] Detectados {len(candidates)} items. Bloque vertical: {scroll_calculado:.0f}px", flush=True)

            # 3. EJECUCIÓN
            for item in candidates:
                if not state["auto_scroll"]: return

                try:
                    # Verificación de vida del elemento
                    if not item["element"].is_visible():
                        # Intento de recuperación si el DOM cambió
                        item["element"] = fichas_locator.nth(item["index"])
                        
                    # Extracción ID
                    product_id = extract_product_id_from_card(item["element"], page)
                    msg_id = f"ID:{product_id}" if product_id else "?"
                    
                    print(f"[CLICK] ({item['x']:.0f},{item['y']:.0f}) {msg_id}", flush=True)

                    if product_id: state["waiting_for_product"] = product_id
                    
                    # Acción
                    page.mouse.move(item["x"], item["y"], steps=4)
                    page.mouse.down()
                    time.sleep(random.uniform(0.05, 0.1))
                    page.mouse.up()
                    
                    clicks_hechos += 1

                    # Espera de Modal
                    if wait_for_flutter_modal(page):
                        time.sleep(DATA_WAIT)
                        if save_callback: save_callback()
                    
                    state["waiting_for_product"] = None
                    page.keyboard.press("Escape")
                    time.sleep(0.3)
                    
                except Exception as e:
                    print(f"   [SKIP] Error en click: {e}", flush=True)
                    page.keyboard.press("Escape")

        # 4. SCROLL DINÁMICO
        dims = page.evaluate("() => ({ w: window.innerWidth, h: window.innerHeight })")
        
        # Si no calculamos nada (porque no hubo clicks) usamos un default del 60% de la pantalla
        if scroll_calculado == 0:
            scroll_calculado = dims['h'] * 0.6
            print(f"[SCROLL] Sin targets. Scroll default: {scroll_calculado:.0f}px", flush=True)
        else:
            print(f"[SCROLL] Bajando {scroll_calculado:.0f}px (calculado por grid)", flush=True)
        
        # Ejecutar Scroll
        page.mouse.move(dims['w'] / 2, dims['h'] / 2)
        page.mouse.wheel(0, scroll_calculado)
        time.sleep(0.8) # Importante: dar tiempo a que cargue el nuevo contenido
        
    except Exception as e:
        print(f"[ERROR CRITICO] {e}", flush=True)