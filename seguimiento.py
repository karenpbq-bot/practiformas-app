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
# 2. LÓGICA DE CASCADA (RESTAURADA Y SEGURA)
# =========================================================
def registrar_hitos_cascada(p_id, hito_final, fecha_str):
    supabase = conectar()
    try:
        idx_limite = HITOS_LIST.index(hito_final)
        hitos_a_marcar = HITOS_LIST[:idx_limite + 1]
        for h in hitos_a_marcar:
            # UPSERT: Preserva si ya existe, inserta si no.
            supabase.table("seguimiento").upsert({
                "producto_id": int(p_id), 
                "hito": h, 
                "fecha": fecha_str
            }, on_conflict="producto_id, hito").execute()
    except Exception as e:
        st.error(f"Error en cascada: {e}")

# =========================================================
# 3. INTERFAZ PRINCIPAL
# =========================================================
def mostrar(supervisor_id=None):
    # Inyección de CSS para Sticky Header y Scroll Area Real
    st.markdown("""
        <style>
        .sticky-top { position: sticky; top: 0; background: white; z-index: 1000; padding: 10px 0; border-bottom: 3px solid #FF8C00; }
        .scroll-area { max-height: 600px; overflow-y: auto; overflow-x: hidden; border: 1px solid #eee; padding: 10px; border-radius: 5px; }
        .metric-box { background-color: #f8f9fa; padding: 10px; border-radius: 5px; text-align: center; border: 1px solid #dee2e6; }
        </style>
    """, unsafe_allow_html=True)
    
    st.header("📈 Panel de Seguimiento Matricial")
    supabase = conectar()

    # --- BLOQUE 1 (PLEGABLE): SELECCIÓN DE PROYECTO ---
    with st.expander("📁 SELECCIÓN DE PROYECTO", expanded=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        bus_p = c1.text_input("🔍 Buscar proyecto por palabra clave...", key="bus_seg_proy")
        df_p = obtener_proyectos(bus_p, supervisor_id=supervisor_id)
        
        solo_activos = c3.toggle("Solo proyectos activos", value=True)
        if solo_activos and not df_p.empty:
            df_p = df_p[df_p['estatus'] == 'Activo']

        if df_p.empty:
            st.info("No hay proyectos."); return

        opciones = {f"{r['proyecto_text']} — {r['cliente']}": r['id'] for _, r in df_p.iterrows()}
        sel_p_nom = c2.selectbox("Elija Proyecto:", ["Seleccione..."] + list(opciones.keys()))

    if sel_p_nom == "Seleccione...":
        st.info("💡 Seleccione un proyecto en el Bloque 1."); return

    id_p = opciones[sel_p_nom]
    p_data = df_p[df_p['id'] == id_p].iloc[0]

    # --- BLOQUE 2 (PLEGABLE): HERRAMIENTAS, PONDERACIÓN E IMPORTACIÓN ---
    with st.expander("🛠️ CONFIGURACIÓN AVANZADA, PONDERACIÓN E IMPORTACIÓN", expanded=False):
        t1, t2, t3 = st.tabs(["📊 Ponderación de Etapas", "🔍 Filtros de Matriz", "📥 Importar/Exportar"])
        
        with t1:
            st.write("⚖️ **Distribución de Esfuerzo por Etapa** (Debe sumar 100%)")
            cols_w = st.columns(4)
            pesos = {}
            default_w = 12.5 # Equitativo
            for i, h in enumerate(HITOS_LIST):
                pesos[h] = cols_w[i % 4].number_input(f"{h} (%)", value=default_w, step=0.5, key=f"w_{h}")
            
            suma_w = sum(pesos.values())
            if suma_w != 100:
                st.warning(f"⚠️ La suma actual es {suma_w}%. Debe ser 100% para cálculos precisos.")

        with t2:
            f1, f2, f3 = st.columns(3)
            opciones_filtro = {"Sin grupo": None, "Ubicación": "ubicacion", "Tipo": "tipo"}
            columna_tecnica = opciones_filtro[f1.selectbox("📂 Agrupar matriz por:", list(opciones_filtro.keys()))]
            bus_capa1 = f2.text_input("🔍 Filtro Primario (Zona/Tipo):")
            bus_capa2 = f3.text_input("🔍 Refinar Búsqueda:")
            
        with t3:
            c_imp, c_exp = st.columns(2)
            archivo_excel = c_imp.file_uploader("📥 Cargar Excel de Avance", type=["xlsx"])
            
            # Lógica de Importación por Atributos (Ubicación, Tipo, ml)
            if archivo_excel:
                df_imp = pd.read_excel(archivo_excel)
                # CÓDIGO NUEVO PARA EL MATCH
                if c_imp.button("🚀 Procesar Importación por Atributos"):
                    prods_db = supabase.table("productos").select("id, ubicacion, tipo, ml").eq("proyecto_id", id_p).execute()
                    prods_df = pd.DataFrame(prods_db.data)
    
                    # CORRECCIÓN 1: Normalizamos todas las columnas del Excel a minúsculas y sin tildes 
                    # para que coincidan con 'ubicacion', 'tipo' y 'ml' sin importar cómo se escribió.
                    df_imp.columns = [str(c).lower().replace('ó','o').replace('á','a').strip() for c in df_imp.columns]
    
                    count = 0
                    for _, row_ex in df_imp.iterrows():
                    # CORRECCIÓN 2: Match robusto. Usamos .str.lower() y .strip() en ambos lados
                    # y un margen de error (abs < 0.05) para los metros lineales.
                    match = prods_df[
                        (prods_df['ubicacion'].astype(str).str.lower().str.strip() == str(row_ex.get('ubicacion','')).lower().strip()) & 
                        (prods_df['tipo'].astype(str).str.lower().str.strip() == str(row_ex.get('tipo','')).lower().strip()) & 
                        (abs(prods_df['ml'] - float(row_ex.get('ml', 0))) < 0.05)
                    ]
        
                    # CORRECCIÓN 3: Identificación dinámica del hito más avanzado en el Excel
                    hito_encontrado = None
                    for h in reversed(HITOS_LIST):
                        # Normalizamos el nombre del hito para buscarlo en el Excel (ej: "diseñado" -> "disenado")
                        col_excel = h.lower().replace('ñ','n').replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u')
                        val_excel = str(row_ex.get(col_excel, row_ex.get(h, ""))).upper()
                        if val_excel not in ["", "NAN", "NO", "NONE"]:
                            hito_encontrado = h
                            break
        
                    if not match.empty and hito_encontrado:
                        registrar_hitos_cascada(match.iloc[0]['id'], hito_encontrado, obtener_fecha_formateada())
                        count += 1
    
                # CORRECCIÓN 4: st.rerun() es vital aquí para que la matriz lea los nuevos datos de la nube
                st.success(f"✅ Se actualizaron {count} productos."); st.rerun()
                            
            # Exportación (Fiel a la vista)
            if c_exp.button("📤 Preparar Excel para Descarga"):
                st.info("Función de exportación lista en el panel principal.")

        st.divider()
        nota_proy = st.text_area("📝 Notas u Observaciones del Proyecto:", value=p_data.get('partida', ''))

    # --- CARGA DE DATOS ---
    res_base = supabase.table("productos").select("*").eq("proyecto_id", id_p).execute()
    prods_all = pd.DataFrame(res_base.data)
    
    ids_list = prods_all['id'].tolist() if not prods_all.empty else []
    segs_res = supabase.table("seguimiento").select("*").in_("producto_id", ids_list).execute()
    segs = pd.DataFrame(segs_res.data) if segs_res.data else pd.DataFrame(columns=['producto_id','hito','fecha','observaciones'])

    # Aplicación de Filtros (Capa 2 y 3)
    prods_filt = prods_all.copy()
    if not prods_filt.empty:
        if bus_capa1: prods_filt = prods_filt[prods_filt['ubicacion'].str.contains(bus_capa1, case=False) | prods_filt['tipo'].str.contains(bus_capa1, case=False)]
        if bus_capa2: prods_filt = prods_filt[prods_filt['ubicacion'].str.contains(bus_capa2, case=False) | prods_filt['tipo'].str.contains(bus_capa2, case=False)]

    # --- CÁLCULO DE AVANCES (TOTAL Y PARCIAL) ---
    def calcular_pct(df_muebles, df_segs, tabla_pesos):
        if df_muebles.empty: return 0.0
        total_puntos_posibles = len(df_muebles) * 100
        puntos_obtenidos = 0
        for _, m in df_muebles.iterrows():
            hitos_hechos = df_segs[df_segs['producto_id'] == m['id']]['hito'].tolist()
            puntos_obtenidos += sum([tabla_pesos.get(h, 0) for h in hitos_hechos])
        return round((puntos_obtenidos / total_puntos_posibles) * 100, 2)

    pct_total = calcular_pct(prods_all, segs, pesos)
    pct_parcial = calcular_pct(prods_filt, segs, pesos)

    # =========================================================
    # 4. ACCIONES GLOBALES E INDICADORES (STICKY)
    # =========================================================
    # Contenedor Sticky que agrupa Acciones, Métricas y Encabezado
    st.markdown('<div class="sticky-top">', unsafe_allow_html=True)
    
    # Fila 1: Acciones
    a1, a2, a3, a4 = st.columns([1.5, 1.2, 1.2, 1.5])
    fecha_reg = a1.date_input("📅 Fecha de Registro:", datetime.now())
    
    if a2.button("💾 GUARDAR AVANCE", use_container_width=True, type="primary"):
        actualizar_avance_real(id_p) # Actualiza el % en tabla proyectos
        ahora = datetime.now()
        supabase.table("cierres_diarios").insert({
            "proyecto_id": id_p, "fecha": ahora.strftime("%d/%m/%Y"), 
            "hora": ahora.strftime("%H:%M:%S"), "cerrado_por": st.session_state.get('id_usuario', 0)
        }).execute()
        # Guardar notas también
        supabase.table("proyectos").update({"partida": nota_proy, "avance": pct_total}).eq("id", id_p).execute()
        st.success("Cierre guardado con éxito."); st.rerun()

    # Botón Exportar
    df_exp = prods_filt.copy()
    for h in HITOS_LIST:
        df_exp[h] = df_exp['id'].apply(lambda x: "OK" if not segs[(segs['producto_id']==x) & (segs['hito']==h)].empty else "")
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_exp.to_excel(writer, index=False)
    a3.download_button("📥 EXPORTAR EXCEL", output.getvalue(), f"Seguimiento_{sel_p_nom}.xlsx", use_container_width=True)

    # Fila 2: Indicadores de Avance
    m1, m2 = st.columns(2)
    m1.markdown(f"<div class='metric-box'><b>% AVANCE TOTAL PROYECTO</b><br><span style='font-size:24px; color:#FF8C00;'>{pct_total}%</span></div>", unsafe_allow_html=True)
    m2.markdown(f"<div class='metric-box'><b>% AVANCE SELECCIÓN (FILTRADO)</b><br><span style='font-size:24px; color:#2E86C1;'>{pct_parcial}%</span></div>", unsafe_allow_html=True)

    st.write("") # Espaciador

    # Fila 3: Encabezado Matricial
    cols_h = st.columns([3] + [0.7]*8 + [2])
    cols_h[0].write("**Producto / Medida**")
    for i, hito in enumerate(HITOS_LIST):
        with cols_h[i+1]:
            if st.button("✅", key=f"btn_all_{hito}"):
                for p_id in prods_filt['id'].tolist(): registrar_hitos_cascada(p_id, hito, fecha_reg.strftime("%d/%m/%Y"))
                st.rerun()
            st.write(MAPEO_HITOS[hito])
    cols_h[-1].write("**Observación**")
    st.markdown('</div>', unsafe_allow_html=True)

    # =========================================================
    # 5. ÁREA DE SCROLL Y FILAS
    # =========================================================
    st.markdown('<div class="scroll-area">', unsafe_allow_html=True)
    
    def render_prods(df_items):
        rol = st.session_state.rol
        for _, prod in df_items.iterrows():
            cols = st.columns([3] + [0.7]*8 + [2])
            cols[0].markdown(f"**{prod['ubicacion']}** {prod['tipo']} `{prod['ml']} ml`", unsafe_allow_html=True)
            
            for i, hito in enumerate(HITOS_LIST):
                seg_match = segs[(segs['producto_id'] == prod['id']) & (segs['hito'] == hito)]
                en_db = not seg_match.empty
                
                # Regla de desmarcado 8 a 1 y Bloqueo Supervisor
                tiene_posterior = False
                if i < len(HITOS_LIST) - 1:
                    tiene_posterior = not segs[(segs['producto_id'] == prod['id']) & (segs['hito'] == HITOS_LIST[i+1])].empty
                
                # Un supervisor solo puede marcar, no desmarcar.
                bloqueo = (en_db and rol == "Supervisor") or (en_db and tiene_posterior)

                if cols[i+1].checkbox("Ok", key=f"c_{prod['id']}_{hito}", value=en_db, label_visibility="collapsed", disabled=bloqueo):
                    if not en_db:
                        registrar_hitos_cascada(prod['id'], hito, fecha_reg.strftime("%d/%m/%Y"))
                        st.rerun()
                elif en_db and not tiene_posterior and rol != "Supervisor":
                    # Borrado solo permitido para Admin/Gerente si no hay posteriores
                    supabase.table("seguimiento").delete().eq("producto_id", prod['id']).eq("hito", hito).execute()
                    st.rerun()
            
            # Notas por producto (Inline)
            obs_db = seg_match['observaciones'].iloc[0] if en_db and 'observaciones' in seg_match.columns else ""
            n_key = f"o_{prod['id']}"
            new_obs = cols[-1].text_input("Nota", value=obs_db, key=n_key, label_visibility="collapsed")
            if new_obs != obs_db:
                # Actualizar observaciones requiere que el hito exista
                if en_db:
                    supabase.table("seguimiento").update({"observaciones": new_obs}).eq("producto_id", prod['id']).eq("hito", HITOS_LIST[0]).execute()

    if columna_tecnica:
        for nombre, grupo in prods_filt.groupby(columna_tecnica):
            st.markdown(f"#### 📂 {nombre}")
            render_prods(grupo)
    else:
        render_prods(prods_filt)
    
    st.markdown('</div>', unsafe_allow_html=True)

