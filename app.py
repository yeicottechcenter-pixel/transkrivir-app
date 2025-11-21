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
    # Filtro anti-ruido (-ar 16000) activado
    cmd = [ffmpeg_path, "-y", "-i", entrada, "-ss", str(inicio), "-t", str(duracion), 
           "-vn", "-acodec", "libmp3lame", "-ac", "1", "-ar", "16000", "-b:a", "64k", salida]
    subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=False)

def obtener_modelo_seguro():
    """
    Busca el modelo exacto evitando errores 404 (nombre) y 429 (cuota).
    """
    try:
        modelos_disponibles = list(genai.list_models())
        nombres = [m.name for m in modelos_disponibles]
        
        # LISTA DE PRIORIDAD (Del más estable al menos estable)
        # Buscamos las versiones numeradas que NO fallan con 404
        candidatos = [
            "models/gemini-1.5-flash-002", # Versión estable nueva
            "models/gemini-1.5-flash-001", # Versión estable clásica
            "models/gemini-1.5-flash",     # Alias genérico
            "models/gemini-1.5-flash-8b",  # Versión ligera
        ]
        
        for candidato in candidatos:
            if candidato in nombres:
                return candidato
        
        # Si no encuentra ninguno de los ideales, busca cualquiera que diga "flash"
        # pero que NO sea experimental ("exp") para evitar el error de cuota
        for n in nombres:
            if "flash" in n and "exp" not in n and "preview" not in n:
                return n
                
        # Último recurso: El experimental (riesgo de error 429 pero mejor que nada)
        return "models/gemini-1.5-flash"
        
    except Exception as e:
        return "models/gemini-1.5-flash"

# ==========================================
# 🚀 APP PRINCIPAL
# ==========================================

st.title("🎙️ TransKrivir.ai Pro")

uploaded_file = st.file_uploader("Sube tu archivo (Hasta 2GB)", type=['mp3', 'm4a', 'wav', 'flac'])

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
    
    if duracion_seg > 0:
        st.success(f"✅ Archivo cargado: {int(duracion_seg/60)} minutos.")
    else:
        duracion_seg = 600

    if st.button("🚀 TRANSCRIBIR AHORA"):
        try:
            genai.configure(api_key=api_key)
            
            # 1. SELECCIÓN INTELIGENTE DEL MODELO
            nombre_modelo = obtener_modelo_seguro()
            st.toast(f"Conectado a: {nombre_modelo}") # Te avisará cuál eligió
            
            model = genai.GenerativeModel(nombre_modelo, generation_config={"temperature": 0.2})
            
            MINUTOS_BLOQUE = 15
            segundos_bloque = MINUTOS_BLOQUE * 60
            total_partes = math.ceil(duracion_seg / segundos_bloque)
            
            texto_completo = ""
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
                    
                    prompt = f"""
                    Transcribe este audio (Minuto {min_real}).
                    FORMATO: Hablante [MM:SS]: Texto.
                    Ajusta tiempos sumando {min_real} min.
                    Si hay ruido/silencio escribe [RUIDO]. No inventes texto.
                    """
                    
                    response = model.generate_content([prompt, archivo_nube])
                    texto_completo += f"\n\n--- MINUTO {min_real} ---\n{response.text}"
                    area_texto.text_area("Transcripción:", value=texto_completo, height=400)
                    
                    genai.delete_file(archivo_nube.name)
                    os.remove(nombre_chunk)
                    
                    # Pausa de seguridad anti-bloqueo
                    time.sleep(2)
                    
                except Exception as e:
                    st.error(f"Error bloque {i}: {e}")
                    # Si falla, mostrar qué modelos ve la cuenta para diagnosticar
                    if "404" in str(e):
                        mis_modelos = [m.name for m in genai.list_models()]
                        st.warning(f"Tu cuenta solo ve estos modelos: {mis_modelos}")
                
                barra.progress((i+1)/total_partes)

            st.success("¡Listo!")
            st.balloons()
            st.download_button("📥 Descargar TXT", data=texto_completo, file_name="transcripcion.txt")
            
        except Exception as e:
            st.error(f"Error: {e}")
