mport streamlit as st
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
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SEGURIDAD: RECUPERAR CLAVE DE LA CAJA FUERTE (SECRETS) ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("⚠️ Error: No se encontró la clave 'GOOGLE_API_KEY' en los Secrets de Streamlit.")
    st.stop()

# --- FUNCIÓN 1: BUSCAR HERRAMIENTAS (Robustez Nube/Local) ---
def configurar_ffmpeg():
    if shutil.which("ffmpeg"):
        return "ffmpeg", "ffprobe"
    if os.path.exists("ffmpeg.exe"):
        return "ffmpeg.exe", "ffprobe.exe"
    return None, None

# --- FUNCIÓN 2: OBTENER DURACIÓN ---
def obtener_duracion(archivo, ffprobe_path):
    cmd = [
        ffprobe_path, 
        "-v", "error", 
        "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", 
        archivo
    ]
    try:
        salida = subprocess.check_output(cmd, shell=False, stderr=subprocess.STDOUT).decode().strip()
        return float(salida)
    except Exception as e:
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
    subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=False)

# --- INTERFAZ PRINCIPAL ---
st.title("🎙️ TransKrivir.ai")
st.markdown("### Tu Inteligencia Artificial para Juntas y Audiencias")

# --- BARRA LATERAL: MONETIZACIÓN Y CONTACTO ---
with st.sidebar:
    st.header("💰 Apoya este Proyecto")
    st.info("Esta herramienta usa IA avanzada para ahorrarte horas de trabajo.")
    
    st.markdown("### ¿Te fue útil? ¡Apóyame! ☕")
    st.markdown("""
    Puedes donar a:
    * 🟣 **Nequi:** `302 323 6538`
    * 🔴 **Daviplata:** `302 323 6538`
    """)
    
    st.divider()
    st.write("📧 **Contacto para empresas:**")
    st.code("yeicottechcenter@gmail.com")

# --- SUBIDA DE ARCHIVO (Soporte FLAC incluido) ---
uploaded_file = st.file_uploader("Sube tu archivo de audio (MP3, M4A, WAV, FLAC)", type=['mp3', 'm4a', 'wav', 'flac'])

if uploaded_file:
    # Guardar archivo temporalmente
    ext = uploaded_file.name.split('.')[-1]
    nombre_temp = f"audio_temp.{ext}"
    
    with open(nombre_temp, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # Logs
    print(f"👀 NUEVO CLIENTE: Subió '{uploaded_file.name}' ({uploaded_file.size} bytes)")

    ffmpeg_path, ffprobe_path = configurar_ffmpeg()
    
    if not ffmpeg_path:
        st.error("❌ Error: No encuentro FFmpeg. (Si estás en la nube, intenta 'Reboot App').")
        st.stop()

    duracion_seg = obtener_duracion(nombre_temp, ffprobe_path)
    
    if duracion_seg > 0:
        minutos_total = int(duracion_seg / 60)
        st.success(f"✅ Audio analizado: {minutos_total} minutos reales.")
    else:
        st.warning("⚠️ No pude leer la duración exacta. Usaré el modo seguro (10 min).")
        minutos_total = 10 

    if st.button("🚀 INICIAR TRANSCRIPCIÓN"):
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('models/gemini-2.0-flash', generation_config={"temperature": 0.0})
            
            MINUTOS_BLOQUE = 20
            segundos_bloque = MINUTOS_BLOQUE * 60
            total_partes = math.ceil(duracion_seg / segundos_bloque)
            if total_partes == 0: total_partes = 1 
            
            nombre_salida = f"Transcripcion_{uploaded_file.name}.txt"
            texto_completo = f"--- TRANSCRIPCIÓN: {uploaded_file.name} ---\nDuración: {minutos_total} min\n\n"
            
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
                    
                    genai.delete_file(archivo_nube.name)
                    os.remove(nombre_chunk)
                    
                except Exception as e:
                    st.error(f"Error en bloque {i}: {e}")
                
                barra.progress((i + 1) / total_partes)

            estado.success("¡Terminado! 🎉")
            st.balloons() 
            
            st.download_button(
                label="📥 Descargar Transcripción Completa", 
                data=texto_completo, 
                file_name=nombre_salida,
                mime="text/plain"
            )
            
        except Exception as e:
            st.error(f"Ocurrió un error general: {e}")
