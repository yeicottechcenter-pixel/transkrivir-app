import streamlit as st
import google.generativeai as genai
import subprocess
import os
import math
import time
import shutil

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="TransKrivir.ai Pro", page_icon="🎙️", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .stButton>button {width: 100%; background-color: #FF4B4B; color: white; font-weight: bold;}
    </style>
    """, unsafe_allow_html=True)

# --- API KEY ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("⚠️ Falta la clave 'GOOGLE_API_KEY' en los Secrets de Streamlit.")
    st.stop()

# ==========================================
# 🛠️ FUNCIONES DEL SISTEMA
# ==========================================

def configurar_ffmpeg():
    if shutil.which("ffmpeg"): return "ffmpeg", "ffprobe"
    if os.path.exists("ffmpeg.exe"): return "ffmpeg.exe", "ffprobe.exe"
    return None, None

def obtener_duracion(archivo, ffprobe_path):
    cmd = [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", archivo]
    try:
        return float(subprocess.check_output(cmd, shell=False).decode().strip())
    except:
        return 0

def cortar_audio(ffmpeg_path, entrada, inicio, duracion, salida):
    # Convertir a MP3 ligero, mono (ac 1) para máxima compatibilidad y velocidad
    cmd = [ffmpeg_path, "-y", "-i", entrada, "-ss", str(inicio), "-t", str(duracion), 
           "-vn", "-acodec", "libmp3lame", "-ac", "1", "-q:a", "5", salida]
    subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=False)

# ==========================================
# 🧠 LÓGICA INTELIGENTE DE MODELOS
# ==========================================
def obtener_mejor_modelo():
    """Busca automáticamente qué modelo Flash tiene permitido el usuario"""
    try:
        modelos = list(genai.list_models())
        # 1. Intentamos buscar el 2.5 que vimos en tu cuenta
        for m in modelos:
            if 'gemini-2.5-flash' in m.name:
                return m.name
        # 2. Si no, buscamos el 1.5
        for m in modelos:
            if 'gemini-1.5-flash' in m.name:
                return m.name
        # 3. Si no, cualquiera que diga flash
        for m in modelos:
            if 'flash' in m.name:
                return m.name
        return "models/gemini-1.5-flash" # Fallback por defecto
    except:
        return "models/gemini-1.5-flash"

# ==========================================
# 🚀 APP PRINCIPAL
# ==========================================

st.title("🎙️ TransKrivir.ai Pro")
st.caption("Sube archivos de hasta 2GB (FLAC, MP3, WAV, M4A)")

with st.sidebar:
    st.info(f"Librería v{genai.__version__}")
    
uploaded_file = st.file_uploader("Arrastra tu archivo aquí", type=['mp3', 'm4a', 'wav', 'flac'])

if uploaded_file:
    # 1. GUARDAR
    ext = uploaded_file.name.split('.')[-1].lower()
    nombre_temp = f"audio_temp.{ext}"
    with open(nombre_temp, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # 2. VERIFICAR
    ffmpeg_path, ffprobe_path = configurar_ffmpeg()
    if not ffmpeg_path:
        st.error("❌ Error: Falta FFmpeg.")
        st.stop()

    # 3. DURACIÓN
    duracion_seg = obtener_duracion(nombre_temp, ffprobe_path)
    minutos_total = int(duracion_seg / 60)
    
    if duracion_seg > 0:
        st.success(f"✅ Audio detectado: {minutos_total} min.")
    else:
        st.warning("⚠️ Duración ilegible. Usando modo seguro (10 min).")
        duracion_seg = 600
        minutos_total = 10

    if st.button("🚀 INICIAR TRANSCRIPCIÓN"):
        try:
            genai.configure(api_key=api_key)
            
            # --- AUTO-DETECCIÓN DEL MODELO ---
            with st.spinner("🔍 Detectando el mejor modelo para tu cuenta..."):
                nombre_modelo = obtener_mejor_modelo()
            
            st.toast(f"Usando modelo: {nombre_modelo}")
            model = genai.GenerativeModel(nombre_modelo, generation_config={"temperature": 0})
            
            MINUTOS_BLOQUE = 20
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
                
                status.info(f"⏳ Procesando parte {i+1}/{total_partes} (Min {min_real})...")
                
                # Cortar
                cortar_audio(ffmpeg_path, nombre_temp, inicio, segundos_bloque, nombre_chunk)
                
                try:
                    archivo_nube = genai.upload_file(path=nombre_chunk)
                    
                    while archivo_nube.state.name == "PROCESSING":
                        time.sleep(1)
                        archivo_nube = genai.get_file(archivo_nube.name)
                    
                    if archivo_nube.state.name == "FAILED":
                        raise ValueError("Google rechazó el audio.")

                    prompt = f"Transcribe este audio. Inicia en min {min_real}."
                    response = model.generate_content([prompt, archivo_nube])
                    
                    texto_completo += f"\n\n--- MINUTO {min_real} ---\n{response.text}"
                    area_texto.text_area("Transcripción:", value=texto_completo, height=400)
                    
                    genai.delete_file(archivo_nube.name)
                    os.remove(nombre_chunk)
                    
                except Exception as e:
                    st.error(f"❌ Error bloque {i+1}: {e}")
                
                barra.progress((i + 1) / total_partes)

            status.success("¡Listo!")
            st.download_button("📥 Descargar TXT", data=texto_completo, file_name="transcripcion.txt")
            
        except Exception as e:
            st.error(f"Error: {e}")
