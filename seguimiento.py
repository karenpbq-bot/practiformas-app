import streamlit as st
import pandas as pd
from datetime import datetime
import io
from base_datos import conectar, obtener_proyectos, actualizar_avance_real

# =========================================================
# 1. CONFIGURACIÓN Y DICCIONARIOS MAESTROS
# =========================================================
MAPEO_HITOS = {
    "Diseñado": "🗺️", "Fabricado": "🪚", "Material en Obra": "🚛",
    "Material en Ubicación": "📍", "Instalación de Estructura": "📦", 
    "Instalación de Puertas o Frentes": "🗄️", "Revisión y Observaciones": "🔍", "Entrega": "🤝"
}

HITOS_LIST = list(MAPEO_HITOS.keys())

def obtener_fecha_formateada():
    return datetime.now().strftime("%d/%m/%Y")

# =========================================================
# 2. LÓGICA DE CASCADA (REGISTRO ATÓMICO)
# =========================================================
def registrar_hitos_cascada(p_id, hito_final, fecha_str):
    supabase = conectar()
    try:
        safe_p_id = int(p_id)
        safe_fecha = str(fecha_str) if pd.notnull(fecha_str) else obtener_fecha_formateada()
        idx_limite = HITOS_LIST.index(hito_final)
        hitos_a_marcar = HITOS_LIST[:idx_limite + 1]
        
        for h in hitos_a_marcar:
            supabase.table("seguimiento").upsert({
                "producto_id": safe_p_id, 
                "hito": str(h), 
                "fecha": safe_fecha
            }, on_conflict="producto_id, hito").execute()
    except Exception as e:
        st.error(f"Error detallado en cascada: {e}")

