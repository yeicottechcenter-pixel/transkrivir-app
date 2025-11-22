import streamlit as st
import google.generativeai as genai
import subprocess
import os
import math
import time
import shutil

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="TransKrivir.ai Suite", page_icon="🎙️", layout="wide")

# --- ESTILOS ---
st.markdown("""
    <style>
    .stButton>button {width: 100%; background-color: #FF4B4B; color: white; font-weight: bold;}
    .stDownloadButton>button {background-color: #2E8B57; color: white;}
    </style>
    """, unsafe_allow_html=True)

# --- API KEY ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("⚠️ Falta GOOGLE_API_KEY en los Secrets.")
    st.stop()

# ==========================================
# 💰 BARRA LATERAL
# ==========================================
with st.sidebar:
    st.header("☕ Apoya el proyecto")
    st.success("""
    **¡Invítame un café!**
    * 📱 **Nequi:** 302 323 6538
    * 📱 **Daviplata:** 302 323 6538
    """)
    st.divider()
    st.subheader("📞 Contacto Directo")
    st.markdown("""
    * 💬 **[Clic para WhatsApp](https://wa.me/573023236538)**
    * 📧 yeicottechcenter@gmail.com
    """)
    st.caption(f"Librería v{genai.__version__}")

# ==========================================
# 🛠️ FUNCIONES TÉCNICAS
# ==========================================

def configurar_ffmpeg():
    if shutil.which("ffmpeg"): return "ffmpeg", "ffprobe"
    if os.path.exists("ffmpeg.exe"): return "ffmpeg.exe", "ffprobe.exe"
    return None, None

def obtener_duracion(archivo, ffprobe_path):
    cmd = [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", archivo]
    try: return float(subprocess.check_output(cmd, shell=False).decode().strip())
    except: return 0

def cortar_audio(ffmpeg_path, entrada, inicio, duracion, salida):
    # Filtro anti-ruido (-ar 16000)
    cmd = [ffmpeg_path, "-y", "-i", entrada, "-ss", str(inicio), "-t", str(duracion), 
           "-vn", "-acodec", "libmp3lame", "-ac", "1", "-ar", "16000", "-b:a", "64k", salida]
    subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=False)

def obtener_modelo_seguro():
    """Selecciona el modelo más estable disponible en la cuenta"""
    try:
        modelos = list(genai.list_models())
        nombres = [m.name for m in modelos]
        # Prioridad a versiones estables
        candidatos = ["models/gemini-1.5-flash-002", "models/gemini-1.5-flash-001", "models/gemini-1.5-flash"]
        for c in candidatos:
            if c in nombres: return c
        return "models/gemini-1.5-flash" # Fallback
    except:
        return "models/gemini-1.5-flash"

def generar_documento_extra(modelo, prompt_base, texto_transcrito):
    """Función genérica para crear actas, resúmenes, etc."""
    full_prompt = f"""
    {prompt_base}
    
    BASADO EN LA SIGUIENTE TRANSCRIPCIÓN COMPLETA:
    {texto_transcrito}
    """
    response = modelo.generate_content(full_prompt)
    return response.text

# ==========================================
# 🚀 APP PRINCIPAL
# ==========================================

st.title("🎙️ TransKrivir.ai Suite")
st.markdown("### Transcripción, Actas y Resúmenes Automáticos")

uploaded_file = st.file_uploader("Sube tu archivo (Hasta 2GB)", type=['mp3', 'm4a', 'wav', 'flac'])

# Inicializar estado de sesión para guardar la transcripción si no existe
if 'texto_final' not in st.session_state:
    st.session_state.texto_final = ""

