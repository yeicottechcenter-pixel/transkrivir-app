import streamlit as st
import google.generativeai as genai
import subprocess
import os
import math
import time
import shutil

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="TransKrivir.ai", page_icon="🎙️", layout="centered")

# --- ESTILOS ---
st.markdown("""<style>.stButton>button {width: 100%; background-color: #FF4B4B; color: white; font-weight: bold;}</style>""", unsafe_allow_html=True)

# --- API KEY ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("⚠️ Falta la GOOGLE_API_KEY en los Secrets.")
    st.stop()

# --- FUNCIONES DE FFmpeg ---
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
    # Convierte cualquier formato (FLAC/WAV) a MP3 ligero para enviar a la IA
    cmd = [ffmpeg_path, "-y", "-i", entrada, "-ss", str(inicio), "-t", str(duracion), 
           "-vn", "-acodec", "libmp3lame", "-q:a", "5", salida]
    subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=False)

# --- INTERFAZ ---
st.title("🎙️ TransKrivir.ai Pro")
st.markdown("### Soporte para FLAC y archivos de hasta 2GB")

uploaded_file = st.file_uploader("Sube tu audio", type=['mp3', 'm4a', 'wav', 'flac'])

if uploaded_file:
    # 1. DETECTAR EXTENSIÓN CORRECTA (CRÍTICO PARA FLAC)
    ext = uploaded_file.name.split('.')[-1].lower()
    nombre_temp = f"audio_temp.{ext}"
    
    # Guardar archivo
    with open(nombre_temp, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    ffmpeg_path, ffprobe_path = configurar_ffmpeg()
    if not ffmpeg_path:
        st.error("❌ No se encontró FFmpeg. Verifica packages.txt")
        st.stop()

    # 2. ANÁLISIS
    duracion_seg = obtener_duracion(nombre_temp, ffprobe_path)
    minutos_total = int(duracion_seg / 60)
    
    if duracion_seg > 0:
        st.success(f"✅ Archivo {ext.upper()} cargado: {minutos_total} minutos.")
    else:
        st.warning("⚠️ No se pudo leer la duración. Usando modo seguro (10 min).")
        duracion_seg = 600

    if st.button("🚀 TRANSCRIBIR"):
        try:
            genai.configure(api_key=api_key)
            # Usamos flash 1.5 por ser más estable para textos largos que el 2.0 experimental
            model = genai.GenerativeModel('models/gemini-1.5-flash', generation_config={"temperature": 0})
            
            MINUTOS_BLOQUE = 20
            segundos_bloque = MINUTOS_BLOQUE * 60
            total_partes = math.ceil(duracion_seg / segundos_bloque)
            
            texto_completo = ""
            barra = st.progress(0)
            area_texto = st.empty()

            for i in range(total_partes):
                inicio = i * segundos_bloque
                min_real = int(inicio / 60)
                nombre_chunk = f"chunk_{i}.mp3" # Siempre enviamos MP3 a la IA
                
                # Cortar y convertir
                cortar_audio(ffmpeg_path, nombre_temp, inicio, segundos_bloque, nombre_chunk)
                
                try:
                    archivo_nube = genai.upload_file(path=nombre_chunk)
                    while archivo_nube.state.name == "PROCESSING":
                        time.sleep(1)
                        archivo_nube = genai.get_file(archivo_nube.name)
                    
                    prompt = f"Transcribe este audio. El audio inicia en el minuto {min_real}. Usa marcas de tiempo relativas a ese inicio. Identifica hablantes."
                    
                    response = model.generate_content([prompt, archivo_nube])
                    texto_completo += f"\n\n-- MINUTO {min_real} --\n{response.text}"
                    area_texto.text_area("Transcripción en vivo:", value=texto_completo, height=300)
                    
                    # Limpieza
                    genai.delete_file(archivo_nube.name)
                    os.remove(nombre_chunk)
                    
                except Exception as e:
                    st.error(f"Error bloque {i}: {e}")
                
                barra.progress((i + 1) / total_partes)

            st.download_button("📥 Descargar Transcripción", data=texto_completo, file_name="transcripcion.txt")
            
        except Exception as e:
            st.error(f"Error general: {e}")
