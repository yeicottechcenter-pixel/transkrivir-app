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

# --- ESTILOS CSS (Para que se vea bonita) ---
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        background-color: #FF4B4B;
        color: white;
        font-weight: bold;
    }
    .success-box {
        padding: 15px;
        background-color: #D4EDDA;
        color: #155724;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIÓN PARA BUSCAR HERRAMIENTAS ---
def configurar_ffmpeg():
    cwd = os.getcwd()
    ffmpeg_exe = os.path.join(cwd, "ffmpeg.exe")
    ffprobe_exe = os.path.join(cwd, "ffprobe.exe")
    
    if os.path.exists(ffmpeg_exe) and os.path.exists(ffprobe_exe):
        return ffmpeg_exe, ffprobe_exe
    else:
        return None, None

# --- FUNCIÓN: OBTENER DURACIÓN ---
def obtener_duracion(archivo, ffprobe_path):
    cmd = [
        ffprobe_path, "-v", "error", "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", archivo
    ]
    try:
        salida = subprocess.check_output(cmd, shell=True).decode().strip()
        return float(salida)
    except:
        return 0

# --- FUNCIÓN: CORTAR AUDIO ---
def cortar_audio(ffmpeg_path, entrada, inicio, duracion, salida):
    cmd = [
        ffmpeg_path, "-y", "-i", entrada, "-ss", str(inicio), 
        "-t", str(duracion), "-vn", "-acodec", "libmp3lame", "-q:a", "4", salida
    ]
    subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=True)

# --- INTERFAZ PRINCIPAL ---
st.title("🎙️ TransKrivir.ai")
st.markdown("### Tu Inteligencia Artificial para Juntas y Audiencias")
st.info("Sube audios largos (3+ horas). El sistema los cortará y procesará automáticamente.")

# 1. CAMPO PARA LA API KEY (Para que sea seguro)
api_key = st.text_input("🔑 Ingresa tu Google API Key:", type="password", placeholder="AIzaSyD...")

# 2. SUBIR ARCHIVO
uploaded_file = st.file_uploader("Sube tu archivo de audio (MP3, M4A, WAV)", type=['mp3', 'm4a', 'wav'])

if uploaded_file and api_key:
    # Guardar archivo temporalmente
    nombre_temp = "audio_temp_subido.mp3"
    with open(nombre_temp, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    ffmpeg_path, ffprobe_path = configurar_ffmpeg()
    
    if not ffmpeg_path:
        st.error("❌ Error: No encuentro ffmpeg.exe en la carpeta del proyecto.")
        st.stop()

    # Obtener duración
    duracion_seg = obtener_duracion(nombre_temp, ffprobe_path)
    minutos_total = int(duracion_seg / 60)
    
    st.success(f"✅ Audio cargado: {minutos_total} minutos detectados.")
    
    # Botón de inicio
    if st.button("🚀 INICIAR TRANSCRIPCIÓN INTELIGENTE"):
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('models/gemini-2.0-flash', generation_config={"temperature": 0.0})
        
        # Configuración de bloques
        MINUTOS_BLOQUE = 20
        segundos_bloque = MINUTOS_BLOQUE * 60
        total_partes = math.ceil(duracion_seg / segundos_bloque)
        
        # Archivo de salida final
        nombre_salida = "Transcripcion_Completa.txt"
        with open(nombre_salida, "w", encoding="utf-8") as f:
            f.write(f"--- TRANSCRIPCIÓN: {uploaded_file.name} ---\n\n")

        # Barra de progreso
        barra_progreso = st.progress(0)
        estado_texto = st.empty()
        area_texto = st.empty()
        texto_acumulado = ""

        for i in range(total_partes):
            inicio = i * segundos_bloque
            min_real = int(inicio / 60)
            nombre_chunk = f"temp_parte_{i}.mp3"
            
            # Actualizar estado
            estado_texto.markdown(f"**⏳ Procesando Parte {i+1}/{total_partes} (Minuto {min_real})...**")
            
            # 1. CORTAR
            cortar_audio(ffmpeg_path, nombre_temp, inicio, segundos_bloque, nombre_chunk)
            
            # 2. SUBIR Y TRANSCRIBIR
            try:
                archivo_nube = genai.upload_file(path=nombre_chunk)
                
                # Esperar a que esté activo
                while archivo_nube.state.name == "PROCESSING":
                    time.sleep(2)
                    archivo_nube = genai.get_file(archivo_nube.name)

                prompt = f"""
                Eres un estenógrafo experto.
                Esta es la parte {i+1} de una reunión que inicia en el minuto {min_real}.
                Transcribe palabra por palabra. Identifica hablantes.
                En las marcas de tiempo [MM:SS], suma {min_real} minutos al tiempo real.
                """
                
                response = model.generate_content([prompt, archivo_nube])
                texto_bloque = response.text
                
                # Guardar
                with open(nombre_salida, "a", encoding="utf-8") as f:
                    f.write(f"\n--- BLOQUE MINUTO {min_real} ---\n")
                    f.write(texto_bloque + "\n")
                
                texto_acumulado += f"\n\n--- BLOQUE {min_real} ---\n" + texto_bloque
                area_texto.text_area("Vista Previa (En vivo):", value=texto_acumulado, height=300)

                # Limpieza
                try:
                    genai.delete_file(archivo_nube.name)
                    os.remove(nombre_chunk)
                except:
                    pass
                
            except Exception as e:
                st.error(f"Error en el bloque {i+1}: {e}")

            # Actualizar barra
            barra_progreso.progress((i + 1) / total_partes)

        estado_texto.success("🎉 ¡TRANSCRIPCIÓN FINALIZADA!")
        
        # BOTÓN DE DESCARGA
        with open(nombre_salida, "r", encoding="utf-8") as f:
            st.download_button(
                label="📥 DESCARGAR TRANSCRIPCIÓN COMPLETA",
                data=f,
                file_name=f"Transcripcion_{uploaded_file.name}.txt",
                mime="text/plain"
            )
        
        # Limpiar archivo original temporal
        os.remove(nombre_temp)

elif not api_key:
    st.warning("⚠️ Por favor ingresa tu API Key para comenzar.")