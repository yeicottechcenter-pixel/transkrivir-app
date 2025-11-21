import streamlit as st
import google.generativeai as genai
import subprocess
import os
import math
import time
import shutil

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="TransKrivir.ai", page_icon="🎙️")

# --- DIAGNÓSTICO (EL CHIVATO) ---
# Esto nos dirá si Streamlit actualizó o sigue con la vieja
ver = genai.__version__
st.sidebar.info(f"Versión Librería Google: {ver}")
if ver < "0.8.3":
    st.error("⚠️ ALERTA: Streamlit está usando una versión vieja. BORRA la app en el panel y créala de nuevo.")

try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("Falta la API Key.")
    st.stop()

# --- FUNCIONES FFMPEG ---
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
    cmd = [ffmpeg_path, "-y", "-i", entrada, "-ss", str(inicio), "-t", str(duracion), 
           "-vn", "-acodec", "libmp3lame", "-q:a", "5", salida]
    subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=False)

# --- INTERFAZ ---
st.title("🎙️ TransKrivir.ai")

uploaded_file = st.file_uploader("Sube audio", type=['mp3', 'm4a', 'wav', 'flac'])

if uploaded_file:
    ext = uploaded_file.name.split('.')[-1].lower()
    nombre_temp = f"audio_temp.{ext}"
    with open(nombre_temp, "wb") as f:
        f.write(uploaded_file.getbuffer())

    ffmpeg_path, ffprobe_path = configurar_ffmpeg()
    if not ffmpeg_path:
        st.error("No se encontró FFmpeg.")
        st.stop()

    duracion_seg = obtener_duracion(nombre_temp, ffprobe_path)
    st.success(f"Audio cargado: {int(duracion_seg/60)} min.")

    if st.button("🚀 TRANSCRIBIR"):
        try:
            genai.configure(api_key=api_key)
            
            # INTENTO DE CONEXIÓN ROBUSTA
            # Usamos 'gemini-1.5-flash' a secas, sin 'models/'
            model = genai.GenerativeModel('gemini-1.5-flash', generation_config={"temperature": 0})
            
            MINUTOS_BLOQUE = 20
            segundos_bloque = MINUTOS_BLOQUE * 60
            total_partes = math.ceil(duracion_seg / segundos_bloque)
            
            texto_completo = ""
            area_texto = st.empty()
            barra = st.progress(0)

            for i in range(total_partes):
                inicio = i * segundos_bloque
                nombre_chunk = f"chunk_{i}.mp3"
                
                cortar_audio(ffmpeg_path, nombre_temp, inicio, segundos_bloque, nombre_chunk)
                
                try:
                    archivo_nube = genai.upload_file(path=nombre_chunk)
                    while archivo_nube.state.name == "PROCESSING":
                        time.sleep(1)
                        archivo_nube = genai.get_file(archivo_nube.name)
                    
                    prompt = f"Transcribe este audio."
                    response = model.generate_content([prompt, archivo_nube])
                    
                    texto_completo += f"\n\n-- PARTE {i+1} --\n{response.text}"
                    area_texto.text_area("Resultado:", value=texto_completo, height=300)
                    
                    genai.delete_file(archivo_nube.name)
                    os.remove(nombre_chunk)
                    
                except Exception as e:
                    st.error(f"Error bloque {i}: {e}")
                
                barra.progress((i+1)/total_partes)
                
        except Exception as e:
            st.error(f"Error crítico: {e}")
