import streamlit as st
import pandas as pd
from datetime import datetime
from base_datos import conectar, obtener_proyectos, actualizar_avance_real

# =========================================================
# 1. CONFIGURACIÓN Y DICCIONARIOS MAESTROS
# =========================================================
MAPEO_HITOS = {
    "Diseñado": "🗺️", "Fabricado": "🪚", "Material en Obra": "🚛",
    "Material en Ubicación": "📍", "Instalación de Estructura": "📦", 
    "Instalación de Puertas o Frentes": "🗄️", "Revisión y Observaciones": "🔍", "Entrega": "🤝"
}

LEYENDA_DETALLADA = {
    "🗺️": "Diseño", "🪚": "Fabricación", "🚛": "En Obra", "📍": "En Ubicación",
    "📦": "Estructura", "🗄️": "Frentes", "🔍": "Revisión", "🤝": "Entrega"
}

def obtener_fecha_formateada():
    return datetime.now().strftime("%d/%m/%Y")

# =========================================================
# 2. LÓGICA DE CASCADA (RESTAURADA)
# =========================================================
def registrar_hitos_cascada(p_id, hito_final, fecha_str):
    supabase = conectar()
    hitos_orden = list(MAPEO_HITOS.keys())
    try:
        idx_limite = hitos_orden.index(hito_final)
        hitos_a_marcar = hitos_orden[:idx_limite + 1]
        for h in hitos_a_marcar:
            # Preserva la fecha si ya existe, si no, inserta la actual
            supabase.table("seguimiento").upsert({
                "producto_id": int(p_id), "hito": h, "fecha": fecha_str
            }, on_conflict="producto_id, hito").execute()
    except Exception as e:
        st.error(f"Error en cascada: {e}")

