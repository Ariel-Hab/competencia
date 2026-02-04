// ============================================================================
// SISTEMA DE PESTAÑAS
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Inicializar pestañas
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');

            // Desactivar todas
            tabButtons.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            // Activar la seleccionada
            btn.classList.add('active');
            document.getElementById(`tab-${targetTab}`).classList.add('active');

            // Si es diccionario, cargar datos
            if (targetTab === 'diccionario') {
                DiccionarioModule.init();
            } else if (targetTab === 'scraper') {
                ScraperModule.init();
            }
        });
    });

    // Inicializar el módulo activo
    ScraperModule.init();
});

// ============================================================================
// UTILIDADES
// ============================================================================

const Utils = {
    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast show ${type}`;

        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    },

    formatDate(dateString) {
        if (!dateString) return '-';
        const date = new Date(dateString);
        return date.toLocaleDateString('es-AR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    getConfianzaBadge(confianza) {
        if (confianza >= 90) return 'badge-alta';
        if (confianza >= 70) return 'badge-media';
        return 'badge-baja';
    }
};

// ============================================================================
// MÓDULO: SCRAPER
// ============================================================================

const ScraperModule = {
    isRunning: false,
    autoScrollActive: false,
    refreshInterval: null,

    init() {
        this.startStatusRefresh();
    },

    startStatusRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }

        this.refreshInterval = setInterval(() => {
            this.refreshStatus();
        }, 800);
    },

    async refreshStatus() {
        try {
            const response = await fetch('/scraper/status');
            const data = await response.json();

            const log = document.getElementById('scraperLog');
            log.textContent = (data.log || []).join('\n');
            log.scrollTop = log.scrollHeight;

            const statusDot = document.getElementById('statusDot');
            const statusText = document.getElementById('statusText');
            const taskText = document.getElementById('taskText');
            const scrollStatus = document.getElementById('scrollStatus');

            this.isRunning = data.running;

            if (data.running) {
                statusDot.classList.add('active');
                statusText.textContent = 'Activo';
                taskText.textContent = data.task || 'Corriendo...';
                document.getElementById('scraperBtn').disabled = true;
                document.getElementById('scrollBtn').disabled = false;
                document.getElementById('stopBtn').disabled = false;
                document.getElementById('enterBtn').disabled = false;
            } else {
                statusDot.classList.remove('active');
                statusText.textContent = 'Inactivo';
                taskText.textContent = 'Esperando...';
                document.getElementById('scraperBtn').disabled = false;
                document.getElementById('scrollBtn').disabled = true;
                document.getElementById('stopBtn').disabled = true;
                document.getElementById('enterBtn').disabled = true;
            }

            if (data.auto_scroll !== this.autoScrollActive) {
                this.autoScrollActive = data.auto_scroll;
                this.updateScrollButton();
            }

            if (data.auto_scroll) {
                scrollStatus.style.display = 'flex';
            } else {
                scrollStatus.style.display = 'none';
            }

        } catch (error) {
            console.error('Error al actualizar estado:', error);
        }
    },

    updateScrollButton() {
        const btn = document.getElementById('scrollBtn');
        if (this.autoScrollActive) {
            btn.textContent = '⏸️ Pausar Scroll';
        } else {
            btn.textContent = '🤖 Scroll Auto';
        }
    },

    async openChrome() {
        try {
            const response = await fetch('/scraper/open-chrome', { method: 'POST' });
            const data = await response.json();

            if (data.ok) {
                Utils.showToast('Chrome abierto correctamente', 'success');
            } else {
                Utils.showToast('Error: ' + data.msg, 'error');
            }
        } catch (error) {
            Utils.showToast('Error al abrir Chrome', 'error');
        }
    },

    async runScraper() {
        try {
            const response = await fetch('/scraper/run', { method: 'POST' });

            if (response.status === 409) {
                Utils.showToast('Ya hay un proceso corriendo', 'error');
                return;
            }

            Utils.showToast('Scraper iniciado', 'success');
        } catch (error) {
            Utils.showToast('Error al iniciar scraper', 'error');
        }
    },

    async runExcel() {
        try {
            const response = await fetch('/scraper/excel', { method: 'POST' });

            if (response.status === 409) {
                Utils.showToast('Ya hay un proceso corriendo', 'error');
                return;
            }

            Utils.showToast('Generando Excel...', 'info');
        } catch (error) {
            Utils.showToast('Error al generar Excel', 'error');
        }
    },

    async sendEnter() {
        try {
            const response = await fetch('/scraper/enter', { method: 'POST' });
            const data = await response.json();

            if (data.ok) {
                Utils.showToast('Enter enviado', 'success');
            } else {
                Utils.showToast('Error: ' + data.msg, 'error');
            }
        } catch (error) {
            Utils.showToast('Error al enviar Enter', 'error');
        }
    },

    async toggleScroll() {
        try {
            const response = await fetch('/scraper/toggle-scroll', { method: 'POST' });
            const data = await response.json();

            if (data.ok) {
                const status = data.active ? 'activado' : 'pausado';
                Utils.showToast(`Scroll automático ${status}`, 'success');
            } else {
                Utils.showToast('Error: ' + data.msg, 'error');
            }
        } catch (error) {
            Utils.showToast('Error al cambiar scroll', 'error');
        }
    },

    async stop() {
        try {
            const response = await fetch('/scraper/stop', { method: 'POST' });
            const data = await response.json();

            if (data.ok) {
                Utils.showToast('Proceso detenido', 'success');
            } else {
                Utils.showToast('Error: ' + data.msg, 'error');
            }
        } catch (error) {
            Utils.showToast('Error al detener proceso', 'error');
        }
    },

    clearLog() {
        document.getElementById('scraperLog').textContent = '';
    }
};

// ============================================================================
// MÓDULO: DICCIONARIO
// ============================================================================

const DiccionarioModule = {
    currentPage: 1,
    perPage: 50,
    searchTimeout: null,

    init() {
        this.loadStats();
        this.loadTraducciones();
        this.setupEventListeners();
    },

    setupEventListeners() {
        const searchInput = document.getElementById('searchInput');
        const filterSelect = document.getElementById('filterSelect');

        searchInput.addEventListener('input', (e) => {
            clearTimeout(this.searchTimeout);
            this.searchTimeout = setTimeout(() => {
                this.currentPage = 1;
                this.loadTraducciones();
            }, 500);
        });

        filterSelect.addEventListener('change', () => {
            this.currentPage = 1;
            this.loadTraducciones();
        });

        // Autocompletar producto
        const inputProducto = document.getElementById('inputProducto');
        inputProducto.addEventListener('input', (e) => {
            this.searchProductos(e.target.value);
        });

        // Sugerencias automáticas cuando cambia el nombre Panacea
        const inputNombrePanacea = document.getElementById('inputNombrePanacea');
        inputNombrePanacea.addEventListener('input', (e) => {
            clearTimeout(this.searchTimeout);
            this.searchTimeout = setTimeout(() => {
                this.loadSugerencias(e.target.value);
            }, 500);
        });
    },

    async loadStats() {
        try {
            const response = await fetch('/diccionario/stats');
            const result = await response.json();

            if (result.ok) {
                const stats = result.data;
                const statsGrid = document.getElementById('statsGrid');

                statsGrid.innerHTML = `
                    <div class="stat-card">
                        <div class="stat-value">${stats.total_productos}</div>
                        <div class="stat-label">Total Productos</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.productos_traducidos}</div>
                        <div class="stat-label">Con Traducción</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.productos_sin_traducir}</div>
                        <div class="stat-label">Sin Traducir</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.total_traducciones}</div>
                        <div class="stat-label">Total Traducciones</div>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error al cargar estadísticas:', error);
        }
    },

    async loadTraducciones() {
        const search = document.getElementById('searchInput').value;
        const filtro = document.getElementById('filterSelect').value;

        try {
            const url = `/diccionario/list?page=${this.currentPage}&per_page=${this.perPage}&filtro=${filtro}&search=${encodeURIComponent(search)}`;
            const response = await fetch(url);
            const result = await response.json();

            if (result.ok) {
                this.renderTable(result.data.items);
                this.renderPagination(result.data);
            }
        } catch (error) {
            console.error('Error al cargar traducciones:', error);
            Utils.showToast('Error al cargar datos', 'error');
        }
    },

    renderTable(items) {
        const tbody = document.getElementById('diccionarioBody');

        if (!items || items.length === 0) {
            // Nota el colspan="6" porque ahora hay una columna más
            tbody.innerHTML = '<tr><td colspan="6" class="loading">No se encontraron resultados</td></tr>';
            return;
        }

        tbody.innerHTML = items.map(item => {
            const confianza = Number(item.confianza || 0);
            
            return `
            <tr>
                <td class="text-muted"><small>${item.external_id || '-'}</small></td>
                <td><strong>${item.nombre_panacea || 'Sin nombre'}</strong></td>
                <td>${item.nombre_producto || 'Desconocido'}</td>
                <td>
                    <span class="badge ${Utils.getConfianzaBadge(confianza)}">
                        ${confianza.toFixed(1)}%
                    </span>
                </td>
                <td>${Utils.formatDate(item.created_at)}</td>
                <td>
                    <div class="action-btns">
                        <button class="btn-icon" onclick="DiccionarioModule.editTraduccion('${item.id}')" title="Editar">
                            ✏️
                        </button>
                        <button class="btn-icon" onclick="DiccionarioModule.deleteTraduccion('${item.id}')" title="Eliminar">
                            🗑️
                        </button>
                    </div>
                </td>
            </tr>
        `}).join('');
    },

    renderPagination(data) {
        const pagination = document.getElementById('pagination');
        const totalPages = data.total_pages;

        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }

        let html = '';

        // Anterior
        if (this.currentPage > 1) {
            html += `<button class="page-btn" onclick="DiccionarioModule.goToPage(${this.currentPage - 1})">‹</button>`;
        }

        // Páginas
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= this.currentPage - 2 && i <= this.currentPage + 2)) {
                const active = i === this.currentPage ? 'active' : '';
                html += `<button class="page-btn ${active}" onclick="DiccionarioModule.goToPage(${i})">${i}</button>`;
            } else if (i === this.currentPage - 3 || i === this.currentPage + 3) {
                html += `<span>...</span>`;
            }
        }

        // Siguiente
        if (this.currentPage < totalPages) {
            html += `<button class="page-btn" onclick="DiccionarioModule.goToPage(${this.currentPage + 1})">›</button>`;
        }

        pagination.innerHTML = html;
    },

    goToPage(page) {
        this.currentPage = page;
        this.loadTraducciones();
    },

    // CRUD Operations
    showAddModal() {
        document.getElementById('modalAdd').classList.add('show');
        document.getElementById('inputNombrePanacea').value = '';
        document.getElementById('inputProducto').value = '';
        document.getElementById('inputProductoId').value = '';
        document.getElementById('inputConfianza').value = '100';
        document.getElementById('sugerenciasAuto').innerHTML = '';
    },

    closeModals() {
        document.querySelectorAll('.modal').forEach(modal => {
            modal.classList.remove('show');
        });
    },

    async saveTraduccion() {
        const nombrePanacea = document.getElementById('inputNombrePanacea').value.trim();
        const productoId = document.getElementById('inputProductoId').value;
        const confianza = document.getElementById('inputConfianza').value;

        if (!nombrePanacea || !productoId) {
            Utils.showToast('Complete todos los campos', 'error');
            return;
        }

        try {
            const response = await fetch('/diccionario/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    nombre_panacea: nombrePanacea,
                    producto_id: productoId,
                    confianza: parseFloat(confianza)
                })
            });

            const result = await response.json();

            if (result.ok) {
                Utils.showToast(`Traducción ${result.data.accion}`, 'success');
                this.closeModals();
                this.loadTraducciones();
                this.loadStats();
            } else {
                Utils.showToast('Error: ' + result.msg, 'error');
            }
        } catch (error) {
            Utils.showToast('Error al guardar traducción', 'error');
        }
    },

    async deleteTraduccion(id) {
        if (!confirm('¿Estás seguro de eliminar esta traducción?')) {
            return;
        }

        try {
            const response = await fetch(`/diccionario/delete/${id}`, {
                method: 'DELETE'
            });

            const result = await response.json();

            if (result.ok) {
                Utils.showToast('Traducción eliminada', 'success');
                this.loadTraducciones();
                this.loadStats();
            } else {
                Utils.showToast('Error: ' + result.msg, 'error');
            }
        } catch (error) {
            Utils.showToast('Error al eliminar traducción', 'error');
        }
    },

    async searchProductos(query) {
        if (query.length < 2) {
            document.getElementById('sugerenciasProducto').innerHTML = '';
            document.getElementById('sugerenciasProducto').classList.remove('show');
            return;
        }

        try {
            const response = await fetch(`/diccionario/productos-db?search=${encodeURIComponent(query)}&limit=10`);
            const result = await response.json();

            if (result.ok) {
                const sugerencias = document.getElementById('sugerenciasProducto');
                sugerencias.innerHTML = result.data.map(p => `
                    <div class="sugerencia-item" onclick="DiccionarioModule.selectProducto('${p.id}', '${p.nombre.replace(/'/g, "\\'")}')">
                        ${p.nombre}
                    </div>
                `).join('');
                sugerencias.classList.add('show');
            }
        } catch (error) {
            console.error('Error al buscar productos:', error);
        }
    },

    selectProducto(id, nombre) {
        document.getElementById('inputProducto').value = nombre;
        document.getElementById('inputProductoId').value = id;
        document.getElementById('sugerenciasProducto').classList.remove('show');
    },

    async loadSugerencias(nombrePanacea) {
        if (nombrePanacea.length < 3) {
            document.getElementById('sugerenciasAuto').innerHTML = '';
            return;
        }

        try {
            const response = await fetch(`/diccionario/sugerencias/${encodeURIComponent(nombrePanacea)}`);
            const result = await response.json();

            if (result.ok && result.data.length > 0) {
                const container = document.getElementById('sugerenciasAuto');
                container.innerHTML = `
                    <h4>💡 Sugerencias Automáticas</h4>
                    ${result.data.map(s => `
                        <div class="sugerencia-auto-item" 
                             onclick="DiccionarioModule.selectProducto('${s.producto_id}', '${s.nombre.replace(/'/g, "\\'")}'); DiccionarioModule.setConfianza(${s.confianza})">
                            <strong>${s.nombre}</strong>
                            <span class="badge ${Utils.getConfianzaBadge(s.confianza)}">${s.confianza.toFixed(1)}%</span>
                        </div>
                    `).join('')}
                `;
            }
        } catch (error) {
            console.error('Error al cargar sugerencias:', error);
        }
    },

    setConfianza(confianza) {
        document.getElementById('inputConfianza').value = confianza.toFixed(1);
    },

    // Auto-matching
    autoMatch() {
        document.getElementById('modalAutoMatch').classList.add('show');
    },

    async executeAutoMatch() {
        const umbral = parseFloat(document.getElementById('inputUmbral').value);
        const limite = parseInt(document.getElementById('inputLimite').value);

        if (umbral < 60 || umbral > 100) {
            Utils.showToast('El umbral debe estar entre 60 y 100', 'error');
            return;
        }

        this.closeModals();
        Utils.showToast('Ejecutando matching automático...', 'info');

        try {
            const response = await fetch('/diccionario/auto-match', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ umbral, limite })
            });

            const result = await response.json();

            if (result.ok) {
                const data = result.data;
                Utils.showToast(
                    `Matching completado: ${data.insertados} insertados, ${data.rechazados} rechazados`,
                    'success'
                );
                this.loadTraducciones();
                this.loadStats();
            } else {
                Utils.showToast('Error: ' + result.msg, 'error');
            }
        } catch (error) {
            Utils.showToast('Error al ejecutar matching', 'error');
        }
    },

    // Importar/Exportar
    exportar() {
        window.location.href = '/diccionario/export';
        Utils.showToast('Exportando diccionario...', 'info');
    },

    showImportModal() {
        document.getElementById('modalImport').classList.add('show');
    },

    async executeImport() {
        const fileInput = document.getElementById('inputFile');
        const file = fileInput.files[0];

        if (!file) {
            Utils.showToast('Selecciona un archivo', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        this.closeModals();
        Utils.showToast('Importando archivo...', 'info');

        try {
            const response = await fetch('/diccionario/import', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.ok) {
                const data = result.data;
                Utils.showToast(
                    `Importación completada: ${data.insertados} insertados, ${data.existentes} ya existían`,
                    'success'
                );
                this.loadTraducciones();
                this.loadStats();
            } else {
                Utils.showToast('Error: ' + result.msg, 'error');
            }
        } catch (error) {
            Utils.showToast('Error al importar archivo', 'error');
        }
    }
};