if uploaded_file:
    ext = uploaded_file.name.split('.')[-1].lower()
    nombre_temp = f"audio_temp.{ext}"
    with open(nombre_temp, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    ffmpeg_path, ffprobe_path = configurar_ffmpeg()
    if not ffmpeg_path:
        st.error("❌ Error: Falta FFmpeg.")
        st.stop()

    duracion_seg = obtener_duracion(nombre_temp, ffprobe_path)
    
    if duracion_seg > 0:
        st.success(f"✅ Archivo cargado: {int(duracion_seg/60)} minutos.")
    else:
        duracion_seg = 600

    # --- BOTÓN DE TRANSCRIPCIÓN ---
    if st.button("🚀 INICIAR TRANSCRIPCIÓN"):
        try:
            genai.configure(api_key=api_key)
            nombre_modelo = obtener_modelo_seguro()
            model = genai.GenerativeModel(nombre_modelo, generation_config={"temperature": 0.2})
            
            MINUTOS_BLOQUE = 15
            segundos_bloque = MINUTOS_BLOQUE * 60
            total_partes = math.ceil(duracion_seg / segundos_bloque)
            
            texto_acumulado = ""
            barra = st.progress(0)
            area_texto = st.empty()
            
            for i in range(total_partes):
                inicio = i * segundos_bloque
                min_real = int(inicio / 60)
                nombre_chunk = f"chunk_{i}.mp3"
                
                cortar_audio(ffmpeg_path, nombre_temp, inicio, segundos_bloque, nombre_chunk)
                
                try:
                    archivo_nube = genai.upload_file(path=nombre_chunk)
                    while archivo_nube.state.name == "PROCESSING":
                        time.sleep(1)
                        archivo_nube = genai.get_file(archivo_nube.name)
                    
                    prompt = f"""
                    Transcribe este audio (Min {min_real}).
                    FORMATO: Hablante [MM:SS]: Texto.
                    Ajusta tiempos sumando {min_real} min.
                    Si hay ruido/silencio escribe [RUIDO]. No inventes texto.
                    """
                    
                    response = model.generate_content([prompt, archivo_nube])
                    texto_acumulado += f"\n\n--- MINUTO {min_real} ---\n{response.text}"
                    area_texto.text_area("Transcripción en vivo:", value=texto_acumulado, height=400)
                    
                    genai.delete_file(archivo_nube.name)
                    os.remove(nombre_chunk)
                    time.sleep(2)
                    
                except Exception as e:
                    st.error(f"Error bloque {i}: {e}")
                
                barra.progress((i+1)/total_partes)
            
            # GUARDAMOS EL TEXTO EN SESIÓN PARA USARLO DESPUÉS
            st.session_state.texto_final = texto_acumulado
            st.success("¡Transcripción Finalizada!")
            st.balloons()
            
        except Exception as e:
            st.error(f"Error general: {e}")

    # ==========================================
    # 📝 ZONA DE DOCUMENTOS INTELIGENTES
    # ==========================================
    if st.session_state.texto_final:
        st.divider()
        st.header("🧠 Generación de Documentos")
        st.info("Usa la transcripción generada para crear documentos automáticamente.")
        
        # Opción de descarga de la transcripción base
        st.download_button("📥 Descargar Transcripción Completa", data=st.session_state.texto_final, file_name="transcripcion_completa.txt")

        # Pestañas para las nuevas funciones
        tab1, tab2, tab3 = st.tabs(["📄 Generar Acta", "📊 Generar Resumen", "📋 Informe de Tareas"])
        
        # Configuramos el modelo nuevamente por si acaso
        genai.configure(api_key=api_key)
        nombre_modelo_docs = obtener_modelo_seguro()
        model_docs = genai.GenerativeModel(nombre_modelo_docs)

        with tab1:
            st.write("Crea un acta formal con asistentes, orden del día y conclusiones.")
            if st.button("Generar Acta Formal"):
                with st.spinner("Redactando acta..."):
                    prompt_acta = """
                    Actúa como un secretario experto. Basado en la transcripción, redacta un ACTA FORMAL.
                    Estructura obligatoria:
                    1. ENCABEZADO (Fecha, Hora, Lugar aproximados o por definir).
                    2. ASISTENTES (Identifica los nombres de quienes hablaron).
                    3. ORDEN DEL DÍA (Deduce los temas tratados).
                    4. DESARROLLO (Resumen cronológico de lo discutido).
                    5. COMPROMISOS Y CONCLUSIONES.
                    Usa lenguaje formal y corporativo.
                    """
                    acta = generar_documento_extra(model_docs, prompt_acta, st.session_state.texto_final)
                    st.text_area("Vista previa Acta:", value=acta, height=400)
                    st.download_button("📥 Descargar Acta", data=acta, file_name="Acta_Reunion.txt")

        with tab2:
            st.write("Crea un resumen ejecutivo de los puntos más importantes.")
            if st.button("Generar Resumen"):
                with st.spinner("Resumiendo..."):
                    prompt_resumen = """
                    Actúa como un analista ejecutivo. Haz un RESUMEN EJECUTIVO de la reunión.
                    - Identifica el tema principal.
                    - Lista los 5 puntos más importantes discutidos.
                    - Ignora discusiones triviales o chistes.
                    - Sé directo y conciso.
                    """
                    resumen = generar_documento_extra(model_docs, prompt_resumen, st.session_state.texto_final)
                    st.text_area("Vista previa Resumen:", value=resumen, height=400)
                    st.download_button("📥 Descargar Resumen", data=resumen, file_name="Resumen_Ejecutivo.txt")

        with tab3:
            st.write("Extrae una lista de tareas, responsables y fechas mencionadas.")
            if st.button("Generar Informe de Tareas"):
                with st.spinner("Analizando tareas..."):
                    prompt_tareas = """
                    Extrae exclusivamente los COMPROMISOS, TAREAS Y ACUERDOS.
                    Formato de tabla o lista:
                    - Tarea/Compromiso: [Descripción]
                    - Responsable: [Nombre o Cargo]
                    - Fecha límite (si se mencionó): [Fecha o 'No definida']
                    Si no hay tareas explícitas, indica las conclusiones principales.
                    """
                    informe = generar_documento_extra(model_docs, prompt_tareas, st.session_state.texto_final)
                    st.text_area("Vista previa Informe:", value=informe, height=400)
                    st.download_button("📥 Descargar Informe", data=informe, file_name="Informe_Tareas.txt")
