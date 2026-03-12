import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client

# =========================================================
# 1. CONEXIÓN Y CONFIGURACIÓN (NUBE)
# =========================================================

def conectar():
    """Establece conexión con la base de datos de Supabase."""
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

def inicializar_bd():
    """Mantenida por compatibilidad con app_principal.py"""
    pass

# =========================================================
# 2. GESTIÓN DE USUARIOS
# =========================================================

def validar_usuario(usuario, clave):
    supabase = conectar()
    res = supabase.table("usuarios").select("*").eq("nombre_usuario", usuario).eq("contrasena", clave).execute()
    return res.data[0] if res.data else None

def obtener_supervisores():
    supabase = conectar()
    res = supabase.table("usuarios").select("id, nombre_real, rol").in_("rol", ['Administrador', 'Gerente', 'Supervisor']).execute()
    return pd.DataFrame(res.data)

# =========================================================
# 3. GESTIÓN DE PROYECTOS
# =========================================================

def obtener_proyectos(busqueda="", supervisor_id=None):
    supabase = conectar()
    query = supabase.table("proyectos").select("*")
    
    if supervisor_id:
        query = query.eq("supervisor_id", supervisor_id)
    
    res = query.execute()
    df = pd.DataFrame(res.data)
    
    if not df.empty and busqueda:
        busqueda = busqueda.lower()
        df = df[df['proyecto_text'].str.lower().str.contains(busqueda) | 
                df['cliente'].str.lower().str.contains(busqueda) | 
                df['estatus'].str.lower().str.contains(busqueda)]
    return df

def actualizar_proyecto(id_p, campos):
    supabase = conectar()
    supabase.table("proyectos").update(campos).eq("id", id_p).execute()

def eliminar_proyecto(id_p):
    supabase = conectar()
    supabase.table("proyectos").delete().eq("id", id_p).execute()

# =========================================================
# 4. GESTIÓN DE PRODUCTOS E INVENTARIO
# =========================================================

def agregar_producto_manual(id_p, u, t, c, m):
    supabase = conectar()
    supabase.table("productos").insert({
        "proyecto_id": id_p, "ubicacion": u, "tipo": t, "ctd": c, "ml": m
    }).execute()

def actualizar_producto(id_prod, u, t, c, m):
    supabase = conectar()
    supabase.table("productos").update({
        "ubicacion": u, "tipo": t, "ctd": c, "ml": m
    }).eq("id", id_prod).execute()

def eliminar_producto(id_prod):
    supabase = conectar()
    supabase.table("productos").delete().eq("id", id_prod).execute()

def obtener_resumen_inventario(id_proyecto):
    supabase = conectar()
    res = supabase.table("productos").select("ctd, ml").eq("proyecto_id", id_proyecto).execute()
    df = pd.DataFrame(res.data)
    if df.empty: return (0, 0)
    return (df['ctd'].sum(), df['ml'].sum())

def obtener_datos_reporte(id_proyecto):
    supabase = conectar()
    res = supabase.table("productos").select("ubicacion, tipo, ctd, ml").eq("proyecto_id", id_proyecto).execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        df.columns = ['Ubicación', 'Tipo', 'Cantidad', 'Metros Lineales']
    return df

def borrar_productos_proyecto(proyecto_id):
    supabase = conectar()
    supabase.table("productos").delete().eq("proyecto_id", proyecto_id).execute()
    supabase.table("proyectos").update({"avance": 0}).eq("id", proyecto_id).execute()

# =========================================================
# 5. SEGUIMIENTO, AVANCE Y GANTT (LÓGICA PRESERVADA)
# =========================================================

def actualizar_avance_real(id_p):
    supabase = conectar()
    # Contar productos
    prods = supabase.table("productos").select("id").eq("proyecto_id", id_p).execute()
    total_prod = len(prods.data)
    if total_prod == 0: return

    # Contar hitos marcados
    ids_prod = [p['id'] for p in prods.data]
    segs = supabase.table("seguimiento").select("id").in_("producto_id", ids_prod).execute()
    
    checks = len(segs.data)
    nuevo_avance = (checks / (total_prod * 8)) * 100
    supabase.table("proyectos").update({"avance": nuevo_avance}).eq("id", id_p).execute()

def obtener_gantt_real_data(id_p):
    supabase = conectar()
    mapeo = {
        "Diseño": ["Diseñado"], 
        "Fabricación": ["Fabricado"], 
        "Traslado": ["Material en Obra", "Material en Ubicación"], 
        "Instalación": ["Instalación de Estructura", "Instalación de Puertas o Frentes", "Revisión y Observaciones"], 
        "Entrega": ["Entrega"]
    }
    
    # Obtener todos los seguimientos del proyecto
    prods = supabase.table("productos").select("id").eq("proyecto_id", id_p).execute()
    ids_prod = [p['id'] for p in prods.data]
    segs_res = supabase.table("seguimiento").select("hito, fecha").in_("producto_id", ids_prod).execute()
    df_segs = pd.DataFrame(segs_res.data)
    
    reales = []
    if not df_segs.empty:
        for etapa, hitos in mapeo.items():
            mask = df_segs['hito'].isin(hitos)
            fechas_etapa = df_segs[mask]['fecha']
            if not fechas_etapa.empty:
                reales.append({"Etapa": etapa, "Inicio": fechas_etapa.min(), "Fin": fechas_etapa.max()})
    
    return pd.DataFrame(reales)

# =========================================================
# 6. GESTIÓN DE INCIDENCIAS Y PIEZAS
# =========================================================

def registrar_incidencia_detallada(proy_id, tipo_inc, motivo, piezas, materiales, user_id):
    supabase = conectar()
    # Insertar cabecera
    inc_res = supabase.table("incidencias").insert({
        "proyecto_id": proy_id, "tipo_requerimiento": tipo_inc, 
        "categoria": motivo, "fecha_reporte": date.today().isoformat(), "usuario_id": user_id
    }).execute()
    
    inc_id = inc_res.data[0]['id']
    
    if piezas:
        for p in piezas:
            p['incidencia_id'] = inc_id
            supabase.table("detalles_piezas").insert(p).execute()
    
    if materiales:
        for m in materiales:
            m['incidencia_id'] = inc_id
            supabase.table("detalles_materiales").insert(m).execute()

def obtener_incidencias_resumen():
    supabase = conectar()
    # En Supabase las uniones (JOIN) se hacen mediante relaciones de tablas
    res = supabase.table("incidencias").select("*, proyectos(proyecto_text), usuarios(nombre_real)").order("id", desc=True).execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        # Aplanar el JSON de respuesta para mantener compatibilidad con tu código actual
        df['proyecto_text'] = df['proyectos'].apply(lambda x: x['proyecto_text'] if x else "")
        df['nombre_real'] = df['usuarios'].apply(lambda x: x['nombre_real'] if x else "")
    return df

def actualizar_estado_incidencia(inc_id, nuevo_estado):
    supabase = conectar()
    supabase.table("incidencias").update({"estado": nuevo_estado}).eq("id", inc_id).execute()
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

