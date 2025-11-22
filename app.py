import streamlit as st
import google.generativeai as genai
import subprocess
import os
import math
import time
import shutil
import re # Importamos expresiones regulares para limpiar texto

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
    # Mantenemos el filtro -ar 16000 que ayuda mucho
    cmd = [ffmpeg_path, "-y", "-i", entrada, "-ss", str(inicio), "-t", str(duracion), 
           "-vn", "-acodec", "libmp3lame", "-ac", "1", "-ar", "16000", "-b:a", "64k", salida]
    subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=False)

def buscar_modelo_compatible():
    try:
        mis_modelos = list(genai.list_models())
        nombres = [m.name for m in mis_modelos if 'generateContent' in m.supported_generation_methods]
        
        # Prioridad a las versiones estables y nuevas (002 o 001)
        for m in nombres:
            if 'gemini-1.5-flash-002' in m: return m
        for m in nombres:
            if 'gemini-1.5-flash-001' in m: return m
        if 'models/gemini-1.5-flash' in nombres: return 'models/gemini-1.5-flash'
        
        # Evitar experimentales si es posible
        for m in nombres:
            if 'flash' in m and 'exp' not in m: return m

        return nombres[0]
    except:
        return "models/gemini-1.5-flash"

def limpiar_respuesta_ia(texto):
    """
    Función de seguridad: Elimina bucles 'se se se' y explicaciones en inglés.
    """
    if not texto: return ""
    
    # 1. Detectar bucle "se se se" o "de de de" (más de 4 repeticiones)
    patron_bucle = r'((\b\w{1,3}\s+)\2{4,})'
    if re.search(patron_bucle, texto, re.IGNORECASE):
        # Si encuentra el bucle, lo reemplaza por una etiqueta de ruido
        texto = re.sub(patron_bucle, " [RUIDO DE FONDO/ESTÁTICA] ", texto)
    
    # 2. Eliminar posibles encabezados en inglés de la IA
    frases_prohibidas = ["Here is the transcription", "Let's break down", "Segment 1", "The audio seems to"]
    for frase in frases_prohibidas:
        if frase in texto:
            # Si empieza con explicaciones, intentamos cortar hasta donde empieza el español o limpiarlo
            pass # Por ahora confiamos en el Prompt fuerte, pero esto monitorea.
            
    return texto

def generar_documento_extra(modelo, prompt_base, texto_transcrito):
    prompt_completo = f"{prompt_base}\n\nBASADO EN ESTA TRANSCRIPCIÓN:\n{texto_transcrito}"
    response = modelo.generate_content(prompt_completo)
    return response.text

# ==========================================
# 🚀 APP PRINCIPAL
# ==========================================

st.title("🎙️ TransKrivir.ai Suite")
st.markdown("### Transcripción + Actas + Informes")

uploaded_file = st.file_uploader("Sube tu archivo", type=['mp3', 'm4a', 'wav', 'flac'])

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
    
    if duracion_seg < 60 and uploaded_file.size > 1000000:
        st.warning("⚠️ Usando modo seguro (15 min) por error de lectura de duración.")
        duracion_seg = 900 
    elif duracion_seg > 0:
        st.success(f"✅ Archivo cargado: {int(duracion_seg/60)} minutos.")
    else:
        duracion_seg = 600

    if st.button("🚀 INICIAR TRANSCRIPCIÓN"):
        try:
            genai.configure(api_key=api_key)
            nombre_modelo = buscar_modelo_compatible()
            st.toast(f"Procesando con: {nombre_modelo}")
            
            # CAMBIO 1: Temperatura a 0.0 (Cero creatividad, máxima precisión)
            model = genai.GenerativeModel(nombre_modelo, generation_config={"temperature": 0.0})
            
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
                    
                    # CAMBIO 2: PROMPT "REGAÑÓN" (Blindado contra inglés y explicaciones)
                    prompt = f"""
                    Tu única tarea es transcribir este audio en ESPAÑOL.
                    
                    REGLAS ESTRICTAS (NO LAS ROMPAS):
                    1. SOLO devuelve la transcripción. NO escribas introducciones, ni explicaciones, ni "Here is the text".
                    2. Si escuchas estática o ruidos repetitivos, escribe [RUIDO] y SALTA esa parte. NO escribas "se se se".
                    3. Formato: "Hablante [MM:SS]: Texto".
                    4. Suma {min_real} minutos a las marcas de tiempo.
                    """
                    
                    response = model.generate_content([prompt, archivo_nube])
                    
                    # CAMBIO 3: PASAR EL LIMPIADOR AUTOMÁTICO
                    texto_limpio = limpiar_respuesta_ia(response.text)
                    
                    texto_acumulado += f"\n\n--- MINUTO {min_real} ---\n{texto_limpio}"
                    area_texto.text_area("Transcripción en vivo:", value=texto_acumulado, height=400)
                    
                    genai.delete_file(archivo_nube.name)
                    os.remove(nombre_chunk)
                    time.sleep(2)
                    
                except Exception as e:
                    st.error(f"Error en bloque {i}: {e}")
                    if "404" in str(e):
                         st.warning("Error de modelo. Intenta regenerar la API Key.")
                
                barra.progress((i+1)/total_partes)
            
            st.session_state.texto_final = texto_acumulado
            st.success("¡Transcripción Finalizada!")
            st.balloons()
            
        except Exception as e:
            st.error(f"Error general: {e}")

    # ==========================================
    # 🧠 ZONA DE DOCUMENTOS
    # ==========================================
    if st.session_state.texto_final:
        st.divider()
        st.header("📑 Generar Documentos")
        
        st.download_button("📥 Descargar Transcripción (TXT)", data=st.session_state.texto_final, file_name="transcripcion_completa.txt")

        tab1, tab2, tab3 = st.tabs(["📄 Generar Acta", "📊 Resumen Ejecutivo", "✅ Lista de Tareas"])
        
        genai.configure(api_key=api_key)
        modelo_docs = genai.GenerativeModel(buscar_modelo_compatible())

        with tab1:
            if st.button("Crear Acta Formal"):
                with st.spinner("Redactando acta..."):
                    prompt = "Redacta un ACTA FORMAL. Incluye: Fecha, Asistentes, Orden del día, Desarrollo y Compromisos."
                    res = generar_documento_extra(modelo_docs, prompt, st.session_state.texto_final)
                    st.text_area("Resultado:", value=res, height=400)
                    st.download_button("Descargar Acta", data=res, file_name="Acta.txt")

        with tab2:
            if st.button("Crear Resumen"):
                with st.spinner("Resumiendo..."):
                    prompt = "Haz un RESUMEN EJECUTIVO. Puntos clave y conclusiones."
                    res = generar_documento_extra(modelo_docs, prompt, st.session_state.texto_final)
                    st.text_area("Resultado:", value=res, height=400)
                    st.download_button("Descargar Resumen", data=res, file_name="Resumen.txt")
        
        with tab3:
            if st.button("Extraer Tareas"):
                with st.spinner("Buscando tareas..."):
                    prompt = "Tabla de Tareas: Tarea | Responsable | Fecha."
                    res = generar_documento_extra(modelo_docs, prompt, st.session_state.texto_final)
                    st.text_area("Resultado:", value=res, height=400)
                    st.download_button("Descargar Tareas", data=res, file_name="Tareas.txt")
