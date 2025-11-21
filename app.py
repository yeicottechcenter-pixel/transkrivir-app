import streamlit as st
import google.generativeai as genai
import subprocess
import os
import math
import time
import shutil

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="TransKrivir.ai Pro", page_icon="🎙️", layout="wide")

# --- ESTILOS ---
st.markdown("""
    <style>
    .stButton>button {width: 100%; background-color: #FF4B4B; color: white; font-weight: bold;}
    </style>
    """, unsafe_allow_html=True)

# --- API KEY ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("⚠️ Falta GOOGLE_API_KEY en los Secrets.")
    st.stop()

# ==========================================
# 💰 BARRA LATERAL (TU CONTACTO Y APOYO)
# ==========================================
with st.sidebar:
    st.header("☕ Apoya el proyecto")
    st.markdown("Esta herramienta usa IA avanzada para ahorrarte horas de trabajo manual.")
    
    st.success("""
    **¡Invítame un café!**
    
    * 📱 **Nequi:** 302 323 6538
    * 📱 **Daviplata:** 302 323 6538
    """)
    
    st.divider()
    st.subheader("📞 Contacto Directo")
    # Enlace inteligente a WhatsApp
    st.markdown("""
    ¿Necesitas soporte o desarrollo a medida?
    
    * 💬 **[Clic para WhatsApp](https://wa.me/573023236538)**
    * 📧 yeicottechcenter@gmail.com
    """)
    
    st.divider()
    # Info técnica discreta al final
    st.caption(f"Motor IA: Google GenerativeAI v{genai.__version__}")

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
    # Mantenemos el filtro -ar 16000 para evitar el error del "se se se"
    cmd = [ffmpeg_path, "-y", "-i", entrada, "-ss", str(inicio), "-t", str(duracion), 
           "-vn", "-acodec", "libmp3lame", "-ac", "1", "-ar", "16000", "-b:a", "64k", salida]
    subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=False)

def obtener_mejor_modelo():
    # Busca automáticamente el mejor modelo disponible en tu cuenta
    try:
        modelos = list(genai.list_models())
        nombres = [m.name for m in modelos]
        for n in nombres:
            if 'gemini-2.0-flash' in n: return n
        for n in nombres:
            if 'gemini-1.5-flash' in n: return n
        return "models/gemini-1.5-flash"
    except:
        return "models/gemini-1.5-flash"

# ==========================================
# 🚀 APP PRINCIPAL
# ==========================================

st.title("🎙️ TransKrivir.ai Pro")
st.markdown("### Tu Inteligencia Artificial para Juntas y Audiencias")

uploaded_file = st.file_uploader("Sube tu archivo (MP3, M4A, WAV, FLAC - Hasta 2GB)", type=['mp3', 'm4a', 'wav', 'flac'])

if uploaded_file:
    ext = uploaded_file.name.split('.')[-1].lower()
    nombre_temp = f"audio_temp.{ext}"
    with open(nombre_temp, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    ffmpeg_path, ffprobe_path = configurar_ffmpeg()
    if not ffmpeg_path:
        st.error("❌ Error: Falta FFmpeg. Verifica packages.txt")
        st.stop()

    duracion_seg = obtener_duracion(nombre_temp, ffprobe_path)
    
    if duracion_seg > 0:
        st.success(f"✅ Archivo cargado: {int(duracion_seg/60)} minutos.")
    else:
        duracion_seg = 600 # 10 min por defecto si falla lectura

    if st.button("🚀 TRANSCRIBIR AHORA"):
        try:
            genai.configure(api_key=api_key)
            nombre_modelo = obtener_mejor_modelo()
            
            model = genai.GenerativeModel(nombre_modelo, generation_config={"temperature": 0.2})
            
            MINUTOS_BLOQUE = 15
            segundos_bloque = MINUTOS_BLOQUE * 60
            total_partes = math.ceil(duracion_seg / segundos_bloque)
            
            texto_completo = ""
            barra = st.progress(0)
            area_texto = st.empty()
            status = st.empty()

            for i in range(total_partes):
                inicio = i * segundos_bloque
                min_real = int(inicio / 60)
                nombre_chunk = f"chunk_{i}.mp3"
                
                status.info(f"⏳ Procesando parte {i+1} de {total_partes} (Minuto {min_real})...")
                
                cortar_audio(ffmpeg_path, nombre_temp, inicio, segundos_bloque, nombre_chunk)
                
                try:
                    archivo_nube = genai.upload_file(path=nombre_chunk)
                    while archivo_nube.state.name == "PROCESSING":
                        time.sleep(1)
                        archivo_nube = genai.get_file(archivo_nube.name)
                    
                    # Prompt Estricto para formato Hablante + Tiempo
                    prompt = f"""
                    Actúa como un transcriptor profesional.
                    Tu tarea es transcribir este audio que comienza en el minuto {min_real}.
                    
                    INSTRUCCIONES OBLIGATORIAS:
                    1. FORMATO: Usa "Hablante X [MM:SS]: Texto".
                    2. TIEMPO: Ajusta las marcas de tiempo sumando {min_real} minutos al inicio.
                    3. LIMPIEZA: Si hay solo ruido, estática o silencio, escribe [SILENCIO] y continua. NO repitas sílabas.
                    """
                    
                    response = model.generate_content([prompt, archivo_nube])
                    texto_completo += f"\n\n--- BLOQUE MINUTO {min_real} ---\n{response.text}"
                    area_texto.text_area("Transcripción en vivo:", value=texto_completo, height=400)
                    
                    genai.delete_file(archivo_nube.name)
                    os.remove(nombre_chunk)
                    
                except Exception as e:
                    st.error(f"Error en bloque {i}: {e}")
                
                barra.progress((i+1)/total_partes)

            status.success("¡Transcripción Finalizada!")
            st.balloons()
            st.download_button("📥 Descargar Transcripción Completa", data=texto_completo, file_name="transcripcion_final.txt")
            
        except Exception as e:
            st.error(f"Error general: {e}")
