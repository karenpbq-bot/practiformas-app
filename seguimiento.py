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
        # Aseguramos que p_id sea un entero de Python puro (evita tipos de numpy)
        safe_p_id = int(p_id)
        
        # Validamos que la fecha no sea un valor nulo de Pandas (NaN)
        safe_fecha = str(fecha_str) if pd.notnull(fecha_str) else obtener_fecha_formateada()
        
        idx_limite = HITOS_LIST.index(hito_final)
        hitos_a_marcar = HITOS_LIST[:idx_limite + 1]
        
        for h in hitos_a_marcar:
            # UPSERT con datos limpios
            supabase.table("seguimiento").upsert({
                "producto_id": safe_p_id, 
                "hito": str(h), 
                "fecha": safe_fecha
            }, on_conflict="producto_id, hito").execute()
            
    except Exception as e:
        # Esto nos dará más detalle si el error persiste
        st.error(f"Error detallado en cascada: {e}")

# =========================================================
# 3. INTERFAZ PRINCIPAL
# =========================================================
def mostrar(supervisor_id=None):
  # CSS Profesional: Elimina cuadros vacíos y gaps de Streamlit
    st.markdown("""
        <style>
        /* 1. Neutralizar gaps de Streamlit y márgenes de página */
        .block-container { padding: 1rem 1rem 0rem 1rem !important; }
        [data-testid="stVerticalBlock"] > div { gap: 0rem !important; padding: 0px !important; }
        
        /* 2. Centro de Control y Encabezado FIJO (Sticky) */
        .sticky-top { 
            position: sticky; top: 0; background: white; z-index: 1000; 
            border-bottom: 2px solid #FF8C00; margin-bottom: 0px !important;
        }

        /* 3. Área de productos: Altura para ~25 líneas y scroll fluido */
        .scroll-area { 
            height: 600px; overflow-y: auto !important; overflow-x: auto !important; 
            border: 1px solid #eee; margin-top: 0px !important; padding-top: 0px !important;
        }

        /* 4. Forzar vista matricial (no apilar en móvil) */
        [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 2px !important; }

        /* 5. Ajuste de métricas y botones mini */
        .metric-small { font-size: 11px; font-weight: bold; color: #555; line-height: 1; }
        .pct-val { font-size: 13px; color: #FF8C00; font-weight: bold; }
        .stButton>button { height: 28px !important; font-size: 10px !important; padding: 0px 5px !important; }
        .stCheckbox { margin-bottom: 0px !important; }
        </style>
    """, unsafe_allow_html=True)
    
    st.header("📈 Panel de Seguimiento Matricial")
    supabase = conectar()

    # --- BLOQUE 1 (PLEGABLE): SELECCIÓN DE PROYECTO ---
    with st.expander("📁 1. SELECCIÓN DE PROYECTO", expanded=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        bus_p = c1.text_input("🔍 Buscar proyecto o cliente...", key="bus_seg_proy")
        df_p = obtener_proyectos(bus_p, supervisor_id=supervisor_id)
        
        solo_activos = c3.toggle("Solo activos", value=True)
        if solo_activos and not df_p.empty:
            df_p = df_p[df_p['estatus'] == 'Activo']

        if df_p.empty:
            st.info("No hay proyectos."); return

        opciones = {f"{r['proyecto_text']} — {r['cliente']}": r['id'] for _, r in df_p.iterrows()}
        sel_p_nom = c2.selectbox("Elija Proyecto:", ["Seleccione..."] + list(opciones.keys()))

    if sel_p_nom == "Seleccione...":
        st.info("💡 Por favor, seleccione un proyecto para cargar la matriz."); return

    id_p = opciones[sel_p_nom]
    p_data = df_p[df_p['id'] == id_p].iloc[0]

    # --- CARGA DE DATOS ---
    res_base = supabase.table("productos").select("*").eq("proyecto_id", id_p).execute()
    prods_all = pd.DataFrame(res_base.data)
    ids_list = prods_all['id'].tolist() if not prods_all.empty else []
    segs_res = supabase.table("seguimiento").select("*").in_("producto_id", ids_list).execute()
    segs = pd.DataFrame(segs_res.data) if segs_res.data else pd.DataFrame(columns=['producto_id','hito','fecha','observaciones'])

    # IMPORTANTE: También define prods_filt aquí arriba para que las herramientas lo vean
    prods_filt = prods_all.copy()
    if not prods_filt.empty:
        if bus_capa1: prods_filt = prods_filt[prods_filt['ubicacion'].str.contains(bus_capa1, case=False) | prods_filt['tipo'].str.contains(bus_capa1, case=False)]
        if bus_capa2: prods_filt = prods_filt[prods_filt['ubicacion'].str.contains(bus_capa2, case=False) | prods_filt['tipo'].str.contains(bus_capa2, case=False)]

    # --- BLOQUE 2 (PLEGABLE): CONFIGURACIÓN, PONDERACIÓN E IMPORTACIÓN ---
    with st.expander("🛠️ 2. HERRAMIENTAS, PONDERACIÓN E IMPORTACIÓN", expanded=False):
        t1, t2, t3 = st.tabs(["⚖️ Ponderación de Etapas", "🔍 Filtros de Matriz", "📥 Importar Avances"])
        
        with t1:
            st.write("Ajuste el peso (%) de cada etapa según el esfuerzo real:")
            cols_w = st.columns(4)
            pesos = {h: cols_w[i % 4].number_input(f"{h} (%)", value=12.5, step=0.5, key=f"w_{h}") for i, h in enumerate(HITOS_LIST)}
            if sum(pesos.values()) != 100:
                st.warning(f"⚠️ La suma actual es {sum(pesos.values())}%. Ajuste para llegar a 100%.")

        with t2:
            f1, f2, f3 = st.columns(3)
            opciones_filtro = {"Sin grupo": None, "Ubicación": "ubicacion", "Tipo": "tipo"}
            columna_tecnica = opciones_filtro[f1.selectbox("📂 Agrupar por:", list(opciones_filtro.keys()))]
            bus_capa1 = f2.text_input("🔍 Filtro Primario (Zona/Tipo):")
            bus_capa2 = f3.text_input("🔍 Refinar Búsqueda:")
            
        with t3:
            archivo_excel = st.file_uploader("📥 Cargar Seguimiento Excel", type=["xlsx"])
            if archivo_excel:
                df_imp = pd.read_excel(archivo_excel)
                # Normalización de encabezados para el Match
                df_imp.columns = [str(c).lower().replace('ó','o').replace('á','a').strip() for c in df_imp.columns]
                
                if st.button("🚀 Procesar Importación Rápida"):
                    prods_db = supabase.table("productos").select("id, ubicacion, tipo, ml").eq("proyecto_id", id_p).execute()
                    prods_df = pd.DataFrame(prods_db.data)
                    
                    # --- OPTIMIZACIÓN: CARGA POR LOTES ---
                    registros_masivos = []
                    fecha_hoy = obtener_fecha_formateada()

                    for _, row_ex in df_imp.iterrows():
                        match = prods_df[
                            (prods_df['ubicacion'].astype(str).str.lower().str.strip() == str(row_ex.get('ubicacion','')).lower().strip()) & 
                            (prods_df['tipo'].astype(str).str.lower().str.strip() == str(row_ex.get('tipo','')).lower().strip()) & 
                            (abs(prods_df['ml'] - float(row_ex.get('ml', 0))) < 0.05)
                        ]
                        
                        if not match.empty:
                            p_id = int(match.iloc[0]['id'])
                            # Identificar hito máximo para aplicar cascada
                            hito_max = None
                            for h in reversed(HITOS_LIST):
                                col_ex = h.lower().replace('ñ','n').replace('ó','o').replace('á','a')
                                if str(row_ex.get(col_ex, "")).upper() not in ["", "NAN", "NO", "NONE"]:
                                    hito_max = h
                                    break
                            
                            if hito_max:
                                # Agrupamos todos los hitos previos en la lista masiva
                                idx_limite = HITOS_LIST.index(hito_max)
                                for i in range(idx_limite + 1):
                                    registros_masivos.append({
                                        "producto_id": p_id,
                                        "hito": HITOS_LIST[i],
                                        "fecha": fecha_hoy
                                    })

                    # ENVÍO ÚNICO A LA BASE DE DATOS (CON LIMPIEZA DE DUPLICADOS)
                    if registros_masivos:
                        try:
                            # CORRECCIÓN: Eliminamos duplicados dentro de la lista de registros
                            # antes de enviarlos a Supabase para evitar el error 21000
                            df_limpio = pd.DataFrame(registros_masivos).drop_duplicates(subset=['producto_id', 'hito'])
                            registros_finales = df_limpio.to_dict(orient='records')

                            # Upsert masivo seguro
                            supabase.table("seguimiento").upsert(registros_finales, on_conflict="producto_id, hito").execute()
                            
                            st.success(f"✅ Se procesaron {len(df_imp)} productos correctamente.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error en carga masiva: {e}")
                    else:
                        st.warning("No se encontraron coincidencias para importar.")

        # --- BOTÓN DE EXPORTACIÓN (REUBICADO) ---
            st.divider()
            st.subheader("📤 Exportar Reporte")
            
            # Generamos el Excel basándonos en los filtros actuales de la matriz
            df_exp = prods_filt.copy().rename(columns={'proyecto_id': 'Id Proyecto', 'ubicacion': 'Ubicacion', 'tipo': 'Tipo', 'ctd': 'Ctd'})
            for h in HITOS_LIST:
                df_exp[h] = df_exp['id'].apply(lambda x: segs[(segs['producto_id']==x) & (segs['hito']==h)]['fecha'].iloc[0] if not segs[(segs['producto_id']==x) & (segs['hito']==h)].empty else "")
            
            output_exp = io.BytesIO()
            with pd.ExcelWriter(output_exp, engine='openpyxl') as writer:
                df_exp[['Id Proyecto', 'Ubicacion', 'Tipo', 'Ctd', 'ml'] + HITOS_LIST].to_excel(writer, index=False, sheet_name='Seguimiento')
            
            st.download_button(
                label="📥 DESCARGAR SEGUIMIENTO EXCEL",
                data=output_exp.getvalue(),
                file_name=f"Seguimiento_{sel_p_nom}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    # Aplicación de Capas de Filtro
    prods_filt = prods_all.copy()
    if not prods_filt.empty:
        if bus_capa1: prods_filt = prods_filt[prods_filt['ubicacion'].str.contains(bus_capa1, case=False) | prods_filt['tipo'].str.contains(bus_capa1, case=False)]
        if bus_capa2: prods_filt = prods_filt[prods_filt['ubicacion'].str.contains(bus_capa2, case=False) | prods_filt['tipo'].str.contains(bus_capa2, case=False)]

    # --- LÓGICA DE AVANCES % (TOTAL Y FILTRADO) ---
    def calcular_avance(df_m, df_s, t_pesos):
        if df_m.empty: return 0.0
        puntos = 0
        for _, m in df_m.iterrows():
            hechos = df_s[df_s['producto_id'] == m['id']]['hito'].tolist()
            puntos += sum([t_pesos.get(h, 0) for h in hechos])
        return round(puntos / len(df_m), 2)

    pct_total = calcular_avance(prods_all, segs, pesos)
    pct_parcial = calcular_avance(prods_filt, segs, pesos)

    # =========================================================
    # 4. CENTRO DE CONTROL COMPACTO (STICKY)
    # =========================================================
    st.markdown('<div class="sticky-top">', unsafe_allow_html=True)
    
    # Fila 1: Avance T | Avance P | Fecha | Guardar
    c_ctrl = st.columns([1, 1, 1.1, 1.2])
    c_ctrl[0].markdown(f"<div class='metric-small'>TOTAL<br><span class='pct-val'>{pct_total}%</span></div>", unsafe_allow_html=True)
    c_ctrl[1].markdown(f"<div class='metric-small'>FILTRO<br><span class='pct-val'>{pct_parcial}%</span></div>", unsafe_allow_html=True)
    
    with c_ctrl[2]:
        fecha_reg = st.date_input("F", datetime.now(), label_visibility="collapsed")
    
    with c_ctrl[3]:
        if st.button("💾 GUARDAR", use_container_width=True, type="primary"):
            actualizar_avance_real(id_p)
            # Aseguramos que la nota se guarde (usa la variable del text_area o la de la DB)
            val_nota = nota_proy if 'nota_proy' in locals() else p_data.get('partida', '')
            supabase.table("proyectos").update({"partida": val_nota, "avance": pct_total}).eq("id", id_p).execute()
            st.success("¡Guardado!"); st.rerun()

    # Fila 2: Encabezado Naranja (Mueble + Iconos ✅)
    cols_h = st.columns([3] + [0.7]*8 + [2])
    cols_h[0].markdown("<div style='font-size:11px; font-weight:bold; padding-top:5px;'>Mueble / ml</div>", unsafe_allow_html=True)
    
    for i, hito in enumerate(HITOS_LIST):
        with cols_h[i+1]:
            if st.button("✅", key=f"btn_massive_{hito}"):
                for pid in prods_filt['id'].tolist(): 
                    registrar_hitos_cascada(pid, hito, fecha_reg.strftime("%d/%m/%Y"))
                st.rerun()
            st.write(MAPEO_HITOS[hito])
    
    # La columna de Nota/Observación va FUERA del bucle for
    cols_h[-1].markdown("<div style='font-size:11px; font-weight:bold; padding-top:5px;'>Nota</div>", unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True) # Cierre exacto del Sticky

    # =========================================================
    # 5. MATRIZ DE PRODUCTOS (SCROLL)
    # =========================================================
    # Iniciamos el scroll inmediatamente después del encabezado naranja
    st.markdown('<div class="scroll-area">', unsafe_allow_html=True)
    
    def render_prods(df_render):
        rol = st.session_state.rol
        for _, prod in df_render.iterrows():
            cols = st.columns([3] + [0.7]*8 + [2])
            cols[0].markdown(f"<div style='font-size:11px; line-height:1.2;'><b>{prod['ubicacion']}</b> {prod['tipo']} <br><code style='font-size:10px;'>{prod['ml']} ml</code></div>", unsafe_allow_html=True)
            
            for i, hito in enumerate(HITOS_LIST):
                m = segs[(segs['producto_id'] == prod['id']) & (segs['hito'] == hito)]
                en_db = not m.empty
                tiene_post = not segs[(segs['producto_id'] == prod['id']) & (segs['hito'].isin(HITOS_LIST[i+1:]))].empty
                
                bloqueo = (en_db and rol == "Supervisor") or (en_db and tiene_post)

                if cols[i+1].checkbox("Ok", key=f"c_{prod['id']}_{hito}", value=en_db, label_visibility="collapsed", disabled=bloqueo):
                    if not en_db:
                        registrar_hitos_cascada(prod['id'], hito, fecha_reg.strftime("%d/%m/%Y"))
                        st.rerun()
                elif en_db and not tiene_post and rol != "Supervisor":
                    supabase.table("seguimiento").delete().eq("producto_id", prod['id']).eq("hito", hito).execute()
                    st.rerun()
            
            # Nota individual
            obs_db = m['observaciones'].iloc[0] if en_db and 'observaciones' in m.columns else ""
            cols[-1].text_input("N", value=obs_db, key=f"o_{prod['id']}", label_visibility="collapsed")

    # Renderizado con lógica de agrupación
    if columna_tecnica:
        for n, g in prods_filt.groupby(columna_tecnica):
            st.markdown(f"<div style='background:#f1f1f1; padding:2px 5px; font-size:11px; font-weight:bold;'>📂 {n.upper()}</div>", unsafe_allow_html=True)
            render_prods(g)
    else:
        render_prods(prods_filt)
        
    st.markdown('</div>', unsafe_allow_html=True)

