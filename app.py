import streamlit as st
import google.generativeai as genai
import subprocess
import os
import math
import time
import shutil

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="TransKrivir.ai",
    page_icon="🎙️",
    layout="centered"
)

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        background-color: #FF4B4B;
        color: white;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CLAVE DE API ---
api_key = "AIzaSyD0TzF0LwQwGDEZQxyLxyzXlewldgMjrG8" 

# --- FUNCIÓN 1: BUSCAR HERRAMIENTAS (Robustez Nube/Local) ---
def configurar_ffmpeg():
    # 1. Buscamos en el sistema (Para Streamlit Cloud / Linux)
    if shutil.which("ffmpeg"):
        return "ffmpeg", "ffprobe"
    
    # 2. Buscamos en la carpeta local (Para tu Windows)
    if os.path.exists("ffmpeg.exe"):
        return "ffmpeg.exe", "ffprobe.exe"
    
    return None, None

# --- FUNCIÓN 2: OBTENER DURACIÓN (Corregida para Linux) ---
def obtener_duracion(archivo, ffprobe_path):
    cmd = [
        ffprobe_path, 
        "-v", "error", 
        "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", 
        archivo
    ]
    try:
        # IMPORTANTE: shell=False es más seguro y estable en Linux
        salida = subprocess.check_output(cmd, shell=False, stderr=subprocess.STDOUT).decode().strip()
        return float(salida)
    except subprocess.CalledProcessError as e:
        # Si falla, imprimimos el error en la consola de Streamlit para depurar
        print(f"Error FFprobe: {e.output}")
        return 0
    except Exception as e:
        print(f"Error General: {e}")
        return 0

# --- FUNCIÓN 3: CORTAR AUDIO ---
def cortar_audio(ffmpeg_path, entrada, inicio, duracion, salida):
    cmd = [
        ffmpeg_path, "-y", 
        "-i", entrada, 
        "-ss", str(inicio), 
        "-t", str(duracion), 
        "-vn", "-acodec", "libmp3lame", "-q:a", "4", 
        salida
    ]
    # shell=False aquí también
    subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=False)

# --- INTERFAZ PRINCIPAL ---
st.title("🎙️ TransKrivir.ai")
st.markdown("### Tu Inteligencia Artificial para Juntas y Audiencias")

if not api_key:
    st.error("❌ Error crítico: Falta la API Key.")
    st.stop()

uploaded_file = st.file_uploader("Sube tu archivo de audio (MP3, M4A, WAV)", type=['mp3', 'm4a', 'wav'])

if uploaded_file:
    # Guardar archivo temporalmente
    # Usamos un nombre simple sin espacios para evitar problemas en Linux
    nombre_temp = "audio_temp.mp3" 
    with open(nombre_temp, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    ffmpeg_path, ffprobe_path = configurar_ffmpeg()
    
    if not ffmpeg_path:
        st.error("❌ Error: No encuentro FFmpeg. (Si estás en la nube, intenta 'Reboot App').")
        st.stop()

    # Obtener duración
    duracion_seg = obtener_duracion(nombre_temp, ffprobe_path)
    
    if duracion_seg > 0:
        minutos_total = int(duracion_seg / 60)
        st.success(f"✅ Audio analizado: {minutos_total} minutos reales.")
    else:
        st.warning("⚠️ No pude leer la duración exacta. Usaré el modo seguro (10 min).")
        minutos_total = 10 # Fallback

    if st.button("🚀 INICIAR TRANSCRIPCIÓN"):
        genai.configure(api_key=api_key)
        # Usamos Flash 2.0 con temperatura 0 para precisión
        model = genai.GenerativeModel('models/gemini-2.0-flash', generation_config={"temperature": 0.0})
        
        MINUTOS_BLOQUE = 20
        segundos_bloque = MINUTOS_BLOQUE * 60
        total_partes = math.ceil(duracion_seg / segundos_bloque)
        if total_partes == 0: total_partes = 1 # Evitar división por cero
        
        nombre_salida = f"Transcripcion_{uploaded_file.name}.txt"
        texto_completo = ""
        
        barra = st.progress(0)
        estado = st.empty()
        area_texto = st.empty()

        for i in range(total_partes):
            inicio = i * segundos_bloque
            min_real = int(inicio / 60)
            nombre_chunk = f"chunk_{i}.mp3"
            
            estado.info(f"⏳ Procesando bloque {i+1} de {total_partes} (Minuto {min_real})...")
            
            cortar_audio(ffmpeg_path, nombre_temp, inicio, segundos_bloque, nombre_chunk)
            
            try:
                archivo_nube = genai.upload_file(path=nombre_chunk)
                while archivo_nube.state.name == "PROCESSING":
                    time.sleep(1)
                    archivo_nube = genai.get_file(archivo_nube.name)
                
                prompt = f"Transcribe este audio que inicia en el minuto {min_real}. Identifica hablantes. Escribe marcas de tiempo [MM:SS] sumando {min_real} minutos."
                
                response = model.generate_content([prompt, archivo_nube])
                texto_bloque = response.text
                
                texto_completo += f"\n\n--- BLOQUE MIN {min_real} ---\n{texto_bloque}"
                area_texto.text_area("Vista en vivo:", value=texto_completo, height=300)
                
                # Limpieza del bloque
                genai.delete_file(archivo_nube.name)
                os.remove(nombre_chunk)
                
            except Exception as e:
                st.error(f"Error en bloque {i}: {e}")
            
            barra.progress((i + 1) / total_partes)

        estado.success("¡Terminado!")
        st.download_button("📥 Descargar Transcripción", texto_completo, file_name=nombre_salida)
