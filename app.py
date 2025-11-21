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
# 🛠️ FUNCIONES DEL SISTEMA (FFMPEG)
# ==========================================

def configurar_ffmpeg():
    # Busca ffmpeg en el sistema (Linux/Streamlit Cloud) o local (Windows)
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
    # Convierte cualquier formato (FLAC, WAV, M4A) a MP3 ligero para la IA
    # Usamos calidad 5 para balancear velocidad y peso
    cmd = [ffmpeg_path, "-y", "-i", entrada, "-ss", str(inicio), "-t", str(duracion), 
           "-vn", "-acodec", "libmp3lame", "-q:a", "5", salida]
    subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=False)

# ==========================================
# 🚀 APP PRINCIPAL
# ==========================================

st.title("🎙️ TransKrivir.ai Pro")
st.caption("Sube archivos de hasta 2GB (FLAC, MP3, WAV, M4A)")

# Barra lateral con info
with st.sidebar:
    st.info(f"✅ Sistema listo. Librería Google v{genai.__version__}")
    st.write("Si tienes problemas, verifica que tu API Key tenga saldo o permisos.")

# Carga de archivo
uploaded_file = st.file_uploader("Arrastra tu archivo aquí", type=['mp3', 'm4a', 'wav', 'flac'])

if uploaded_file:
    # 1. GUARDAR ARCHIVO TEMPORALMENTE
    # Detectamos la extensión real para manejar FLAC correctamente
    ext = uploaded_file.name.split('.')[-1].lower()
    nombre_temp = f"audio_temp.{ext}"
    
    with open(nombre_temp, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # 2. VERIFICAR HERRAMIENTAS
    ffmpeg_path, ffprobe_path = configurar_ffmpeg()
    if not ffmpeg_path:
        st.error("❌ Error Crítico: No se encontró FFmpeg. Verifica que 'packages.txt' existe en GitHub.")
        st.stop()

    # 3. ANALIZAR DURACIÓN
    duracion_seg = obtener_duracion(nombre_temp, ffprobe_path)
    minutos_total = int(duracion_seg / 60)
    
    if duracion_seg > 0:
        st.success(f"✅ Archivo cargado correctamente: {minutos_total} minutos.")
    else:
        st.warning("⚠️ No se pudo leer la duración exacta. Activando modo seguro (10 min).")
        duracion_seg = 600
        minutos_total = 10

    # 4. BOTÓN DE ACCIÓN
    if st.button("🚀 INICIAR TRANSCRIPCIÓN"):
        try:
            genai.configure(api_key=api_key)
            
            # -------------------------------------------------------
            # 🔧 CONFIGURACIÓN DEL MODELO (CORREGIDO)
            # Usamos el nombre exacto que tu cuenta requiere (con 'models/')
            # -------------------------------------------------------
            nombre_modelo = "models/gemini-1.5-flash"
            
            model = genai.GenerativeModel(nombre_modelo, generation_config={"temperature": 0})
            
            # Configuración de bloques (20 minutos por pedazo)
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
                nombre_chunk = f"chunk_{i}.mp3" # Convertimos todo a MP3 para enviar
                
                status.info(f"⏳ Procesando parte {i+1} de {total_partes} (Minuto {min_real})...")
                
                # A. Cortar y convertir
                cortar_audio(ffmpeg_path, nombre_temp, inicio, segundos_bloque, nombre_chunk)
                
                # B. Enviar a Google Gemini
                try:
                    archivo_nube = genai.upload_file(path=nombre_chunk)
                    
                    # Esperar a que Google procese el audio
                    while archivo_nube.state.name == "PROCESSING":
                        time.sleep(1)
                        archivo_nube = genai.get_file(archivo_nube.name)
                    
                    if archivo_nube.state.name == "FAILED":
                        raise ValueError("Google rechazó el archivo de audio (Error en servidor).")

                    # Prompt optimizado
                    prompt = f"Transcribe este audio fielmente. El audio inicia en el minuto {min_real}. Indica cambios de hablante. No resumas, transcribe todo."
                    
                    response = model.generate_content([prompt, archivo_nube])
                    
                    texto_nuevo = response.text
                    texto_completo += f"\n\n--- MINUTO {min_real} ---\n{texto_nuevo}"
                    area_texto.text_area("Transcripción en vivo:", value=texto_completo, height=400)
                    
                    # Limpieza para ahorrar espacio
                    genai.delete_file(archivo_nube.name)
                    os.remove(nombre_chunk)
                    
                except Exception as e:
                    st.error(f"❌ Error en el bloque {i+1}: {e}")
                    # Si falla, intentamos continuar con el siguiente bloque
                
                barra.progress((i + 1) / total_partes)

            status.success("¡Proceso terminado con éxito!")
            st.balloons()
            
            # Botón de descarga
            st.download_button(
                label="📥 Descargar Transcripción Completa (TXT)", 
                data=texto_completo, 
                file_name="transcripcion_final.txt",
                mime="text/plain"
            )
            
        except Exception as e:
            st.error(f"Ocurrió un error general: {e}")
