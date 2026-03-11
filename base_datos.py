import sqlite3
import pandas as pd
from datetime import datetime, date

def conectar():
    # Eliminamos cualquier rastro de caché con isolation_level=None
    conn = sqlite3.connect('carpinteria_v2.db', timeout=30, isolation_level=None)
    conn.execute('PRAGMA foreign_keys = ON')
    # Modo WAL permite que Streamlit lea mientras la base de datos escribe
    conn.execute('PRAGMA journal_mode = WAL') 
    return conn

def inicializar_bd():
    with conectar() as conn:
        cursor = conn.cursor()
        
        # 1. Tabla: Usuarios (Roles: Administrador, Gerente, Supervisor)
        cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_usuario TEXT UNIQUE NOT NULL,
            contrasena TEXT NOT NULL,
            rol TEXT NOT NULL,
            nombre_real TEXT)''')

        # 2. Tabla: Proyectos (17 columnas contractuales + supervisor)
        cursor.execute('''CREATE TABLE IF NOT EXISTS proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, proyecto_text TEXT, partida TEXT,
            f_ini TEXT, f_fin TEXT, estatus TEXT DEFAULT 'Activo', avance REAL DEFAULT 0.0,
            p_dis_i TEXT, p_dis_f TEXT, p_fab_i TEXT, p_fab_f TEXT, 
            p_tra_i TEXT, p_tra_f TEXT, p_ins_i TEXT, p_ins_f TEXT, p_ent_i TEXT, p_ent_f TEXT,
            supervisor_id INTEGER,
            UNIQUE(cliente, proyecto_text),
            FOREIGN KEY (supervisor_id) REFERENCES usuarios (id))''')
        
        # 3. Tabla: Productos
        cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, proyecto_id INTEGER,
            ubicacion TEXT, tipo TEXT, ctd INTEGER, ml REAL,
            FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE)''')

        # 4. Tabla: Seguimiento (Hitos técnicos)
        cursor.execute('''CREATE TABLE IF NOT EXISTS seguimiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER, hito TEXT, fecha TEXT,
            FOREIGN KEY (producto_id) REFERENCES productos (id) ON DELETE CASCADE,
            UNIQUE(producto_id, hito))''')

        # 5. Tabla: Registro de Cierres (El candado) ---
        # Esta tabla anotará qué proyecto y qué fecha ya no se pueden tocar
        cursor.execute('''CREATE TABLE IF NOT EXISTS cierres_diarios (
            proyecto_id INTEGER,
            fecha TEXT,
            cerrado_por INTEGER,
            PRIMARY KEY (proyecto_id, fecha),
            FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE)''')

        # Admin por defecto (Seguridad inicial)
        try:
            cursor.execute("INSERT INTO usuarios (nombre_usuario, contrasena, rol, nombre_real) VALUES (?,?,?,?)",
                         ('admin', 'admin123', 'Administrador', 'Karen Paola'))
        except: pass
        
        # Parche para asegurar columna supervisor en bases de datos existentes
        try:
            cursor.execute("ALTER TABLE proyectos ADD COLUMN supervisor_id INTEGER")
        except: pass
        
        # --- AGREGAR ESTO DENTRO DE inicializar_bd() ---
        
        # 1. Asegurar columna observaciones en seguimiento
        try:
            cursor.execute("ALTER TABLE seguimiento ADD COLUMN observaciones TEXT")
        except sqlite3.OperationalError:
            pass 

        # 2. Nueva Tabla: Incidencias (Cabecera del requerimiento)
        cursor.execute('''CREATE TABLE IF NOT EXISTS incidencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto_id INTEGER,
            tipo_requerimiento TEXT, 
            fecha_reporte TEXT,
            usuario_id INTEGER,
            estado TEXT DEFAULT 'Pendiente', 
            FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE)''')

        # 3. Nueva Tabla: Detalles técnicos de piezas (Atributos de producción)
        cursor.execute('''CREATE TABLE IF NOT EXISTS detalles_piezas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incidencia_id INTEGER,
            descripcion TEXT, veta TEXT, no_veta TEXT, cantidad INTEGER,
            ubicacion TEXT, material TEXT, tc_frontal TEXT, tc_posterior TEXT,
            tc_derecho TEXT, tc_izquierdo TEXT, rotacion TEXT, observaciones TEXT,
            FOREIGN KEY (incidencia_id) REFERENCES incidencias (id) ON DELETE CASCADE)''')

        # 4. Nueva Tabla: Detalles de materiales (Cerrajería, accesorios, etc.)
        cursor.execute('''CREATE TABLE IF NOT EXISTS detalles_materiales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incidencia_id INTEGER,
            descripcion TEXT, cantidad INTEGER, observaciones TEXT,
            FOREIGN KEY (incidencia_id) REFERENCES incidencias (id) ON DELETE CASCADE)''')
        
        conn.commit()