# =========================================================
# 3. INTERFAZ PRINCIPAL Y TRIPLE FILTRO
# =========================================================
def mostrar(supervisor_id=None):
    st.markdown("""
        <style>
        .h-fix { position: sticky; top: 0; background: white; z-index: 1000; border-bottom: 3px solid #FF8C00; padding: 10px 0; }
        .scroll-area { max-height: 500px; overflow-y: auto; overflow-x: hidden; padding-top: 10px; }
        </style>
    """, unsafe_allow_html=True)
    
    st.header("📈 Panel de Seguimiento Matricial")
    supabase = conectar()

    # --- FILTRO 1: PROYECTO ---
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        bus_p = c1.text_input("🔍 Buscar proyecto...", key="bus_seg_proy")
        df_p = obtener_proyectos(bus_p, supervisor_id=supervisor_id)
        
        solo_activos = c3.toggle("Solo activos", value=True)
        if solo_activos and not df_p.empty:
            df_p = df_p[df_p['estatus'] == 'Activo']

        if df_p.empty:
            st.info("No hay proyectos."); return

        opciones = {f"{r['proyecto_text']} — {r['cliente']}": r['id'] for _, r in df_p.iterrows()}
        sel_p_nom = c2.selectbox("Seleccione Proyecto:", ["Seleccione..."] + list(opciones.keys()))

    if sel_p_nom == "Seleccione...":
        st.info("💡 Seleccione un proyecto."); return

    id_p = opciones[sel_p_nom]
    p_data = df_p[df_p['id'] == id_p].iloc[0]

    # --- FILTRO 2 Y 3: BÚSQUEDA DOBLE Y AGRUPACIÓN ---
    with st.expander("🛠️ Filtros Avanzados e Importación", expanded=False):
        f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.2, 1])
        opciones_filtro = {"Sin grupo": None, "Ubicación": "ubicacion", "Tipo": "tipo"}
        columna_tecnica = opciones_filtro[f1.selectbox("📂 Agrupar por:", list(opciones_filtro.keys()))]
        
        bus_capa1 = f2.text_input("🔍 Filtro Primario:")
        bus_capa2 = f3.text_input("🔍 Refinar:")
        
        # --- REINCORPORACIÓN: IMPORTAR EXCEL ---
        archivo_excel = st.file_uploader("📥 Importar Avances (.xlsx)", type=["xlsx"])
        if archivo_excel:
            try:
                df_imp = pd.read_excel(archivo_excel)
                if st.button("🚀 Procesar Importación"):
                    for _, row in df_imp.iterrows():
                        if 'id' in row and 'hito' in row:
                            registrar_hitos_cascada(row['id'], row['hito'], obtener_fecha_formateada())
                    actualizar_avance_real(id_p); st.success("Importación exitosa"); st.rerun()
            except Exception as e: st.error(f"Error en archivo: {e}")

    # --- CARGA DE DATOS ---
    res_base = supabase.table("productos").select("*").eq("proyecto_id", id_p).execute()
    prods = pd.DataFrame(res_base.data)
    
    ids_list = prods['id'].tolist() if not prods.empty else []
    segs_res = supabase.table("seguimiento").select("*").in_("producto_id", ids_list).execute()
    segs = pd.DataFrame(segs_res.data) if segs_res.data else pd.DataFrame(columns=['producto_id','hito','fecha','observaciones'])

    # Aplicación de Búsqueda Doble
    if not prods.empty:
        if bus_capa1: prods = prods[prods['ubicacion'].str.contains(bus_capa1, case=False) | prods['tipo'].str.contains(bus_capa1, case=False)]
        if bus_capa2: prods = prods[prods['ubicacion'].str.contains(bus_capa2, case=False) | prods['tipo'].str.contains(bus_capa2, case=False)]

    # =========================================================
    # SECCIÓN 4: ENCABEZADO FIJO (STICKY)
    # =========================================================
    st.markdown('<div class="h-fix">', unsafe_allow_html=True)
    cols_h = st.columns([3] + [0.7]*8 + [2])
    cols_h[0].write("**Producto / Medida**") # ETIQUETA CORREGIDA
    
    HITOS_LIST = list(MAPEO_HITOS.keys())
    for i, hito in enumerate(HITOS_LIST):
        with cols_h[i+1]:
            if st.button("✅", key=f"btn_all_{hito}"):
                for p_id in prods['id'].tolist(): registrar_hitos_cascada(p_id, hito, obtener_fecha_formateada())
                actualizar_avance_real(id_p); st.rerun()
            st.write(MAPEO_HITOS[hito])
    cols_h[-1].write("Nota")
    st.markdown('</div>', unsafe_allow_html=True)

    # =========================================================
    # SECCIÓN 5: ÁREA DE SCROLL Y FILAS
    # =========================================================
    st.markdown('<div class="scroll-area">', unsafe_allow_html=True)
    
    def render_prods(df):
        for _, prod in df.iterrows():
            with st.container():
                cols = st.columns([3] + [0.7]*8 + [2])
                cols[0].markdown(f"**{prod['ubicacion']}** {prod['tipo']} `{prod['ml']} ml`", unsafe_allow_html=True)
                
                for i, hito in enumerate(HITOS_LIST):
                    key_c = f"c_{prod['id']}_{hito}"
                    seg_match = segs[(segs['producto_id'] == prod['id']) & (segs['hito'] == hito)]
                    en_db = not seg_match.empty
                    
                    # Lógica de bloqueo de desmarcado (8 a 1)
                    tiene_posterior = False
                    if i < len(HITOS_LIST) - 1:
                        tiene_posterior = not segs[(segs['producto_id'] == prod['id']) & (segs['hito'] == HITOS_LIST[i+1])].empty
                    
                    rol = st.session_state.rol
                    bloqueo = (en_db and rol == "Supervisor") or (en_db and tiene_posterior)

                    if cols[i+1].checkbox("Ok", key=key_c, value=en_db, label_visibility="collapsed", disabled=bloqueo):
                        if not en_db:
                            registrar_hitos_cascada(prod['id'], hito, obtener_fecha_formateada())
                            actualizar_avance_real(id_p); st.rerun()
                    elif en_db and not tiene_posterior and rol != "Supervisor":
                        supabase.table("seguimiento").delete().eq("producto_id", prod['id']).eq("hito", hito).execute()
                        actualizar_avance_real(id_p); st.rerun()
                
                # Notas
                obs_db = seg_match['observaciones'].iloc[0] if en_db and 'observaciones' in seg_match.columns else ""
                new_obs = cols[-1].text_input("N", value=obs_db, key=f"o_{prod['id']}", label_visibility="collapsed")
                if new_obs != obs_db:
                    supabase.table("seguimiento").update({"observaciones": new_obs}).eq("producto_id", prod['id']).eq("hito", hito).execute()

    if columna_tecnica:
        for nombre, grupo in prods.groupby(columna_tecnica):
            st.markdown(f"#### 📂 {nombre}")
            render_prods(grupo)
    else:
        render_prods(prods)
    
    st.markdown('</div>', unsafe_allow_html=True)

    # BOTÓN DE GUARDADO FINAL (Con Hora Automática)
    if st.button("💾 FINALIZAR Y GUARDAR AVANCE", use_container_width=True, type="primary"):
        actualizar_avance_real(id_p)
        ahora = datetime.now()
        supabase.table("cierres_diarios").insert({
            "proyecto_id": id_p, "fecha": ahora.strftime("%d/%m/%Y"), 
            "hora": ahora.strftime("%H:%M:%S"), "cerrado_por": st.session_state.get('id_usuario', 0)
        }).execute()
        st.success("Avance guardado."); st.rerun()
