import streamlit as st
import pandas as pd
from datetime import datetime
from base_datos import conectar, obtener_proyectos, actualizar_avance_real

# =========================================================
# 1. DICCIONARIOS MAESTROS (FUNCIONALIDAD ORIGINAL PRESERVADA)
# =========================================================
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
    return datetime.now().strftime("%d/%m/%Y")

# =========================================================
# 2. LÓGICA DE PERSISTENCIA (SUPABASE - SIN CAMBIOS DE LÓGICA)
# =========================================================
def registrar_hitos_cascada(p_id, hito_final, fecha_str):
    """Marca el hito actual y anteriores preservando fechas previas (Lógica Original)."""
    supabase = conectar()
    hitos_orden = list(MAPEO_HITOS.keys())
    try:
        idx_limite = hitos_orden.index(hito_final)
        hitos_a_marcar = hitos_orden[:idx_limite + 1]
        for h in hitos_a_marcar:
            # upsert actúa como el "INSERT OR IGNORE" del código original
            supabase.table("seguimiento").upsert({
                "producto_id": int(p_id), "hito": h, "fecha": fecha_str
            }, on_conflict="producto_id, hito").execute()
    except Exception as e:
        st.error(f"Error en cascada nube: {e}")

# =========================================================
# 3. INTERFAZ Y TRIPLE FILTRO (AUDITORÍA ORIGINAL)
# =========================================================
def mostrar(supervisor_id=None):
    # Estilos CSS Originales (Sticky Header Naranja y Scroll Area)
    st.markdown("""
        <style>
        .header-fixed { position: sticky; top: 0; background: white; z-index: 1000; border-bottom: 2px solid #FF8C00; padding: 10px 0; font-weight: bold; }
        .scroll-area { max-height: 550px; overflow-y: auto; border: 1px solid #eee; padding: 10px; border-radius: 5px; }
        .h-fix { position: sticky; top: 0; background: white; z-index: 10; border-bottom: 2px solid #FF8C00; padding: 5px 0; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)
    
    st.header("📈 Panel de Seguimiento Matricial")
    supabase = conectar()

    # --- FILTRO 1: CABECERA Y SELECCIÓN DE PROYECTO ---
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        bus_p = c1.text_input("🔍 Buscar proyecto o cliente...", key="bus_seg_proy")
        df_p = obtener_proyectos(bus_p, supervisor_id=supervisor_id)
        
        solo_activos = c3.toggle("Ver sólo activos", value=True)
        if solo_activos and not df_p.empty and 'estatus' in df_p.columns:
            df_p = df_p[df_p['estatus'] == 'Activo']

        if df_p.empty:
            st.info("No se encontraron proyectos."); return

        opciones = {f"{r['proyecto_text']} — {r['cliente']}": r['id'] for _, r in df_p.iterrows()}
        sel_p_nom = c2.selectbox("Seleccione Proyecto:", ["Seleccione..."] + list(opciones.keys()))

    if sel_p_nom == "Seleccione...":
        st.info("💡 Por favor, selecciona un proyecto para ver el seguimiento."); return

    id_p = opciones[sel_p_nom]
    p_data = df_p[df_p['id'] == id_p].iloc[0]

    # --- FILTRO 2 Y 3: AGRUPACIÓN Y BÚSQUEDA DOBLE (RECUPERADOS DEL ORIGINAL) ---
    with st.container(border=True):
        d1, d2, d3, d4, d5 = st.columns([2, 1.5, 1, 1, 1.5])
        d1.write(f"**Proy:** {p_data['proyecto_text']}")
        d2.write(f"**Cli:** {p_data['cliente']}")
        
        prod_res = supabase.table("productos").select("*").eq("proyecto_id", id_p).execute()
        prods_base = pd.DataFrame(prod_res.data)
        d3.write(f"**Cant:** {int(prods_base['ctd'].sum()) if not prods_base.empty else 0} Und")
        d4.write(f"**Avance:** {int(p_data['avance'])}%")
        fecha_avance = d5.date_input("📅 Fecha Registro", datetime.now())

    with st.expander("🛠️ Filtros de Producto (Agrupación y Búsqueda Doble)", expanded=False):
        f1, f2, f3, f4 = st.columns([1.2, 1.4, 1.4, 1])
        opciones_filtro = {"Sin grupo": None, "Ubicación": "ubicacion", "Tipo": "tipo"}
        label_agrupar = f1.selectbox("📂 Agrupar por:", list(opciones_filtro.keys()))
        columna_tecnica = opciones_filtro[label_agrupar]
        
        bus_capa1 = f2.text_input("🔍 Filtro Primario:", placeholder="Ej: Cocina...")
        bus_capa2 = f3.text_input("🔍 Refinar:", placeholder="Ej: Bajo...")
        solo_pendientes = f4.toggle("🔴 Solo pendientes", value=False)
        st.info("💡 **Guía:** " + " | ".join([f"{k} {v}" for k, v in LEYENDA_DETALLADA.items()]))

    # --- PROCESAMIENTO DE DATOS ---
    HITOS_LIST = list(MAPEO_HITOS.keys())
    prods = prods_base.copy()
    
    ids_list = prods['id'].tolist() if not prods.empty else []
    segs_res = supabase.table("seguimiento").select("*").in_("producto_id", ids_list).execute()
    
    # SOLUCIÓN AL KEYERROR: Inicializamos con columnas si está vacío
    if not segs_res.data:
        segs = pd.DataFrame(columns=['id', 'producto_id', 'hito', 'fecha', 'observaciones'])
    else:
        segs = pd.DataFrame(segs_res.data)

    # Aplicación de filtros de búsqueda originales
    if not prods.empty:
        if bus_capa1:
            prods = prods[prods['ubicacion'].astype(str).str.contains(bus_capa1, case=False) | prods['tipo'].astype(str).str.contains(bus_capa1, case=False)]
        if bus_capa2:
            prods = prods[prods['ubicacion'].astype(str).str.contains(bus_capa2, case=False) | prods['tipo'].astype(str).str.contains(bus_capa2, case=False)]
        if solo_pendientes:
            prods = prods[prods['id'].apply(lambda x: len(segs[segs['producto_id'] == x]) < 8)]

    # Verificación de candado (Cierres)
    cierre_res = supabase.table("cierres_diarios").select("*").eq("proyecto_id", id_p).eq("fecha", fecha_avance.strftime("%d/%m/%Y")).execute()
    esta_guardado = len(cierre_res.data) > 0
    es_jefe = st.session_state.rol in ['Administrador', 'Gerente']

    # =========================================================
    # 4. PANEL DE ACCIONES (GUARDAR Y EXCEL)
    # =========================================================
    st.divider()
    c_m1, c_m2, c_m3 = st.columns([2, 1.5, 1.5])
    c_m1.write(f"### ⚡ Marcado ({len(prods)})")
    
    with c_m2:
        if st.button("💾 Guardar Avance", use_container_width=True, type="primary"):
            actualizar_avance_real(id_p)
            ahora = datetime.now()
            supabase.table("cierres_diarios").insert({
                "proyecto_id": id_p, "fecha": ahora.strftime("%d/%m/%Y"), 
                "hora": ahora.strftime("%H:%M:%S"), "cerrado_por": st.session_state.get('id_usuario', 0)
            }).execute()
            st.success(f"✅ Guardado {ahora.strftime('%H:%M:%S')}"); st.rerun()

    with c_m3:
        import io
        output = io.BytesIO()
        df_excel = prods.copy()
        for h in HITOS_LIST:
            # Lógica robusta para evitar el KeyError en el Excel
            df_excel[h] = df_excel['id'].apply(lambda x: segs[(segs['producto_id'] == x) & (segs['hito'] == h)]['fecha'].max() if not segs.empty and not segs[(segs['producto_id'] == x) & (segs['hito'] == h)].empty else "")
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_excel.to_excel(writer, index=False, sheet_name='Avance')
        st.download_button("📥 Excel", output.getvalue(), f"Avance_{p_data['proyecto_text']}.xlsx", use_container_width=True)

    # =========================================================
    # 5. MATRIZ CRONOLÓGICA (STICKY HEADER Y RENDERIZADO)
    # =========================================================
    st.markdown('<div class="h-fix">', unsafe_allow_html=True)
    cols_h = st.columns([3] + [0.7]*8 + [2])
    cols_h[0].write("B101 Producto ml") # Título exacto del original
    for i, hito in enumerate(HITOS_LIST):
        with cols_h[i+1]:
            if st.button("✅", key=f"bk_{hito}"):
                for p_id in prods['id'].tolist(): registrar_hitos_cascada(p_id, hito, obtener_fecha_formateada())
                actualizar_avance_real(id_p); st.rerun()
            st.write(MAPEO_HITOS[hito])
    cols_h[-1].write("Observaciones")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="scroll-area">', unsafe_allow_html=True)
    
    if columna_tecnica and not prods.empty:
        for nombre_grupo, items_grupo in prods.groupby(columna_tecnica):
            st.markdown(f"#### 📂 {nombre_grupo}")
            for _, prod in items_grupo.iterrows():
                dibujar_fila(prod, segs, HITOS_LIST, MAPEO_HITOS, supabase, id_p)
    else:
        for _, prod in prods.iterrows():
            dibujar_fila(prod, segs, HITOS_LIST, MAPEO_HITOS, supabase, id_p)

    st.markdown('</div>', unsafe_allow_html=True)

    if esta_guardado and es_jefe:
        if st.button("🔓 Reabrir Reporte", use_container_width=True):
            supabase.table("cierres_diarios").delete().eq("proyecto_id", id_p).eq("fecha", fecha_avance.strftime("%d/%m/%Y")).execute()
            st.rerun()

# =========================================================
# 6. FUNCIÓN DE FILA (FUNCIONALIDAD ORIGINAL INTEGRAL)
# =========================================================
def dibujar_fila(prod, segs, HITOS_LIST, MAPEO_HITOS, supabase, id_p):
    cols = st.columns([3] + [0.7]*8 + [2])
    # Identificación Original en una línea
    cols[0].markdown(f"**{prod['ubicacion']}** {prod['tipo']} `{prod['ml']} ml`", unsafe_allow_html=True)
    
    for i, hito in enumerate(HITOS_LIST):
        key_c = f"c_{prod['id']}_{hito}"
        # Buscamos en el DataFrame segs (ahora seguro contra vacíos)
        seg_match = segs[(segs['producto_id'] == prod['id']) & (segs['hito'] == hito)] if not segs.empty else pd.DataFrame()
        en_db = not seg_match.empty
        fecha_hito = seg_match['fecha'].iloc[0] if en_db else ""

        # Lógica de Bloqueo Original
        tiene_posterior = False
        if i < len(HITOS_LIST) - 1:
            hito_post = HITOS_LIST[i+1]
            tiene_posterior = not segs[(segs['producto_id'] == prod['id']) & (segs['hito'] == hito_post)].empty if not segs.empty else False
        
        bloqueo = (en_db and st.session_state.rol == "Supervisor") or (en_db and tiene_posterior)

        if cols[i+1].checkbox("Ok", key=key_c, value=en_db, label_visibility="collapsed", disabled=bloqueo, help=f"Fecha: {fecha_hito}"):
            if not en_db:
                registrar_hitos_cascada(prod['id'], hito, obtener_fecha_formateada())
                actualizar_avance_real(id_p); st.rerun()
        elif en_db and not tiene_posterior and st.session_state.rol != "Supervisor":
            supabase.table("seguimiento").delete().eq("producto_id", prod['id']).eq("hito", hito).execute()
            actualizar_avance_real(id_p); st.rerun()
    
    # Observaciones vinculadas a la nube
    obs_db = seg_match['observaciones'].iloc[0] if en_db and 'observaciones' in seg_match.columns else ""
    new_obs = cols[-1].text_input("N", value=obs_db, key=f"o_{prod['id']}", label_visibility="collapsed")
    if new_obs != obs_db:
        supabase.table("seguimiento").update({"observaciones": new_obs}).eq("producto_id", prod['id']).eq("hito", hito).execute()
