import streamlit as st
import pandas as pd
from datetime import datetime
import io
from base_datos import conectar, obtener_proyectos, obtener_productos_por_proyecto, obtener_seguimiento

# =========================================================
# 1. CONFIGURACIÓN Y DICCIONARIOS MAESTROS
# =========================================================
MAPEO_HITOS = {
    "Diseñado": "🗺️", "Fabricado": "🪚", "Material en Obra": "🚛",
    "Material en Ubicación": "📍", "Instalación de Estructura": "📦", 
    "Instalación de Puertas o Frentes": "🗄️", "Revisión y Observaciones": "🔍", "Entrega": "🤝"
}
HITOS_LIST = list(MAPEO_HITOS.keys())

# =========================================================
# 2. INTERFAZ PRINCIPAL
# =========================================================
def mostrar(supervisor_id=None):
    # --- A. MEMORIA TEMPORAL ---
    if 'cambios_pendientes' not in st.session_state:
        st.session_state.cambios_pendientes = []
    if 'notas_pendientes' not in st.session_state:
        st.session_state.notas_pendientes = {}

    # --- B. ESTILOS ---
    st.markdown("""
        <style>
        .sticky-top { position: sticky; top: 0; background: white; z-index: 1000; padding: 10px 0; border-bottom: 3px solid #FF8C00; }
        .scroll-area { max-height: 550px; overflow-y: auto; border: 1px solid #eee; padding: 10px; border-radius: 5px; }
        [data-testid="stMetricValue"] { color: #FF8C00 !important; font-weight: bold !important; font-size: 24px !important; }
        </style>
    """, unsafe_allow_html=True)

    supabase = conectar()

    # --- C. BÚSQUEDA DE PROYECTO ---
    nombre_proy_act = st.session_state.get('p_nom_sel', "Ninguno")
    st.markdown("### Seguimiento de Avances")
    st.markdown(f"<p style='font-size: 16px; color: #666; margin-top: -15px;'>{nombre_proy_act}</p>", unsafe_allow_html=True)

    with st.expander("🔍 Búsqueda de Proyecto", expanded=not st.session_state.get('id_p_sel')):
        c1, c2 = st.columns([2, 1])
        bus_p = c1.text_input("Escribe nombre, código o cliente...", key="bus_seg_v2")
        df_p_all = obtener_proyectos(bus_p)
        
        if supervisor_id and not df_p_all.empty:
            df_p_all = df_p_all[df_p_all['supervisor_id'] == supervisor_id]

        if not df_p_all.empty:
            opciones = {f"[{r['codigo']}] {r['proyecto_text']} - {r['cliente']}": r['id'] for _, r in df_p_all.iterrows()}
            lista_opc = ["-- Seleccionar --"] + list(opciones.keys())
            idx_s = lista_opc.index(st.session_state.p_nom_sel) if st.session_state.get('p_nom_sel') in lista_opc else 0
            sel_n = c2.selectbox("Seleccione Proyecto:", lista_opc, index=idx_s, key="sel_proy_seg")
            
            if sel_n != "-- Seleccionar --":
                st.session_state.id_p_sel = opciones[sel_n]
                st.session_state.p_nom_sel = sel_n
            else:
                st.session_state.id_p_sel = None

    if not st.session_state.get('id_p_sel'):
        st.info("💡 Por favor, seleccione un proyecto."); return

    # --- D. CARGA DE DATOS ---
    id_p = st.session_state.id_p_sel
    prods_all = obtener_productos_por_proyecto(id_p)
    if prods_all.empty: st.warning("Sin productos."); return

    # Cargamos seguimiento una sola vez al inicio
    segs_res = supabase.table("seguimiento").select("*").in_("producto_id", prods_all['id'].tolist()).execute()
    segs = pd.DataFrame(segs_res.data) if segs_res.data else pd.DataFrame(columns=['producto_id','hito','fecha','observaciones'])

    # --- E. HERRAMIENTAS ---
    with st.expander("⚙️ CONFIGURACIÓN AVANZADA Y HERRAMIENTAS"):
        t1, t2, t3, t4 = st.tabs(["⚖️ Ponderación", "🔍 Filtros", "📥 Importar", "📤 Exportación"])
        
        with t1:
            cols_w = st.columns(4)
            pesos = {h: cols_w[i % 4].number_input(f"{h} (%)", value=12.5, step=0.5, key=f"peso_{h}") for i, h in enumerate(HITOS_LIST)}
        
        with t2:
            f1, f2, f3 = st.columns(3)
            agrupar_por = f1.selectbox("Agrupar por:", ["Sin grupo", "Ubicación", "Tipo"], key="agrupar_seg")
            bus_c1 = f1.text_input("Filtro Primario:", key="f_pri_seg") # Movido a f1 para evitar duplicidad de columnas
            bus_c2 = f2.text_input("Refinar Búsqueda:", key="f_ref_seg")

        with t3:
            f_av = st.file_uploader("Subir Excel", type=["xlsx", "csv"], key="uploader_excel")
            if f_av and st.button("🚀 Iniciar Importación con Fechas del Excel"):
                try:
                    df_imp = pd.read_excel(f_av) if f_av.name.endswith('xlsx') else pd.read_csv(f_av)
                    lote_imp = []
                    
                    for _, r_ex in df_imp.iterrows():
                        # Buscamos el producto por Ubicación y Tipo
                        match = prods_all[
                            (prods_all['ubicacion'].astype(str).str.strip() == str(r_ex.get('Ubicacion','')).strip()) & 
                            (prods_all['tipo'].astype(str).str.strip() == str(r_ex.get('Tipo','')).strip())
                        ]
                        
                        if not match.empty:
                            pid = int(match.iloc[0]['id'])
                            
                            for h_nom in HITOS_LIST:
                                val_fecha = r_ex.get(h_nom)
                                
                                # Si la celda tiene contenido
                                if pd.notnull(val_fecha) and str(val_fecha).strip() != "":
                                    try:
                                        # FORZAMOS conversión a fecha para validar formato
                                        # Esto convierte tanto objetos Excel como texto "15/03/2024"
                                        fecha_dt = pd.to_datetime(val_fecha, dayfirst=True, errors='coerce')
                                        
                                        if pd.notnull(fecha_dt):
                                            f_str = fecha_dt.strftime("%d/%m/%Y")
                                            lote_imp.append({
                                                "producto_id": pid, 
                                                "hito": h_nom, 
                                                "fecha": f_str
                                            })
                                    except:
                                        continue # Si la fecha es basura, la ignora para no romper la API
                    
                    if lote_imp:
                        # Convertimos a DataFrame para eliminar duplicados accidentales
                        df_lote = pd.DataFrame(lote_imp).drop_duplicates(subset=['producto_id', 'hito'])
                        
                        # Ejecución en Supabase
                        supabase.table("seguimiento").upsert(
                            df_lote.to_dict(orient='records'), 
                            on_conflict="producto_id, hito"
                        ).execute()
                        
                        # Sincronización con el Gantt
                        from base_datos import sincronizar_avances_estructural
                        p_cod = df_p_all[df_p_all['id'] == id_p].iloc[0]['codigo']
                        sincronizar_avances_estructural(p_cod)
                        
                        st.success(f"✅ Se actualizaron {len(df_lote)} hitos con fechas reales.")
                        st.rerun()
                    else:
                        st.warning("No se encontraron coincidencias entre el Excel y los productos del proyecto.")
                
                except Exception as e:
                    st.error(f"Error procesando el archivo: {e}")

        with t4:
            df_exp = prods_all.copy()
            for h in HITOS_LIST: df_exp[h] = df_exp['id'].apply(lambda x: segs[(segs['producto_id']==x) & (segs['hito']==h)]['fecha'].iloc[0] if not segs[(segs['producto_id']==x) & (segs['hito']==h)].empty else "")
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_exp[['ubicacion', 'tipo', 'ctd', 'ml'] + HITOS_LIST].to_excel(writer, index=False)
            st.download_button("📥 Descargar Avance (Excel)", data=output.getvalue(), file_name=f"Avance_{id_p}.xlsx", use_container_width=True)

    # Filtrado
    df_f = prods_all.copy()
    if bus_c1: df_f = df_f[df_f['ubicacion'].str.contains(bus_c1, case=False) | df_f['tipo'].str.contains(bus_c1, case=False)]
    if bus_c2: df_f = df_f[df_f['ubicacion'].str.contains(bus_c2, case=False) | df_f['tipo'].str.contains(bus_c2, case=False)]

    def calc_avance(df_m, df_s):
        if df_m.empty: return 0.0
        puntos = sum([pesos.get(h, 0) for h in df_s[df_s['producto_id'].isin(df_m['id'].tolist())]['hito']])
        return round(puntos / len(df_m), 2)

    p_tot, p_par = calc_avance(prods_all, segs), calc_avance(df_f, segs)

    # --- F. FILA DE ACCIONES ---
    st.divider()
    rol_user = str(st.session_state.get('rol', '')).lower().strip()
    es_jefe = rol_user in ["admin", "administrador", "gerente"]

    # Ajuste de columnas dinámicas
    cols_acc = st.columns([1.5, 0.8, 0.8, 1.2, 1.2, 1.2, 1.2]) if es_jefe else st.columns([1.5, 0.8, 0.8, 1.2, 1.2, 1.2])
    
    f_reg = cols_acc[0].date_input("Fecha Registro", datetime.now(), format="DD/MM/YYYY", key="f_reg_u")
    cols_acc[1].metric("Av. Parcial", f"{p_par}%")
    cols_acc[2].metric("Av. Global", f"{p_tot}%")
    
    if cols_acc[3].button("🔄 Refrescar", use_container_width=True):
        st.cache_data.clear() # Limpia caché de base_datos.py para ver cambios reales
        st.rerun()

    # --- BOTÓN GUARDAR (Manteniendo tu lógica original) ---
    if cols_acc[4].button("💾 Guardar", type="primary", use_container_width=True):
        f_hoy = f_reg.strftime("%d/%m/%Y")
        try:
            # 1. Procesar cambios en memoria
            df_cp = pd.DataFrame(st.session_state.cambios_pendientes).rename(columns={'pid': 'producto_id'}) if st.session_state.cambios_pendientes else pd.DataFrame(columns=['producto_id', 'hito'])
            df_total = pd.concat([segs[['producto_id', 'hito']], df_cp[['producto_id', 'hito']]]).drop_duplicates()
            lote_save = []
            
            for pid in prods_all['id'].tolist():
                hitos_p = df_total[df_total['producto_id'] == pid]['hito'].tolist()
                if hitos_p:
                    # Regla de cascada al guardar
                    m_idx = max([HITOS_LIST.index(h) for h in hitos_p if h in HITOS_LIST])
                    for i in range(m_idx + 1):
                        if segs[(segs['producto_id'] == pid) & (segs['hito'] == HITOS_LIST[i])].empty:
                            lote_save.append({"producto_id": pid, "hito": HITOS_LIST[i], "fecha": f_hoy})
            
            if lote_save:
                supabase.table("seguimiento").upsert(lote_save, on_conflict="producto_id, hito").execute()

            # 2. Sincronizar Gantt
            from base_datos import sincronizar_avances_estructural
            p_cod = df_p_all[df_p_all['id'] == id_p].iloc[0]['codigo']
            sincronizar_avances_estructural(p_cod)
            
            # 3. Limpiar y refrescar
            st.session_state.cambios_pendientes, st.session_state.notas_pendientes = [], {}
            st.success("✅ Seguimiento guardado.")
            st.rerun()
        except Exception as e:
            st.error(f"Error al guardar: {e}")

    # --- BOTÓN DESCARTAR ---
    if cols_acc[5].button("🚫 Descartar Cambios", help="Limpia lo marcado en esta sesión", use_container_width=True):
        st.session_state.cambios_pendientes = []
        st.rerun()

    # --- BOTÓN SECRETO PARA JEFES (Reseteo) ---
    if es_jefe:
        if cols_acc[6].button("🔥 Borrar Todo", type="secondary", help="Resetea el avance a 0%"):
            ids_p = prods_all['id'].tolist()
            # Borrado físico en Supabase
            supabase.table("seguimiento").delete().in_("producto_id", ids_p).execute()
            # Forzar motor estructural a poner todo en 0
            from base_datos import sincronizar_avances_estructural
            p_cod = df_p_all[df_p_all['id'] == id_p].iloc[0]['codigo']
            sincronizar_avances_estructural(p_cod)
            st.success("Proyecto reseteado correctamente.")
            st.rerun()

    # --- G. MATRIZ ---
    st.markdown('<div class="sticky-top">', unsafe_allow_html=True)
    cols_h = st.columns([2.5] + [0.7]*8 + [1.5])
    cols_h[0].write("**Producto**")
    for i, h in enumerate(HITOS_LIST):
        with cols_h[i+1]:
            st.write(MAPEO_HITOS[h])
            if st.button("✅", key=f"bk_{h}"):
                f_hoy = f_reg.strftime("%d/%m/%Y")
                lote_grupal = []
                h_idx_objetivo = HITOS_LIST.index(h)
                
                for pid in df_f['id'].tolist():
                    # 1. REGLA DE CASCADA: Marcamos desde el inicio hasta el hito seleccionado
                    for idx_previo in range(h_idx_objetivo + 1):
                        hito_a_llenar = HITOS_LIST[idx_previo]
                        
                        # Verificamos si ya existe en DB o en cambios pendientes
                        en_db = not segs[(segs['producto_id'] == pid) & (segs['hito'] == hito_a_llenar)].empty
                        en_memoria = any(d["pid"] == pid and d["hito"] == hito_a_llenar for d in st.session_state.cambios_pendientes)
                        
                        if not en_db and not en_memoria:
                            # 2. LO AGREGAMOS A LA MEMORIA TEMPORAL (Esto hace que el check se vea puesto)
                            st.session_state.cambios_pendientes.append({"pid": int(pid), "hito": hito_a_llenar})
                            # 3. También lo preparamos para el lote de guardado inmediato si prefieres
                            lote_grupal.append({"producto_id": int(pid), "hito": hito_a_llenar, "fecha": f_hoy})
                
                if lote_grupal:
                    try:
                        # Guardamos en Supabase para asegurar los datos
                        supabase.table("seguimiento").upsert(lote_grupal, on_conflict="producto_id, hito").execute()
                        
                        # Actualizamos el Gantt
                        from base_datos import sincronizar_avances_estructural
                        p_data_obj = df_p_all[df_p_all['id'] == id_p].iloc[0]
                        sincronizar_avances_estructural(p_data_obj['codigo'])
                        
                        st.success(f"✅ Etapas hasta {h} marcadas visualmente.")
                        # 4. FORZAMOS EL REFRESCO: Al recargar, leerá la memoria y pondrá los checks
                        st.rerun() 
                    except Exception as e:
                        st.error(f"Error: {e}")
                                                
    cols_h[-1].write("**Notas**")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="scroll-area">', unsafe_allow_html=True)
    
    def render_matriz(df_r):
        # 1. Normalizamos el rol para evitar errores de mayúsculas (admin, Admin, etc.)
        rol_usuario = str(st.session_state.get('rol', 'Supervisor')).strip().lower()
        # Definimos permisos: admin, administrador o gerente pueden borrar
        es_jefe = rol_usuario in ["admin", "administrador", "gerente"]

        for _, p in df_r.iterrows():
            cols = st.columns([2.5] + [0.7]*8 + [1.5])
            cols[0].write(f"{p['ubicacion']} | {p['tipo']} | **{p['ml']} ML**")
            
            for i, h in enumerate(HITOS_LIST):
                # Estado actual en DB y en memoria
                en_db = not segs[(segs['producto_id'] == p['id']) & (segs['hito'] == h)].empty
                idx_mem = next((idx for idx, d in enumerate(st.session_state.cambios_pendientes) if d["pid"] == p['id'] and d["hito"] == h), None)
                existe = en_db or (idx_mem is not None)
                
                # REGLA DE BLOQUEO:
                # Solo bloqueamos al Supervisor si ya está en DB o si hay hitos posteriores.
                # El Jefe (Admin/Gerente) NUNCA ve nada bloqueado.
                tiene_post_db = not segs[(segs['producto_id'] == p['id']) & (segs['hito'].isin(HITOS_LIST[i+1:]))].empty
                bloqueado = False if es_jefe else (en_db or tiene_post_db)

                # Checkbox con la clave única
                valor_check = cols[i+1].checkbox("", key=f"chx_{p['id']}_{h}", value=existe, disabled=bloqueado, label_visibility="collapsed")
                
                # --- SI EL USUARIO CAMBIA EL CHECK ---
                if valor_check != existe:
                    if valor_check: # MARCAR (Con Cascada)
                        # Agregamos este y todos los anteriores a la memoria
                        for idx_p in range(i + 1):
                            h_prev = HITOS_LIST[idx_p]
                            en_db_prev = not segs[(segs['producto_id'] == p['id']) & (segs['hito'] == h_prev)].empty
                            en_mem_prev = any(d["pid"] == p['id'] and d["hito"] == h_prev for d in st.session_state.cambios_pendientes)
                            
                            if not en_db_prev and not en_mem_prev:
                                st.session_state.cambios_pendientes.append({"pid": p['id'], "hito": h_prev})
                        st.rerun()
                    
                    else: # DESMARCAR (Borrar)
                        if idx_mem is not None:
                            # Estaba en memoria, lo quitamos
                            st.session_state.cambios_pendientes.pop(idx_mem)
                            st.rerun()
                        elif en_db and es_jefe:
                            # Estaba en DB y soy jefe: BORRAR REAL
                            try:
                                supabase.table("seguimiento").delete().eq("producto_id", p['id']).eq("hito", h).execute()
                                # Sincronizamos el Gantt inmediatamente
                                from base_datos import sincronizar_avances_estructural
                                p_cod = df_p_all[df_p_all['id'] == id_p].iloc[0]['codigo']
                                sincronizar_avances_estructural(p_cod)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al eliminar: {e}")

            # Sección de Notas
            n_db = segs[(segs['producto_id'] == p['id']) & (segs['hito'] == HITOS_LIST[0])]['observaciones'].iloc[0] if not segs[(segs['producto_id'] == p['id']) & (segs['hito'] == HITOS_LIST[0])].empty else ""
            n_act = st.session_state.notas_pendientes.get(str(p['id']), n_db if pd.notnull(n_db) else "")
            nueva = cols[-1].text_input("N", value=n_act, key=f"nt_{p['id']}", label_visibility="collapsed")
            if nueva != n_act: st.session_state.notas_pendientes[str(p['id'])] = nueva

            # Sección de Notas
            n_db = segs[(segs['producto_id'] == p['id']) & (segs['hito'] == HITOS_LIST[0])]['observaciones'].iloc[0] if not segs[(segs['producto_id'] == p['id']) & (segs['hito'] == HITOS_LIST[0])].empty else ""
            n_act = st.session_state.notas_pendientes.get(str(p['id']), n_db if pd.notnull(n_db) else "")
            nueva = cols[-1].text_input("N", value=n_act, key=f"nt_{p['id']}", label_visibility="collapsed")
            if nueva != n_act: st.session_state.notas_pendientes[str(p['id'])] = nueva

    # Renderizado final
    if agrupar_por != "Sin grupo":
        campo = "ubicacion" if agrupar_por == "Ubicación" else "tipo"
        for n, g in df_f.groupby(campo):
            st.markdown(f"**📂 {agrupar_por}: {n}**")
            render_matriz(g)
    else: render_matriz(df_f)
    st.markdown('</div>', unsafe_allow_html=True)
