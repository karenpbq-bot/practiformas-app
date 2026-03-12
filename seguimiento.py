import streamlit as st
import pandas as pd
from datetime import date
from base_datos import obtener_proyectos, conectar, actualizar_avance_real

# 1. DICCIONARIO MAESTRO DE ICONOS (FUNCIONALIDAD PRESERVADA)
MAPEO_HITOS = {
    "Diseñado": "🗺️", 
    "Fabricado": "🪚",
    "Material en Obra": "🚛",
    "Material en Ubicación": "📍",
    "Instalación de Estructura": "📦", 
    "Instalación de Puertas o Frentes": "🗄️",
    "Revisión y Observaciones": "🔍",
    "Entrega": "🤝"
}

# 2. LEYENDA TÉCNICA (FUNCIONALIDAD PRESERVADA)
LEYENDA_DETALLADA = {
    "🗺️": "Diseño (Plano Técnico)",
    "🪚": "Fabricación (Taller)",
    "🚛": "En Obra (Descargado)",
    "📍": "En Ubicación (Frente de trabajo)",
    "📦": "Estructura (Cajón base)",
    "🗄️": "Frentes (Mueble cerrado)",
    "🔍": "Revisión y atención de Observaciones (Post-instalación)",
    "🤝": "Entrega (Conformidad Cliente)"
}

def obtener_fecha_formateada():
    """Retorna la fecha actual en formato texto DD/MM/YYYY."""
    return date.today().strftime("%d/%m/%Y")

def obtener_fecha_formateada():
    """Retorna la fecha actual en formato ISO para compatibilidad con SQL y Gantt."""
    return date.today().strftime("%Y-%m-%d")

def registrar_hitos_cascada(conn, p_id, hito_final, fecha_str):
    """Marca el hito actual y anteriores sin sobreescribir fechas previas."""
    hitos_orden = list(MAPEO_HITOS.keys())
    try:
        idx_limite = hitos_orden.index(hito_final)
        hitos_a_marcar = hitos_orden[:idx_limite + 1]
        
        for h in hitos_a_marcar:
            # INSERT OR IGNORE: Si el hito ya existe, no hace nada (preserva fecha original)
            # Si no existe, lo crea con la fecha del movimiento actual
            conn.execute(
                "INSERT OR IGNORE INTO seguimiento (producto_id, hito, fecha) VALUES (?,?,?)",
                (p_id, h, fecha_str)
            )
        conn.commit() 
    except Exception as e:
        st.error(f"Error en cascada: {e}")

def obtener_fecha_formateada():
    """Retorna la fecha actual en formato texto DD/MM/YYYY."""
    return date.today().strftime("%d/%m/%Y")

