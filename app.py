import streamlit as st
import google.generativeai as genai
import subprocess
import os
import math
import time
import shutil

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="TransKrivir.ai", page_icon="🎙️", layout="wide")

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
    st.error("⚠️ Falta la clave 'GOOGLE_API_KEY' en los Secrets de Streamlit.")
    st.stop()

# ==========================================
# 🚑 ZONA DE DIAGNÓSTICO (USAR SI FALLA)
# ==========================================
with st.sidebar:
    st.header("🔧 Herramientas")
    st.info(f"Librería Google GenerativeAI v{genai.__version__}")
    
    if st.button("🚑 DIAGNÓSTICO: ¿Qué modelos tengo?"):
        try:
            genai.configure(api_key=api_key)
            st.write("Consultando a Google...")
            modelos = list(genai.list_models())
            nombres = [m.name for m in modelos if 'generateContent' in m.supported_generation_methods]
            st.code(nombres)
            st.success("👆 Estos son los ÚNICOS nombres que tu API Key permite usar.")
        except Exception as e:
            st.error(f"Error de conexión: {e}")

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
    # Convierte FLAC/WAV/M4A a MP3 ligero para la IA
    cmd = [ffmpeg_path, "-y", "-i", entrada, "-ss", str(inicio), "-t", str(duracion), 
           "-vn", "-acodec", "libmp3lame", "-q:a", "5", salida]
    subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=False)

# ==========================================
# 🚀 APP PRINCIPAL
# ==========================================

st.title("🎙️ TransKrivir.ai Pro")
st.caption("Sube archivos de hasta 2GB (FLAC, MP3, WAV, M4A)")

uploaded_file = st.file_uploader("Arrastra tu archivo aquí", type=['mp3', 'm4a', 'wav', 'flac'])

if uploaded_file:
    # 1. GUARDAR ARCHIVO
    ext = uploaded_file.name.split('.')[-1].lower()
    nombre_temp = f"audio_temp.{ext}"
    
    with open(nombre_temp, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # 2. VERIFICAR FFMPEG
    ffmpeg_path, ffprobe_path = configurar_ffmpeg()
    if not ffmpeg_path:
        st.error("❌ Error: No se encontró FFmpeg. Verifica que el archivo 'packages.txt' tenga escrito 'ffmpeg'.")
        st.stop()

    # 3. ANALIZAR DURACIÓN
    duracion_seg = obtener_duracion(nombre_temp, ffprobe_path)
    minutos_total = int(duracion_seg / 60)
    
    if duracion_seg > 0:
        st.success(f"✅ Archivo cargado: {minutos_total} minutos.")
    else:
        st.warning("⚠️ No se pudo leer la duración exacta. Usando modo seguro (10 min).")
        duracion_seg = 600
        minutos_total = 10

    # 4. BOTÓN DE ACCIÓN
    if st.button("🚀 INICIAR TRANSCRIPCIÓN"):
        try:
            genai.configure(api_key=api_key)
            
            # --- SELECCIÓN DE MODELO ---
            # Intentamos usar el nombre más estándar.
            # Si falla, usa el botón de diagnóstico para ver cuál nombre usar.
            nombre_modelo = "gemini-1.5-flash" 
            
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
                
                status.info(f"⏳ Procesando parte {i+1} de {total_partes} (Minuto {min_real})...")
                
                # CORTAR
                cortar_audio(ffmpeg_path, nombre_temp, inicio, segundos_bloque, nombre_chunk)
                
                # ENVIAR A IA
                try:
                    archivo_nube = genai.upload_file(path=nombre_chunk)
                    
                    # Esperar procesamiento
                    while archivo_nube.state.name == "PROCESSING":
                        time.sleep(1)
                        archivo_nube = genai.get_file(archivo_nube.name)
                    
                    if archivo_nube.state.name == "FAILED":
                        raise ValueError("Google rechazó el archivo de audio.")

                    prompt = f"Transcribe este audio fielmente. El audio inicia en el minuto {min_real}. Indica cambio de hablante."
                    
                    response = model.generate_content([prompt, archivo_nube])
                    
                    texto_nuevo = response.text
                    texto_completo += f"\n\n--- MINUTO {min_real} ---\n{texto_nuevo}"
                    area_texto.text_area("Transcripción en vivo:", value=texto_completo, height=400)
                    
                    # Limpieza
                    genai.delete_file(archivo_nube.name)
                    os.remove(nombre_chunk)
                    
                except Exception as e:
                    st.error(f"❌ Error en bloque {i}: {e}")
                    st.error("Si el error dice '404 Not Found', usa el botón de DIAGNÓSTICO en la barra lateral.")
                
                barra.progress((i + 1) / total_partes)

            status.success("¡Proceso terminado!")
            st.download_button("📥 Descargar Transcripción Completa", data=texto_completo, file_name="transcripcion_final.txt")
            
        except Exception as e:
            st.error(f"Error general: {e}")