# --- GESTIÓN DE PROYECTOS ---

def obtener_proyectos(busqueda="", supervisor_id=None):
    with conectar() as conn:
        query = "SELECT * FROM proyectos WHERE 1=1"
        params = []
        if supervisor_id is not None:
            query += " AND supervisor_id = ?"
            params.append(supervisor_id)
        if busqueda:
            query += " AND (proyecto_text LIKE ? OR cliente LIKE ? OR estatus LIKE ?)"
            term = f"%{busqueda}%"
            params.extend([term, term, term])
        return pd.read_sql_query(query, conn, params=params)

def actualizar_proyecto(id_p, campos):
    with conectar() as conn:
        cols = ", ".join([f"{k}=?" for k in campos.keys()])
        conn.execute(f"UPDATE proyectos SET {cols} WHERE id=?", (*campos.values(), id_p))
        conn.commit()

def eliminar_proyecto(id_p):
    with conectar() as conn:
        # ON DELETE CASCADE se encarga de productos y seguimientos
        conn.execute("DELETE FROM proyectos WHERE id=?", (id_p,))
        conn.commit()

# --- GESTIÓN DE PRODUCTOS ---

def agregar_producto_manual(id_p, u, t, c, m):
    with conectar() as conn:
        conn.execute("INSERT INTO productos (proyecto_id, ubicacion, tipo, ctd, ml) VALUES (?,?,?,?,?)", 
                     (id_p, u, t, c, m))
        conn.commit()

def actualizar_producto(id_prod, u, t, c, m):
    with conectar() as conn:
        conn.execute("UPDATE productos SET ubicacion=?, tipo=?, ctd=?, ml=? WHERE id=?", 
                     (u, t, c, m, id_prod))
        conn.commit()

def eliminar_producto(id_prod):
    with conectar() as conn:
        conn.execute("DELETE FROM productos WHERE id=?", (id_prod,))
        conn.commit()

# --- GESTIÓN DE SEGUIMIENTO Y AVANCE ---

def actualizar_avance_real(id_p):
    with conectar() as conn:
        conn.commit()
        total_prod = conn.execute("SELECT COUNT(*) FROM productos WHERE proyecto_id=?", (id_p,)).fetchone()[0]
        if total_prod == 0: return
        query_checks = """
            SELECT COUNT(s.id) FROM seguimiento s
            JOIN productos p ON s.producto_id = p.id
            WHERE p.proyecto_id = ?
        """
        checks = conn.execute(query_checks, (id_p,)).fetchone()[0]
        nuevo_avance = (checks / (total_prod * 8)) * 100
        conn.execute("UPDATE proyectos SET avance=? WHERE id=?", (nuevo_avance, id_p))
        conn.commit()

def obtener_gantt_real_data(id_p):
    mapeo = {"Diseño": ["Diseñado"], "Fabricación": ["Fabricado"], "Traslado": ["Material en Obra", "Material en Ubicación"], 
              "Instalación": ["Instalación de Estructura", "Instalación de Puertas o Frentes", "Revisión y Observaciones"], "Entrega": ["Entrega"]}
    reales = []
    with conectar() as conn:
        for etapa, hitos in mapeo.items():
            h_list = ','.join(['?']*len(hitos))
            query = f"SELECT MIN(s.fecha), MAX(s.fecha) FROM seguimiento s JOIN productos p ON s.producto_id = p.id WHERE s.hito IN ({h_list}) AND p.proyecto_id = ?"
            res = conn.execute(query, (*hitos, id_p)).fetchone()
            if res and res[0]:
                reales.append({"Etapa": etapa, "Inicio": res[0], "Fin": res[1]})
    return pd.DataFrame(reales)

