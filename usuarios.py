import streamlit as st
import pandas as pd # Importante para la pestaña de Lista
from base_datos import conectar

def mostrar():
    st.header("👤 Gestión de Usuarios y Equipo")
    
    tab1, tab2 = st.tabs(["➕ Crear Usuario", "👥 Lista de Equipo"])
    
    with tab1:
        with st.form("nuevo_usuario", clear_on_submit=True):
            st.subheader("Datos del Colaborador")
            u_real = st.text_input("Nombre Completo (Ej: Juan Pérez)")
            u_nombre = st.text_input("Nombre de Usuario (Login)")
            u_pass = st.text_input("Contraseña Temporal", type="password")
            
            # Ajustamos los roles a los 3 niveles definidos anteriormente
            u_rol = st.selectbox("Rol y Permisos", [
                "Supervisor", 
                "Gerente", 
                "Administrador"
            ], help="Supervisor: Solo ve sus proyectos asignados. Gerente: Ve todo pero no borra. Admin: Control total.")
            
            if st.form_submit_button("Registrar en el Sistema"):
                if u_nombre and u_pass and u_real:
                    try:
                        with conectar() as conn:
                            conn.execute(
                                "INSERT INTO usuarios (nombre_usuario, contrasena, rol, nombre_real) VALUES (?,?,?,?)",
                                (u_nombre, u_pass, u_rol, u_real)
                            )
                        st.success(f"✅ ¡Éxito! {u_real} ha sido registrado como {u_rol}.")
                    except Exception as e:
                        st.error("Error: El nombre de usuario ya existe o hubo un problema con la base de datos.")
                else:
                    st.warning("Por favor, complete todos los campos.")

    with tab2:
        st.subheader("Colaboradores con acceso")
        try:
            # Consultamos los usuarios para ver quiénes tienen acceso
            df_u = pd.read_sql_query("SELECT nombre_real as 'Nombre', nombre_usuario as 'Usuario', rol as 'Rol' FROM usuarios", conectar())
            if not df_u.empty:
                st.dataframe(df_u, use_container_width=True, hide_index=True)
            else:
                st.info("No hay otros usuarios registrados.")
        except Exception as e:
            st.error(f"Error al cargar la lista: {e}")

    # Opción adicional para el Administrador
    if st.session_state.rol == "Administrador":
        with st.expander("🔐 Nota de Seguridad"):
            st.info("Como Administrador, usted es el único que puede ver esta pestaña y crear nuevos accesos. Asegúrese de asignar correctamente el rol de 'Supervisor' para que el filtrado de proyectos funcione.")
            