# =========================================================
# 3. INTERFAZ PRINCIPAL
# =========================================================
def mostrar(supervisor_id=None):
    if 'bus_capa1' not in st.session_state: st.session_state.bus_capa1 = ""
    if 'bus_capa2' not in st.session_state: st.session_state.bus_capa2 = ""
    if 'columna_tecnica' not in st.session_state: st.session_state.columna_tecnica = None

    st.markdown("""
        <style>
        .block-container { padding: 1rem 1rem 0rem 1rem !important; }
        [data-testid="stVerticalBlock"] > div { gap: 0rem !important; padding: 0px !important; }
        .sticky-top { position: sticky; top: 0; background: white; z-index: 1000; border-bottom: 2px solid #FF8C00; margin-bottom: 0px !important; }
        .scroll-area { height: 600px; overflow-y: auto !important; overflow-x: auto !important; border: 1px solid #eee; margin-top: 0px !important; padding-top: 0px !important; }
        [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 2px !important; }
        .metric-small { font-size: 11px; font-weight: bold; color: #555; line-height: 1; }
        .pct-val { font-size: 13px; color: #FF8C00; font-weight: bold; }
        .stButton>button { height: 28px !important; font-size: 10px !important; padding: 0px 5px !important; }
        .stCheckbox { margin-bottom: 0px !important; }
        </style>
    """, unsafe_allow_html=True)
    
    st.header("📈 Panel de Seguimiento Matricial")
    supabase = conectar()

    with st.expander("📁 1. SELECCIÓN DE PROYECTO", expanded=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        bus_p = c1.text_input("🔍 Buscar proyecto o cliente...", key="bus_seg_proy")
        df_p = obtener_proyectos(bus_p, supervisor_id=supervisor_id)
        if c3.toggle("Solo activos", value=True) and not df_p.empty:
            df_p = df_p[df_p['estatus'] == 'Activo']
        if df_p.empty: st.info("No hay proyectos."); return
        opciones = {f"{r['proyecto_text']} — {r['cliente']}": r['id'] for _, r in df_p.iterrows()}
        sel_p_nom = c2.selectbox("Elija Proyecto:", ["Seleccione..."] + list(opciones.keys()))

    if sel_p_nom == "Seleccione...": st.info("💡 Por favor, seleccione un proyecto."); return

    id_p = opciones[sel_p_nom]
    p_data = df_p[df_p['id'] == id_p].iloc[0]

    # --- PASO CRÍTICO: CARGA DE DATOS ANTES DE LAS HERRAMIENTAS ---
    res_base = supabase.table("productos").select("*").eq("proyecto_id", id_p).execute()
    prods_all = pd.DataFrame(res_base.data)
    ids_list = prods_all['id'].tolist() if not prods_all.empty else []
    segs_res = supabase.table("seguimiento").select("*").in_("producto_id", ids_list).execute()
    segs = pd.DataFrame(segs_res.data) if segs_res.data else pd.DataFrame(columns=['producto_id','hito','fecha','observaciones'])

    # --- BLOQUE 2: HERRAMIENTAS ---
    with st.expander("🛠️ 2. HERRAMIENTAS, PONDERACIÓN E IMPORTACIÓN", expanded=False):
        t1, t2, t3 = st.tabs(["⚖️ Ponderación", "🔍 Filtros", "📥 Imp/Exp"])
        
        with t1:
            cols_w = st.columns(4)
            pesos = {h: cols_w[i % 4].number_input(f"{h} (%)", value=12.5, step=0.5, key=f"w_{h}") for i, h in enumerate(HITOS_LIST)}

        with t2:
            f1, f2, f3 = st.columns(3)
            opc_f = {"Sin grupo": None, "Ubicación": "ubicacion", "Tipo": "tipo"}
            st.session_state.columna_tecnica = opc_f[f1.selectbox("📂 Agrupar por:", list(opc_f.keys()))]
            st.session_state.bus_capa1 = f2.text_input("🔍 Filtro Primario (Zona/Tipo):", key="f_capa1")
            st.session_state.bus_capa2 = f3.text_input("🔍 Refinar Búsqueda:", key="f_capa2")

        # Aplicamos filtros para que T3 (Exportación) los vea
        prods_filt = prods_all.copy()
        if not prods_filt.empty:
            b1, b2 = st.session_state.bus_capa1, st.session_state.bus_capa2
            if b1: prods_filt = prods_filt[prods_filt['ubicacion'].str.contains(b1, case=False) | prods_filt['tipo'].str.contains(b1, case=False)]
            if b2: prods_filt = prods_filt[prods_filt['ubicacion'].str.contains(b2, case=False) | prods_filt['tipo'].str.contains(b2, case=False)]

        with t3:
            archivo_excel = st.file_uploader("📥 Cargar Seguimiento Excel", type=["xlsx"], key="uploader_seguimiento_unico")
            if archivo_excel:
                df_imp = pd.read_excel(archivo_excel)
                df_imp.columns = [str(c).lower().replace('ó','o').replace('á','a').strip() for c in df_imp.columns]
                
                if st.button("🚀 Procesar Importación Rápida"):
                    prods_db = supabase.table("productos").select("id, ubicacion, tipo, ml").eq("proyecto_id", id_p).execute()
                    prods_df = pd.DataFrame(prods_db.data)
                    registros_masivos = []
                    fecha_sistema = obtener_fecha_formateada() # Fecha de respaldo

                    for _, row_ex in df_imp.iterrows():
                        match = prods_df[
                            (prods_df['ubicacion'].astype(str).str.lower().str.strip() == str(row_ex.get('ubicacion','')).lower().strip()) & 
                            (prods_df['tipo'].astype(str).str.lower().str.strip() == str(row_ex.get('tipo','')).lower().strip()) & 
                            (abs(prods_df['ml'] - float(row_ex.get('ml', 0))) < 0.05)
                        ]
                        
                        if not match.empty:
                            p_id = int(match.iloc[0]['id'])
                            
                            # Buscamos el hito más avanzado que tenga una fecha o marca
                            hito_max = None
                            fecha_excel = None
                            
                            for h in reversed(HITOS_LIST):
                                col_nombre = h.lower().replace('ñ','n').replace('ó','o').replace('á','a')
                                valor_celda = row_ex.get(col_nombre, "")
                                
                                if str(valor_celda).upper() not in ["", "NAN", "NO", "NONE"]:
                                    hito_max = h
                                    # Intentamos rescatar la fecha de la celda
                                    if isinstance(valor_celda, (datetime, pd.Timestamp)):
                                        fecha_excel = valor_celda.strftime("%d/%m/%Y")
                                    else:
                                        # Si no es fecha pero hay texto, usamos la fecha de hoy
                                        fecha_excel = fecha_sistema
                                    break
                            
                            if hito_max:
                                idx_limite = HITOS_LIST.index(hito_max)
                                for i in range(idx_limite + 1):
                                    registros_masivos.append({
                                        "producto_id": p_id, 
                                        "hito": HITOS_LIST[i], 
                                        "fecha": fecha_excel # Registra la fecha rescatada del Excel
                                    })

                    if registros_masivos:
                        df_limpio = pd.DataFrame(registros_masivos).drop_duplicates(subset=['producto_id', 'hito'])
                        supabase.table("seguimiento").upsert(df_limpio.to_dict(orient='records'), on_conflict="producto_id, hito").execute()
                        st.success(f"✅ Se han importado los avances respetando las fechas del Excel.")
                        st.rerun()
            
            st.divider()
            st.write("📤 **Exportar Reporte Maestro**")
            df_exp = prods_filt.copy()
            for h in HITOS_LIST:
                df_exp[h] = df_exp['id'].apply(lambda x: segs[(segs['producto_id']==x) & (segs['hito']==h)]['fecha'].iloc[0] if not segs[(segs['producto_id']==x) & (segs['hito']==h)].empty else "")
            
            output_exp = io.BytesIO()
            with pd.ExcelWriter(output_exp, engine='openpyxl') as writer:
                df_exp.to_excel(writer, index=False, sheet_name='Seguimiento')
            st.download_button(label="📥 DESCARGAR EXCEL", data=output_exp.getvalue(), file_name=f"Seguimiento_{sel_p_nom}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    # --- CÁLCULOS DE AVANCE ---
    def calcular_avance(df_m, df_s, t_w):
        if df_m.empty: return 0.0
        puntos = sum(sum(t_w.get(h, 0) for h in df_s[df_s['producto_id'] == m['id']]['hito'].tolist()) for _, m in df_m.iterrows())
        return round(puntos / len(df_m), 2)

    # === CÁLCULOS PREVIOS (Garantizan que no haya 'aire' entre contenedores) ===
    pct_total = calcular_avance(prods_all, segs, pesos)
    pct_parcial = calcular_avance(prods_filt, segs, pesos)
    # BLINDAJE DE FECHA: Formato Día/Mes/Año para todo el sistema
    f_str_hoy = fecha_reg.strftime("%d/%m/%Y") 

    # =========================================================
    # 4 y 5. INTERFAZ UNIFICADA (STICKY + MATRIZ)
    # =========================================================
    
    # Inyectamos el Sticky y el inicio del Scroll en un solo bloque para eliminar el recuadro vacío
    st.markdown(f"""
        <div class="sticky-top">
            <div style="display: flex; justify-content: space-between; padding: 8px 12px; background: #fff; border-bottom: 1px solid #eee;">
                <div class='metric-small'>AVANCE TOTAL<br><span class='pct-val'>{pct_total}%</span></div>
                <div class='metric-small'>AVANCE FILTRO<br><span class='pct-val'>{pct_parcial}%</span></div>
                <div class='metric-small'>FECHA REGISTRO<br><span style="color:#000;">{f_str_hoy}</span></div>
            </div>
        </div>
        <div class="scroll-area">
    """, unsafe_allow_html=True)

    # Botón de Guardado y Encabezado de Columnas
    c_save = st.columns([3, 1.2])
    with c_save[1]:
        if st.button("💾 GUARDAR TODO", use_container_width=True, type="primary", key="btn_final_save"):
            actualizar_avance_real(id_p)
            nota_actual = p_data.get('partida', '')
            supabase.table("proyectos").update({"partida": nota_actual, "avance": pct_total}).eq("id", id_p).execute()
            st.success("¡Datos Guardados!"); st.rerun()

    cols_h = st.columns([3] + [0.7]*8 + [2])
    cols_h[0].markdown("<div style='font-size:11px; font-weight:bold;'>Mueble / ml</div>", unsafe_allow_html=True)
    
    for i, hito in enumerate(HITOS_LIST):
        with cols_h[i+1]:
            if st.button("✅", key=f"ms_{hito}"):
                for pid in prods_filt['id'].tolist(): 
                    registrar_hitos_cascada(pid, hito, f_str_hoy)
                st.rerun()
            st.write(MAPEO_HITOS[hito])
    cols_h[-1].markdown("<div style='font-size:11px; font-weight:bold;'>Nota</div>", unsafe_allow_html=True)

    # --- FUNCIÓN DE RENDERIZADO (Dentro del contenedor de Scroll) ---
    def render_final(p_row, s_data, r_usr, f_formato):
        cs = st.columns([3] + [0.7]*8 + [2])
        # Info del Mueble
        cs[0].markdown(f"<div style='font-size:10px; line-height:1;'><b>{p_row['ubicacion']}</b><br>{p_row['tipo']} ({p_row['ml']}m)</div>", unsafe_allow_html=True)
        
        for i, h in enumerate(HITOS_LIST):
            m = s_data[(s_data['producto_id'] == p_row['id']) & (s_data['hito'] == h)]
            en_db = not m.empty
            # Seguridad: Bloqueo si hay hitos posteriores o si es Supervisor intentando desmarcar
            tiene_post = not s_data[(s_data['producto_id'] == p_row['id']) & (s_data['hito'].isin(HITOS_LIST[i+1:]))].empty
            bloqueo = (en_db and r_usr == "Supervisor") or (en_db and tiene_post)

            if cs[i+1].checkbox(" ", key=f"mat_{p_row['id']}_{h}", value=en_db, disabled=bloqueo):
                if not en_db: 
                    registrar_hitos_cascada(p_row['id'], h, f_formato)
                    st.rerun()
            elif en_db and not bloqueo and r_usr != "Supervisor":
                supabase.table("seguimiento").delete().eq("producto_id", p_row['id']).eq("hito", h).execute()
                st.rerun()
        
        # Nota/Observación
        obs = m['observaciones'].iloc[0] if en_db and 'observaciones' in m.columns else ""
        cs[-1].text_input("N", value=obs, key=f"obs_f_{p_row['id']}", label_visibility="collapsed")

    # --- EJECUCIÓN DEL RENDERIZADO POR GRUPOS O LISTA ---
    rol_usr = st.session_state.rol
    c_tec = st.session_state.columna_tecnica
    
    if c_tec:
        for n, g in prods_filt.groupby(c_tec):
            st.markdown(f"<div style='background:#f1f1f1; padding:2px 5px; font-size:10px; font-weight:bold; border-left: 3px solid #FF8C00;'>📂 {n.upper()}</div>", unsafe_allow_html=True)
            for _, r in g.iterrows(): render_final(r, segs, rol_usr, f_str_hoy)
    else:
        for _, r in prods_filt.iterrows(): render_final(r, segs, rol_usr, f_str_hoy)

    # CIERRE FINAL DEL CONTENEDOR DE SCROLL
    st.markdown('</div>', unsafe_allow_html=True)