# --- GESTIÓN DE USUARIOS ---

def obtener_supervisores():
    with conectar() as conn:
        # Ahora incluimos a Administradores y Gerentes en la lista de posibles responsables
        query = """
            SELECT id, nombre_real, rol 
            FROM usuarios 
            WHERE rol IN ('Administrador', 'Gerente', 'Supervisor')
        """
        return pd.read_sql_query(query, conn)
    
def obtener_resumen_inventario(id_proyecto):
    """Calcula la sumatoria de cantidades y metros lineales de un proyecto."""
    with conectar() as conn:
        query = "SELECT SUM(ctd), SUM(ml) FROM productos WHERE proyecto_id = ?"
        res = conn.execute(query, (id_proyecto,)).fetchone()
        # Retornamos (0, 0) si no hay productos aún
        return (res[0] or 0, res[1] or 0)
    
def obtener_datos_reporte(id_proyecto):
    """Extrae el inventario detallado para exportación."""
    with conectar() as conn:
        query = """
            SELECT ubicacion AS Ubicación, tipo AS Tipo, ctd AS Cantidad, ml AS 'Metros Lineales'
            FROM productos WHERE proyecto_id = ?
        """
        return pd.read_sql_query(query, conn, params=(id_proyecto,))
    
# =========================================================
# SECCIÓN: GESTIÓN DE INCIDENCIAS (VERSION ACTUALIZADA)
# =========================================================

def registrar_incidencia_detallada(proy_id, tipo_inc, motivo, piezas, materiales, user_id):
    """Guarda requerimientos separando piezas de materiales con su motivo."""
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO incidencias (proyecto_id, tipo_requerimiento, categoria, fecha_reporte, usuario_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (proy_id, tipo_inc, motivo, date.today().isoformat(), user_id))
        
        inc_id = cursor.lastrowid
        
        if piezas:
            for p in piezas:
                cursor.execute('''
                    INSERT INTO detalles_piezas (
                        incidencia_id, descripcion, veta, no_veta, cantidad, ubicacion, 
                        material, tc_frontal, tc_posterior, tc_derecho, tc_izquierdo, 
                        rotacion, observaciones
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (inc_id, p['descripcion'], p['veta'], p['no_veta'], p['cantidad'], 
                      p['ubicacion'], p['material'], p['tc_frontal'], p['tc_posterior'], 
                      p['tc_derecho'], p['tc_izquierdo'], p['rotacion'], p['observaciones']))
        
        if materiales:
            for m in materiales:
                cursor.execute('''
                    INSERT INTO detalles_materiales (incidencia_id, descripcion, cantidad, observaciones)
                    VALUES (?,?,?,?)
                ''', (inc_id, m['descripcion'], m['cantidad'], m['observaciones']))
        conn.commit()

def obtener_incidencias_resumen():
    query = "SELECT i.*, p.proyecto_text, u.nombre_real FROM incidencias i JOIN proyectos p ON i.proyecto_id = p.id JOIN usuarios u ON i.usuario_id = u.id ORDER BY i.id DESC"
    with conectar() as conn:
        return pd.read_sql_query(query, conn)

def actualizar_estado_incidencia(inc_id, nuevo_estado):
    """Cambia el estatus de la incidencia (Pendiente, Enviado, Atendido)."""
    with conectar() as conn:
        conn.execute("UPDATE incidencias SET estado=? WHERE id=?", (nuevo_estado, inc_id))
        conn.commit()

# --- NUEVA FUNCIÓN PARA LIMPIEZA DE PROYECTOS ---

def borrar_productos_proyecto(proyecto_id):
    """Elimina todos los productos de un proyecto para permitir re-importación."""
    with conectar() as conn:
        # Al borrar productos, la tabla 'seguimiento' se limpia sola por el ON DELETE CASCADE
        conn.execute("DELETE FROM productos WHERE proyecto_id = ?", (proyecto_id,))
        # Importante: Reiniciar el avance del proyecto
        conn.execute("UPDATE proyectos SET avance = 0 WHERE id = ?", (proyecto_id,))
        conn.commit()