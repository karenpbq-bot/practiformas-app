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
def mostrar(supervisor_id=None, rol=None):
    # Forzamos que el rol se guarde y se limpie de espacios
    if rol:
        st.session_state.rol = str(rol).strip().lower()
    
    # Diagnóstico secreto (Descomenta la línea de abajo si el botón sigue sin salir)
    # st.write(f"DEBUG: Rol en seguimiento es: '{st.session_state.get('rol')}'")
        
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

    # --- F. FILA DE ACCIONES (RECONSTRUCCIÓN TOTAL) ---
    st.divider()
    
    # 1. Identificación Blindada
    rol_final = str(rol if rol else st.session_state.get('rol', 'Supervisor')).strip().lower()
    es_jefe = rol_final in ["admin", "gerente", "administrador"]

    # 2. Definición de Columnas (7 espacios obligatorios para Admin/Gerente)
    # Ajustamos los pesos [1.5, 0.7, 0.7, 0.9, 0.9, 0.9, 0.9] para que no se amontonen
    if es_jefe:
        cols_acc = st.columns([1.5, 0.7, 0.7, 0.9, 0.9, 0.9, 0.9])
    else:
        cols_acc = st.columns([1.5, 0.8, 0.8, 1.2, 1.2, 1.2])
        
    # Col 0: Fecha
    f_reg = cols_acc[0].date_input("Fecha Registro", datetime.now(), format="DD/MM/YYYY", key="f_reg_v_final")
    
    # Col 1 y 2: Métricas
    cols_acc[1].metric("Av. Parcial", f"{p_par}%")
    cols_acc[2].metric("Av. Global", f"{p_tot}%")
    
    # Col 3: REFRESCAR (Aparecerá ahora sí)
    if cols_acc[3].button("🔄 Refrescar", use_container_width=True, key="btn_ref_v_final"):
        st.cache_data.clear() 
        st.rerun()

    # Col 4: GUARDAR
    if cols_acc[4].button("💾 Guardar", type="primary", use_container_width=True, key="btn_save_v_final"):
        f_hoy = f_reg.strftime("%d/%m/%Y")
        if st.session_state.cambios_pendientes:
            lote = [{"producto_id": c['pid'], "hito": c['hito'], "fecha": f_hoy} for c in st.session_state.cambios_pendientes]
            supabase.table("seguimiento").upsert(lote, on_conflict="producto_id, hito").execute()
            from base_datos import sincronizar_avances_estructural
            p_cod = df_p_all[df_p_all['id'] == id_p].iloc[0]['codigo']
            sincronizar_avances_estructural(p_cod)
            st.session_state.cambios_pendientes = []
            st.success("✅ Guardado")
            st.rerun()

    # Col 5: DESCARTAR
    if cols_acc[5].button("🚫 Descartar", use_container_width=True, key="btn_desc_v_final"):
        st.session_state.cambios_pendientes = []
        st.rerun()

    # Col 6: BORRAR TODO (Solo para Jefes)
    if es_jefe:
        if cols_acc[6].button("🔥 Borrar Todo", type="secondary", use_container_width=True, key="btn_burn_v_final"):
            ids_p = prods_all['id'].tolist()
            supabase.table("seguimiento").delete().in_("producto_id", ids_p).execute()
            from base_datos import sincronizar_avances_estructural
            p_cod = df_p_all[df_p_all['id'] == id_p].iloc[0]['codigo']
            sincronizar_avances_estructural(p_cod)
            st.warning("⚠️ Historial reseteado")
            st.rerun()

    # --- G. MATRIZ ---
    def render_matriz(df_r):
        # Usamos el permiso que ya validamos en la sección F
        es_jefe_m = es_jefe

        for _, p in df_r.iterrows():
            cols = st.columns([2.5] + [0.7]*8 + [1.5])
            cols[0].write(f"{p['ubicacion']} | {p['tipo']} | **{p['ml']} ML**")
            
            for i, h in enumerate(HITOS_LIST):
                # 1. ESTADO DE DATOS (Cascada Visual)
                en_db = not segs[(segs['producto_id'] == p['id']) & (segs['hito'] == h)].empty
                # Regla de cascada visual: si el hito 5 existe, el 1,2,3,4 se marcan automáticamente
                tiene_posterior_en_db = not segs[(segs['producto_id'] == p['id']) & (segs['hito'].isin(HITOS_LIST[i+1:]))].empty
                idx_mem = next((idx for idx, d in enumerate(st.session_state.cambios_pendientes) if d["pid"] == p['id'] and d["hito"] == h), None)
                
                # Definición final de "marcado"
                existe = en_db or tiene_posterior_en_db or (idx_mem is not None)
                
                # 2. REGLA DE BLOQUEO
                # es_jefe ya debe estar definido arriba en render_matriz
                bloqueado = False if es_jefe else (en_db or tiene_posterior_en_db)

                # 3. RENDERIZADO CON LLAVE DINÁMICA
                key_chx = f"v_final_{p['id']}_{h}_{'1' if existe else '0'}"

                if cols[i+1].checkbox("", key=key_chx, value=existe, disabled=bloqueado, label_visibility="collapsed"):
                    if not existe:
                        # ACCIÓN: MARCAR (Cascada hacia atrás en memoria)
                        for idx_p in range(i + 1):
                            h_p = HITOS_LIST[idx_p]
                            # Marcamos si no está en DB y no está ya en memoria
                            if segs[(segs['producto_id'] == p['id']) & (segs['hito'] == h_p)].empty:
                                if not any(d["pid"] == p['id'] and d["hito"] == h_p for d in st.session_state.cambios_pendientes):
                                    st.session_state.cambios_pendientes.append({"pid": p['id'], "hito": h_p})
                        st.rerun()
                else:
                    if existe:
                        # ACCIÓN: DESMARCAR (Solo permitido si bloqueado es False)
                        if idx_mem is not None:
                            st.session_state.cambios_pendientes.pop(idx_mem)
                        elif en_db and es_jefe:
                            # Borrado real en Supabase para el Admin
                            supabase.table("seguimiento").delete().eq("producto_id", p['id']).eq("hito", h).execute()
                            # Actualizamos Gantt/Métricas inmediatamente
                            from base_datos import sincronizar_avances_estructural
                            p_cod = df_p_all[df_p_all['id'] == id_p].iloc[0]['codigo']
                            sincronizar_avances_estructural(p_cod)
                        st.rerun()
            # Notas
            n_db = segs[(segs['producto_id'] == p['id']) & (segs['hito'] == HITOS_LIST[0])]['observaciones'].iloc[0] if not segs[(segs['producto_id'] == p['id']) & (segs['hito'] == HITOS_LIST[0])].empty else ""
            n_act = st.session_state.notas_pendientes.get(str(p['id']), n_db if pd.notnull(n_db) else "")
            nueva = cols[-1].text_input("N", value=n_act, key=f"nt_{p['id']}", label_visibility="collapsed")
            if nueva != n_act: st.session_state.notas_pendientes[str(p['id'])] = nueva

    # RENDERIZADO FINAL
    if agrupar_por != "Sin grupo":
        campo = "ubicacion" if agrupar_por == "Ubicación" else "tipo"
        for n, g in df_f.groupby(campo):
            st.markdown(f"**📂 {agrupar_por}: {n}**")
            render_matriz(g)
    else: 
        render_matriz(df_f)
    
    st.markdown('</div>', unsafe_allow_html=True)