def mostrar(supervisor_id=None):
    # Estilos CSS para el encabezado fijo (Sticky) y área de scroll
    st.markdown("""
        <style>
        .header-fixed { position: sticky; top: 0; background: white; z-index: 1000; border-bottom: 2px solid #FF8C00; padding: 10px 0; font-weight: bold; }
        .scroll-area { max-height: 500px; overflow-y: auto; overflow-x: hidden; border: 1px solid #eee; padding: 10px; border-radius: 5px; }
        </style>
    """, unsafe_allow_html=True)
    
    st.header("📈 Panel de Seguimiento Matricial")

    # --- SECCIÓN 1: CABECERA FILA ÚNICA ---
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        bus_p = c1.text_input("🔍 Buscar proyecto o cliente...", key="bus_seg_proy")
        
        # Filtrado lógico
        df_p = obtener_proyectos(bus_p, supervisor_id=supervisor_id)
        
        # Switch "Ver sólo activos" solicitado
        solo_activos = c3.toggle("Ver sólo activos", value=True)
        if solo_activos:
            df_p = df_p[df_p['estatus'] == 'Activo']

        if df_p.empty:
            st.info("No se encontraron proyectos."); return

        opciones = {f"{r['proyecto_text']} — {r['cliente']}": r['id'] for _, r in df_p.iterrows()}
        sel_p_nom = c2.selectbox("Seleccione Proyecto:", ["Seleccione..."] + list(opciones.keys()))

    # --- VALIDACIÓN DE SEGURIDAD (Evita el KeyError) ---
    if sel_p_nom == "Seleccione...":
        st.info("💡 Por favor, selecciona un proyecto de la lista para ver el seguimiento.")
        return # Esto detiene la ejecución aquí hasta que se seleccione algo real

    # Ahora es seguro definir id_p porque ya sabemos que no es "Seleccione..."
    id_p = opciones[sel_p_nom]
    p_data = df_p[df_p['id'] == id_p].iloc[0]

    # --- SECCIÓN 2: DATOS DEL PROYECTO (FILA HORIZONTAL) ---
    if sel_p_nom == "Seleccione...": return
    id_p = opciones[sel_p_nom]
    p_data = df_p[df_p['id'] == id_p].iloc[0]

    with st.container(border=True):
        d1, d2, d3, d4, d5 = st.columns([2, 1.5, 1, 1, 1.5])
        d1.write(f"**Proy:** {p_data['proyecto_text']}")
        d2.write(f"**Cli:** {p_data['cliente']}")
        # Obtenemos productos para métricas
        with conectar() as conn:
            prods_base = pd.read_sql_query("SELECT * FROM productos WHERE proyecto_id=?", conn, params=(id_p,))
        d3.write(f"**Cant:** {int(prods_base['ctd'].sum())} Und")
        d4.write(f"**Avance:** {int(p_data['avance'])}%")
        fecha_avance = d5.date_input("📅 Fecha Registro", date.today())

    # --- SECCIÓN 3: FILTROS DE TRIPLE CAPA ---
    with st.expander("🛠️ Filtros de Producto (Agrupación y Búsqueda Doble)", expanded=False):
        f1, f2, f3, f4 = st.columns([1.2, 1.4, 1.4, 1])
        
        opciones_filtro = {"Sin grupo": None, "Ubicación": "ubicacion", "Tipo": "tipo"}
        label_agrupar = f1.selectbox("📂 Agrupar por:", list(opciones_filtro.keys()))
        columna_tecnica = opciones_filtro[label_agrupar]
        
        # Filtros de palabra clave (Doble capa)
        bus_capa1 = f2.text_input("🔍 Filtro Primario (Ej: B101):", placeholder="Zona...")
        bus_capa2 = f3.text_input("🔍 Refinar (Ej: bajo):", placeholder="Tipo...")
        
        solo_pendientes = f4.toggle("🔴 Solo pendientes", value=False)
        
        st.info("💡 **Guía:** " + " | ".join([f"{k} {v}" for k, v in LEYENDA_DETALLADA.items()]))

    # --- SECCIÓN 3: CABECERA DE CONTROL (MÉTRICAS) ---
    st.divider()
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.title(f"🚀 {p_data['proyecto_text']}")
        st.subheader(f"👤 Cliente: {p_data['cliente']}")
    with col_t2:
        st.metric("Avance Total", f"{int(p_data['avance'])}%")
        st.progress(p_data['avance']/100)

        # --- SECCIÓN 4: CARGA DE DATOS EN TIEMPO REAL ---
    HITOS_LIST = list(MAPEO_HITOS.keys())
        
        # Forzamos una conexión nueva cada vez que se entra a este bloque
    with conectar() as conn_viva:
            prods = pd.read_sql_query("SELECT * FROM productos WHERE proyecto_id=?", conn_viva, params=(id_p,))
            
            # RELECTURA CRÍTICA: Aquí es donde se "pintan" los checks
            query_viva = "SELECT s.* FROM seguimiento s JOIN productos p ON s.producto_id = p.id WHERE p.proyecto_id = ?"
            segs = pd.read_sql_query(query_viva, conn_viva, params=(id_p,))

        # Filtros de búsqueda (se aplican sobre los datos frescos)
   # --- PROCESAMIENTO DE FILTROS DE TRIPLE CAPA ---
    # 1. Aplicar Filtro Primario (Capa 1)
    if bus_capa1:
        prods = prods[prods['ubicacion'].astype(str).str.contains(bus_capa1, case=False, na=False) | 
                      prods['tipo'].astype(str).str.contains(bus_capa1, case=False, na=False)]
    
    # 2. Aplicar Refinamiento (Capa 2) sobre el resultado anterior
    if bus_capa2:
        prods = prods[prods['ubicacion'].astype(str).str.contains(bus_capa2, case=False, na=False) | 
                      prods['tipo'].astype(str).str.contains(bus_capa2, case=False, na=False)]

    if solo_pendientes:
            def esta_pendiente(p_id):
                num_checks = len(segs[segs['producto_id'] == p_id])
                return num_checks < len(HITOS_LIST)
            prods = prods[prods['id'].apply(esta_pendiente)]

    # --- LÓGICA DE SEGURIDAD Y PERMISOS ---
    with conectar() as conn:
            cierre = conn.execute(
                "SELECT 1 FROM cierres_diarios WHERE proyecto_id = ? AND fecha = ?",
                (id_p, fecha_avance.isoformat())
            ).fetchone()
        
    esta_guardado = cierre is not None
    user_rol = st.session_state.get('rol', 'Supervisor')
    es_jefe = user_rol in ['Administrador', 'Gerente']

    # Definimos quien puede editar
    bloqueo_edicion = esta_guardado and not es_jefe

   # =========================================================
    # SECCIÓN 5: PANEL DE CONTROL SUPERIOR (BOTONES Y EXCEL)
    # =========================================================
    st.divider()
    df_f = prods_base.copy()
    # Aplicar filtros de búsqueda previos
    if bus_capa1:
        df_f = df_f[df_f['ubicacion'].astype(str).str.contains(bus_capa1, case=False) | df_f['tipo'].astype(str).str.contains(bus_capa1, case=False)]
    if bus_capa2:
        df_f = df_f[df_f['ubicacion'].astype(str).str.contains(bus_capa2, case=False) | df_f['tipo'].astype(str).str.contains(bus_capa2, case=False)]
    if solo_pendientes:
        df_f = df_f[df_f['id'].apply(lambda x: len(segs[segs['producto_id'] == x]) < 8)]

    # FILA DE ACCIONES
    c_m1, c_m2, c_m3, c_m4 = st.columns([1.5, 1.2, 1.2, 1.5])
    
    with c_m1:
        st.write(f"### ⚡ Marcado ({len(df_f)})")
    
    with c_m2:
        # El botón ahora está siempre visible para permitir múltiples reportes al día
        if st.button("💾 Guardar Avance", use_container_width=True, type="primary"):
            with conectar() as conn:
                # Actualizamos avance real antes de confirmar
                actualizar_avance_real(id_p)
                # Opcional: Registrar quién hizo la última actualización
                user_id = st.session_state.get('id_usuario', 0)
                conn.execute("INSERT OR REPLACE INTO cierres_diarios (proyecto_id, fecha, cerrado_por) VALUES (?,?,?)",
                            (id_p, date.today().isoformat(), user_id))
            st.success("✅ Avance Guardado"); st.rerun()

        else:
            st.warning("🔐 Cerrado")

    with c_m3:
        # EXPORTAR AVANCE (Excel con Fechas DD/MM/YYYY)
        import io
        output = io.BytesIO()
        df_excel = df_f.copy()
        for h in HITOS_LIST:
            df_excel[h] = df_excel['id'].apply(lambda x: segs[(segs['producto_id'] == x) & (segs['hito'] == h)]['fecha'].max() if not segs[(segs['producto_id'] == x) & (segs['hito'] == h)].empty else "")
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_excel.to_excel(writer, index=False, sheet_name='Avance_Fechas')
        st.download_button("📥 Exportar Avance", data=output.getvalue(), file_name=f"Avance_{p_data['proyecto_text']}.xlsx", use_container_width=True)

    with c_m4: # IMPORTAR AVANCE (Sincronización Corregida)
        f_in = st.file_uploader("📤 Sincronizar Excel", type=["xlsx"], label_visibility="collapsed")
        if f_in:
            try:
                df_imp = pd.read_excel(f_in)
                f_hoy = obtener_fecha_formateada()
                actualizados = 0
                
                # En modo isolation_level=None no usamos BEGIN TRANSACTION manual
                with conectar() as conn:
                    for _, rx in df_imp.iterrows():
                        # Limpieza de datos
                        u_ex = str(rx.get('ubicacion', rx.get('Ubicación', ''))).strip()
                        t_ex = str(rx.get('tipo', rx.get('Tipo', ''))).strip()
                        try:
                            # Intentar obtener ML, si falla o es NaN ponemos 0.0
                            val_ml = rx.get('ml', rx.get('Metros Lineales', 0))
                            m_ex = float(val_ml) if pd.notnull(val_ml) else 0.0
                        except:
                            m_ex = 0.0
                        
                        # Buscamos el ID exacto del producto
                        res = conn.execute(
                            "SELECT id FROM productos WHERE proyecto_id=? AND ubicacion=? AND tipo=? AND ml=?", 
                            (id_p, u_ex, t_ex, m_ex)
                        ).fetchone()

                        if res:
                            p_id_imp = res[0]
                            for hito in MAPEO_HITOS.keys():
                                valor = str(rx.get(hito, '')).strip().upper()
                                # Si la celda en Excel tiene algo (X, OK, SI, etc)
                                if valor not in ["", "NO", "NAN", "NONE", "0"]:
                                    registrar_hitos_cascada(conn, p_id_imp, hito, f_hoy)
                                    actualizados += 1
                    
                    # Recalcular avance del proyecto al finalizar el bucle
                    actualizar_avance_real(id_p)
                
                st.success(f"✅ Sincronización finalizada. {actualizados} hitos procesados.")
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Error al procesar el Excel: {e}")

    # --- ENCABEZADO FIJO ---
    st.markdown("""<style>.h-fix { position: sticky; top: 0; background: white; z-index: 10; border-bottom: 2px solid #FF8C00; padding: 5px 0; font-weight: bold; }</style>""", unsafe_allow_html=True)
    st.markdown('<div class="h-fix">', unsafe_allow_html=True)
    cols_h = st.columns([3] + [0.7]*8 + [2])
    cols_h[0].write("B101 Producto ml")
    for i, hito in enumerate(HITOS_LIST):
        with cols_h[i+1]:
            if st.button("✅", key=f"bk_{hito}"):
                f_now = obtener_fecha_formateada()
                with conectar() as conn:
                    for p_id in df_f['id'].tolist(): registrar_hitos_cascada(conn, p_id, hito, f_now)
                actualizar_avance_real(id_p); st.rerun()
            st.write(MAPEO_HITOS[hito])
    cols_h[-1].write("Observaciones")
    st.markdown('</div>', unsafe_allow_html=True)

    # =========================================================
    # SECCIÓN 6: MATRIZ CRONOLÓGICA (RESULTADO FINAL)
    # =========================================================
    st.markdown('<div class="scroll-area">', unsafe_allow_html=True)
    for _, prod in df_f.iterrows():
        with st.container():
            cols = st.columns([3] + [0.7]*8 + [2])
            # REQ 5: Identificación en una sola línea
            cols[0].markdown(f"**{prod['ubicacion']}** {prod['tipo']} `{prod['ml']} ml`", unsafe_allow_html=True)
            
            for i, hito in enumerate(HITOS_LIST):
                key_c = f"c_{prod['id']}_{hito}"
                seg_match = segs[(segs['producto_id'] == prod['id']) & (segs['hito'] == hito)]
                en_db = not seg_match.empty
                fecha_hito = seg_match['fecha'].iloc[0] if en_db else ""

                # --- LÓGICA DE RESTRICCIÓN DE DESMARCADO ---
                tiene_posterior = False
                if i < len(HITOS_LIST) - 1:
                    hito_post = HITOS_LIST[i+1]
                    # Verificamos si la siguiente etapa está marcada en la base de datos
                    tiene_posterior = not segs[(segs['producto_id'] == prod['id']) & (segs['hito'] == hito_post)].empty

                rol_actual = st.session_state.get('rol', 'Supervisor')
                
                # Bloqueo: 1. Si es Supervisor y ya está marcado. 2. Si intentas desmarcar habiendo etapas posteriores.
                bloqueo_check = (en_db and rol_actual == "Supervisor") or (en_db and tiene_posterior)

                # Renderizado del Checkbox
                if cols[i+1].checkbox("Ok", key=key_c, value=en_db, label_visibility="collapsed", disabled=bloqueo_check, help=f"Fecha: {fecha_hito}"):
                    if not en_db:
                        f_now = obtener_fecha_formateada()
                        with conectar() as conn_f:
                            registrar_hitos_cascada(conn_f, prod['id'], hito, f_now)
                        actualizar_avance_real(id_p)
                        st.rerun()
                elif en_db and not tiene_posterior:
                    # Solo permite borrar si NO hay etapas posteriores marcadas
                    with conectar() as conn: 
                        conn.execute("DELETE FROM seguimiento WHERE producto_id=? AND hito=?", (prod['id'], hito))
                    actualizar_avance_real(id_p)
                    st.rerun()
            
            # Observaciones vinculadas a la DB
            obs_db = seg_match['observaciones'].iloc[0] if en_db and 'observaciones' in seg_match.columns else ""
            new_obs = cols[-1].text_input("Nota", value=obs_db, key=f"o_{prod['id']}", label_visibility="collapsed")
            if new_obs != obs_db:
                with conectar() as conn: conn.execute("UPDATE seguimiento SET observaciones=? WHERE producto_id=? AND hito=?", (new_obs, prod['id'], hito))
        st.markdown("---")
    st.markdown('</div>', unsafe_allow_html=True)

    # BOTÓN PARA REABRIR (Solo Gerencia)
    if esta_guardado and es_jefe:
        if st.button("🔓 Reabrir Reporte", use_container_width=True):
            with conectar() as conn: conn.execute("DELETE FROM cierres_diarios WHERE proyecto_id=? AND fecha=?", (id_p, fecha_avance.isoformat()))

            st.rerun()
