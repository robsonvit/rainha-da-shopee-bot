#!/usr/bin/env python3
"""
Rainha da Shopee → Facebook Auto-Poster Bot
Versão FINAL ABSOLUTA - Noticiário Profissional
Baseado no Bot Jornal Vanguarda — adaptado para a página Rainha da Shopee
"""

import os
import json
import time
import datetime
import logging
import hashlib
import textwrap
import requests
import random
import re
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from requests.adapters import HTTPAdapter
import traceback
import subprocess
import glob
from dotenv import load_dotenv
import difflib

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Configurações
SFY_EMAIL    = os.environ.get("SFY_EMAIL", "")
SFY_PASSWORD = os.environ.get("SFY_PASSWORD", "")
FB_PAGE_ID   = os.environ.get("FB_PAGE_ID", "617626864758252")
FB_TOKEN     = os.environ.get("FB_TOKEN", "")
GEMINI_KEY   = os.environ.get("GEMINI_API_KEY", "")

POSTED_FILE  = "posted_ids.json"
SFY_SHARE    = "https://www.sharesforyou.com/dashboard/share"
SFY_LOGIN    = "https://www.sharesforyou.com/login"
FB_GRAPH     = "https://graph.facebook.com/v22.0"

# Identidade visual — Shopee (laranja vibrante)
SHOPEE_ORANGE  = (255, 87, 34)
SHOPEE_RED     = (213, 0, 0)
SHOPEE_DARK    = (15, 15, 20)
SHOPEE_GOLD    = (255, 193, 7)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    r = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=r))
    return s

# Palavras irrelevantes para normalização semântica de títulos
_STOP_WORDS = {
    "de","da","do","das","dos","a","o","as","os","e","em","no","na","nos","nas",
    "por","para","com","que","se","ao","à","um","uma","uns","umas","é","foi",
    "ser","ter","mais","mas","ou","ele","ela","eles","elas","seu","sua"
}

def normalizar_titulo(title):
    """Normaliza título removendo stop words, números e pontuação para comparação semântica."""
    t = title.lower()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\b\d+\b', '', t)
    palavras = [w for w in t.split() if w not in _STOP_WORDS and len(w) > 2]
    return ' '.join(sorted(palavras))

def make_article_id(title):
    """Gera ID estável baseado no título normalizado."""
    chave = normalizar_titulo(title)
    return hashlib.sha256(chave.encode('utf-8')).hexdigest()[:16]

def load_state():
    """
    Carrega o estado unificado do bot a partir do posted_ids.json.
    Retorna (set_de_ids, lista_de_titulos_recentes).
    """
    if not os.path.exists(POSTED_FILE):
        return set(), []
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            log.info(f"📂 Estado legado carregado: {len(data)} IDs. Migrando para novo formato.")
            return set(data), []
        if isinstance(data, dict):
            ids = set(data.get("ids", []))
            titles = data.get("titles", [])
            log.info(f"📂 Estado carregado: {len(ids)} IDs únicos | {len(titles)} títulos recentes.")
            return ids, titles
    except Exception as e:
        log.warning(f"⚠️ Erro ao carregar estado: {e}")
    return set(), []

def save_state(ids_set, titles_list):
    """Salva o estado unificado em formato JSON estruturado."""
    titles_list = titles_list[-200:]
    data = {
        "ids": sorted(list(ids_set)),
        "titles": titles_list
    }
    try:
        with open(POSTED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info(f"💾 Estado salvo: {len(ids_set)} IDs | {len(titles_list)} títulos.")
    except Exception as e:
        log.error(f"❌ Falha ao salvar estado: {e}")

def load_recent_titles():
    """Carrega títulos recentes para o Gemini não repetir HOOKs visuais."""
    if os.path.exists("last_title.txt"):
        try:
            with open("last_title.txt", "r", encoding="utf-8") as f:
                return [linha.strip() for linha in f.readlines() if linha.strip()]
        except: return []
    return []

def save_recent_titles(titles_list):
    try:
        with open("last_title.txt", "w", encoding="utf-8") as f:
            for t in titles_list[-15:]:
                f.write(t + "\n")
    except: pass

def baixar_fonte(emoji=False):
    local_impact = os.path.join("fonts", "impact.ttf")
    if os.path.exists(local_impact): return local_impact

    if emoji:
        for f in ["C:\\Windows\\Fonts\\seguiemj.ttf"]:
            if os.path.exists(f): return f

    for f in ["C:\\Windows\\Fonts\\impact.ttf", "fonts/NotoSans-Bold.ttf", "C:\\Windows\\Fonts\\arialbd.ttf"]:
        if os.path.exists(f): return f
    return None

def limpar_emojis(texto):
    return re.sub(r'[^\w\s.,!?;:\"\'()\-\u00C0-\u00FF]+', '', texto).strip()

FB_REACTIONS = {
    "LIKE": "1f44d",
    "LOVE": "2764-fe0f",
    "CARE": "1f917",
    "HAHA": "1f606",
    "WOW": "1f62e",
    "SAD": "1f622",
    "ANGRY": "1f621"
}

def gerar_gancho(title):
    default_res = {
        "hook": "BOMBA!!", "tag": "ACHADO SHOPEE",
        "color": (255, 87, 34, 200), "emoji": "1f6d2",
        "hashtags": "#shopee #rainhadashopee #achados",
        "category": "OFERTA",
        "reactions": [("1f631", "Incrível!"), ("1f44d", "Quero!"), ("1f621", "Caro demais")],
        "misterio": "VEJA ESSE ACHADO INCRÍVEL DA SHOPEE"
    }

    if not GEMINI_KEY:
        return default_res

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = (
        f"Analise a notícia: \"{title}\".\n"
        f"Retorne APENAS um JSON válido com a seguinte estrutura:\n"
        "{\n"
        "  \"hook\": \"Título em CAIXA ALTA, muito humano, coeso e extremamente curioso para atrair cliques (máx 6 palavras, evite palavras soltas/sem sentido). CAMUFLE palavras sensíveis (M0RT3, S@NGU3)\",\n"
        "  \"tag\": \"Uma ÚNICA palavra em MAIÚSCULO definindo a categoria da notícia (ex: FOFOCA, POLÍTICA, BRASIL, ESPORTE, VIRAL)\",\n"
        "  \"emoji\": \"código hexadecimal do emoji sem U+, ex: 1f6d2\",\n"
        "  \"hashtags\": \"#hashtag1 #hashtag2 #hashtag3\",\n"
        "  \"misterio\": \"Frase incompleta que gere curiosidade (ex: O que foi descoberto vai te chocar...)\"\n"
        "}\n"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }

    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                resp_text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                dados = json.loads(resp_text)

                for k in ["hook", "tag", "emoji", "hashtags", "misterio"]:
                    if k in dados:
                        default_res[k] = dados[k]

                default_res["emoji"] = default_res["emoji"].replace("U+", "").lower().strip()
                log.info(f"🧠 Gemini gerou o título com sucesso: {default_res['hook']}")
                return default_res
            elif r.status_code == 429:
                log.warning(f"⚠️ Rate limit do Gemini (429). Tentativa {attempt+1}/3. Aguardando...")
                time.sleep(10)
            elif r.status_code >= 500:
                log.warning(f"⚠️ Erro no servidor do Gemini (Status {r.status_code}). Tentativa {attempt+1}/3.")
                time.sleep(10)
            else:
                log.warning(f"⚠️ Erro do Gemini (Status {r.status_code}): {r.text}")
                break
        except Exception as e:
            log.warning(f"⚠️ Exceção na IA do Gemini (Tentativa {attempt+1}/3): {e}")
            time.sleep(5)

    log.warning("❌ Falha em todas as tentativas do Gemini. Usando título genérico.")
    return default_res

def gerar_audio_tts(titulo_noticia):
    """
    Gera o áudio TTS para a notícia.
    Tenta usar edge-tts (API Python) para voz masculina, se falhar, usa gTTS.
    """
    import asyncio
    texto = f"{titulo_noticia}. Veja completo no link azul na legenda."
    tts_file = "temp_tts.mp3"

    try:
        import edge_tts

        async def _gerar_edge():
            communicate = edge_tts.Communicate(texto, voice="pt-BR-AntonioNeural", rate="+50%")
            await communicate.save(tts_file)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Loop fechado")
            loop.run_until_complete(_gerar_edge())
        except RuntimeError:
            asyncio.run(_gerar_edge())

        if os.path.exists(tts_file) and os.path.getsize(tts_file) > 0:
            log.info("✅ Áudio TTS gerado (edge-tts - voz masculina pt-BR-AntonioNeural)")
            return tts_file
        else:
            log.warning("⚠️ edge-tts gerou arquivo vazio ou não encontrado.")
    except ImportError:
        log.warning("⚠️ edge-tts não instalado. Tentando gTTS...")
    except Exception as e:
        log.warning(f"⚠️ Erro ao tentar edge-tts: {e}")

    log.info("🔄 Usando gTTS (voz feminina) como fallback...")
    try:
        from gtts import gTTS
        tts = gTTS(text=texto, lang='pt', slow=False)
        tts.save(tts_file)
        if os.path.exists(tts_file) and os.path.getsize(tts_file) > 0:
            log.info("✅ Áudio TTS gerado (gTTS)")
            return tts_file
    except ImportError:
        log.warning("⚠️ Biblioteca gTTS não instalada. Execute: pip install gTTS edge-tts")
    except Exception as e:
        log.error(f"❌ Erro ao gerar TTS (gTTS): {e}")

    log.error("❌ Todos os métodos TTS falharam. Prosseguindo sem narração.")
    return None


def gerar_video_ffmpeg(img_bg_path, img_text_path, audio_bg_path, audio_tts_path, output_path, duration=20):
    """
    Cria um vídeo com movimento real (efeito Ken Burns / zoom suave) no background,
    e o texto aparece com um leve movimento da esquerda para a direita + fade in (1.5s).
    """
    log.info(f"🎞️ Gerando vídeo DINÂMICO de {duration}s com Ken Burns e texto animado...")
    try:
        fps = 30
        total_frames = duration * fps

        bg_filter = (
            f"[0:v]zoompan=z='min(zoom+0.0003,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s=1080x1920:fps={fps}[bg];"
        )

        text_filter = f"[1:v]scale=1080:1920,fade=t=in:st=0:d=1.5:alpha=1[txt];"

        overlay_filter = f"[bg][txt]overlay=x='-100 + (100/1.5)*min(t,1.5)':y=0[v];"

        if audio_tts_path and os.path.exists(audio_tts_path):
            audio_filter = (
                "[2:a]volume=0.10[a_bg];"
                "[3:a]volume=2.5[a_tts];"
                "[a_bg][a_tts]amix=inputs=2:duration=longest[a_mix];"
                f"[a_mix]afade=t=in:st=0:d=0.5,afade=t=out:st={max(duration-1,0)}:d=1[a]"
            )
            inputs_cmd = [
                "-i", img_bg_path,
                "-loop", "1", "-framerate", str(fps), "-i", img_text_path,
                "-stream_loop", "-1", "-i", audio_bg_path,
                "-i", audio_tts_path
            ]
        else:
            audio_filter = (
                "[2:a]volume=1.0[a_bg];"
                f"[a_bg]afade=t=in:st=0:d=0.5,afade=t=out:st={max(duration-1,0)}:d=1[a]"
            )
            inputs_cmd = [
                "-i", img_bg_path,
                "-loop", "1", "-framerate", str(fps), "-i", img_text_path,
                "-stream_loop", "-1", "-i", audio_bg_path
            ]

        filter_complex = bg_filter + text_filter + overlay_filter + audio_filter

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", str(fps)
        ] + inputs_cmd + [
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-profile:v", "high",
            "-level", "4.0",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-t", str(duration),
            output_path
        ]

        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(cmd, check=True, capture_output=True, creationflags=creationflags)
        log.info(f"✅ Vídeo dinâmico gerado: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"❌ Erro no FFmpeg (código {e.returncode}): {e.stderr.decode('utf-8', errors='replace')[-500:]}")
        return False
    except Exception as e:
        log.error(f"❌ Erro inesperado no FFmpeg: {e}")
        return False

def publicar_reel(page_id, token, video_path, message):
    """
    Publica um Reel no Facebook usando o processo de 3 etapas (Start, Upload, Finish).
    """
    log.info("🚀 Iniciando upload de Reel...")

    try:
        url_init = f"https://graph.facebook.com/v22.0/{page_id}/video_reels"
        res_init = requests.post(url_init, params={
            "upload_phase": "start",
            "access_token": token
        }, timeout=30).json()

        video_id = res_init.get("video_id")
        if not video_id:
            log.error(f"Erro ao iniciar sessão Reel: {res_init}")
            return None

        file_size = os.path.getsize(video_path)
        url_upload = f"https://rupload.facebook.com/video-upload/v22.0/{video_id}"
        headers = {
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "application/octet-stream"
        }
        with open(video_path, "rb") as f:
            res_up = requests.post(url_upload, headers=headers, data=f, timeout=120)

        if res_up.status_code != 200:
            log.error(f"Erro no upload binário: {res_up.text}")
            return None

        url_finish = f"https://graph.facebook.com/v22.0/{page_id}/video_reels"
        payload = {
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": message,
            "access_token": token
        }
        res_finish = requests.post(url_finish, data=payload, timeout=30).json()

        if res_finish.get("success"):
            log.info(f"✅ REEL PUBLICADO! ID: {video_id}")
            return video_id
        else:
            log.error(f"Erro ao finalizar Reel: {res_finish}")
            return None

    except Exception as e:
        log.error(f"Erro no processo de publicação de Reel: {e}")
        return None

def publicar_imagem(page_id, token, img_path, message):
    """
    Publica uma foto na página do Facebook.
    """
    log.info("📸 Iniciando postagem da imagem...")
    try:
        url = f"https://graph.facebook.com/v22.0/{page_id}/photos"
        payload = {
            "message": message,
            "access_token": token
        }
        with open(img_path, "rb") as f:
            res = requests.post(url, data=payload, files={"source": f}, timeout=60).json()

        if res.get("id"):
            log.info(f"✅ IMAGEM PUBLICADA! ID: {res.get('id')}")
            return res.get("id")
        else:
            log.error(f"Erro ao publicar imagem: {res}")
            return None
    except Exception as e:
        log.error(f"Erro no processo de publicação de imagem: {e}")
        return None

def adicionar_texto_premium(img_bytes, dados_esteticos):
    texto = dados_esteticos["hook"]
    tag_texto = dados_esteticos["tag"]

    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

    img_orig = Image.open(BytesIO(img_bytes)).convert("RGB")

    # Reconstruir imagem para garantir a remoção completa de metadados/EXIF
    data = list(img_orig.getdata())
    img_clean = Image.new(img_orig.mode, img_orig.size)
    img_clean.putdata(data)
    img_orig = img_clean

    font_path = baixar_fonte()

    def build_ui(target_ratio):
        sf = 2
        W = 1080 * sf
        H = int(W / target_ratio)

        from PIL import ImageOps
        # 1. Fundo Borrado (Impacto Viral) - cobre a tela toda sem bordas
        canvas = ImageOps.fit(img_orig, (W, H), method=Image.Resampling.LANCZOS)
        canvas = canvas.filter(ImageFilter.GaussianBlur(15 * sf))
        canvas = ImageEnhance.Brightness(canvas).enhance(0.35)

        # Overlay com gradiente laranja-escuro Shopee no fundo inferior
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        grad_h = int(H * 0.55)
        for y in range(H - grad_h, H):
            alpha = int(220 * ((y - (H - grad_h)) / grad_h))
            draw_ov.line([(0, y), (W, y)], fill=(255, 87, 34, min(200, alpha)))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")

        # 2. Imagem Nítida Central (Aumentada para ficar grande na tela)
        max_w = int(W * 0.90)
        max_h = int(H * 0.58)
        orig_w, orig_h = img_orig.size
        # Calcula a escala exata para usar todo o espaço possível
        ratio_w = max_w / orig_w
        ratio_h = max_h / orig_h
        scale = min(ratio_w, ratio_h)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        img_sharp = img_orig.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Sombra leve atrás da imagem principal
        shadow = Image.new("RGBA", (img_sharp.width + int(30*sf), img_sharp.height + int(30*sf)), (0, 0, 0, 0))
        draw_sh = ImageDraw.Draw(shadow)
        draw_sh.rectangle([int(15*sf), int(15*sf), shadow.width, shadow.height], fill=(0, 0, 0, 150))
        shadow = shadow.filter(ImageFilter.GaussianBlur(15*sf))

        paste_x = (W - img_sharp.width) // 2
        paste_y = int(H * 0.1)

        canvas.paste(shadow, (paste_x - int(15*sf), paste_y - int(15*sf)), shadow)
        canvas.paste(img_sharp, (paste_x, paste_y))

        # Cria a camada de texto transparente
        text_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)

        try:
            f_tag = ImageFont.truetype(font_path, int(45 * sf))
            f_text = ImageFont.truetype(font_path, int(80 * sf))
            f_brand = ImageFont.truetype(font_path, int(28 * sf))
        except:
            f_tag = ImageFont.load_default()
            f_text = ImageFont.load_default()
            f_brand = ImageFont.load_default()

        # Tag laranja Shopee "BOMBA" sobrepondo o canto da imagem
        tag_y = paste_y - int(30 * sf)
        if tag_y < int(20 * sf): tag_y = int(20 * sf)
        bbox = draw.textbbox((0, 0), tag_texto, font=f_tag)
        tag_w = bbox[2] - bbox[0] + (60 * sf)

        draw.rectangle([paste_x - int(15*sf), tag_y, paste_x - int(15*sf) + tag_w, tag_y + int(70 * sf)], fill=(255, 87, 34))
        draw.text((paste_x - int(15*sf) + (tag_w // 2), tag_y + int(35 * sf)), tag_texto, fill="white", font=f_tag, anchor="mm")

        # Texto principal (Caixa Alta e Bold)
        texto_puro = limpar_emojis(texto).upper()
        import textwrap
        lines = textwrap.wrap(texto_puro, width=18)
        
        y_text = paste_y + img_sharp.height + int(60 * sf)
        
        # Barras verticais de impacto ao lado do texto
        bar_x = int(W * 0.06)
        draw.line([(bar_x, y_text), (bar_x, y_text + len(lines) * int(85 * sf))], fill=(255, 87, 34), width=int(18 * sf))

        for line in lines:
            draw.text((bar_x + int(40 * sf), y_text), line, fill="white", font=f_text)
            y_text += int(85 * sf)

        return canvas, text_layer

    # A) IMAGEM REEL (Centro 1:1 + Blur 9:16)
    img_bg_1_1, text_layer_1_1 = build_ui(1.0)
    sf = 2
    tw_sf, th_sf = 2160, 3840
    bg_size = th_sf

    # 1. Montar fundo 9:16
    background = img_bg_1_1.resize((bg_size, bg_size), Image.Resampling.LANCZOS)
    left = (bg_size - tw_sf) // 2
    background = background.crop((left, 0, left + tw_sf, th_sf))
    background = background.filter(ImageFilter.GaussianBlur(radius=20 * sf))
    background = ImageEnhance.Brightness(background).enhance(0.55)
    canvas_916_bg = background

    img_core_scaled_bg = img_bg_1_1.resize((tw_sf, tw_sf), Image.Resampling.LANCZOS)
    y_offset = (th_sf - tw_sf) // 2
    canvas_916_bg.paste(img_core_scaled_bg.convert("RGBA"), (0, y_offset), img_core_scaled_bg.convert("RGBA"))

    out_reel_bg = BytesIO()
    canvas_916_bg.convert("RGB").save(out_reel_bg, format="JPEG", quality=98)

    # 2. Montar texto 9:16
    canvas_916_text = Image.new("RGBA", (tw_sf, th_sf), (0, 0, 0, 0))
    text_layer_scaled = text_layer_1_1.resize((tw_sf, tw_sf), Image.Resampling.LANCZOS)
    canvas_916_text.paste(text_layer_scaled, (0, y_offset), text_layer_scaled)

    out_reel_text = BytesIO()
    canvas_916_text.save(out_reel_text, format="PNG")

    # B) IMAGEM POST (4:5 puro)
    img_bg_4_5, text_layer_4_5 = build_ui(0.8)
    canvas_4_5 = img_bg_4_5.copy()
    canvas_4_5.paste(text_layer_4_5, (0, 0), text_layer_4_5)

    out_post = BytesIO()
    canvas_4_5.convert("RGB").save(out_post, format="JPEG", quality=98)

    return out_reel_bg.getvalue(), out_reel_text.getvalue(), out_post.getvalue()


def _selecionar_link_correto(links_info: list) -> str:
    """
    Seleciona o link correto do card SFY.
    """
    for li in links_info:
        icone = li.get("iconeClasse", "")
        if any(cls in icone for cls in ["ti-bold", "ti-typography", "ti-article",
                                         "ti-letter-t", "ti-text", "ti-file-text", "ti-news"]):
            return li.get("href", "")
    for li in links_info:
        href = li.get("href", "")
        if any(p in href for p in ["/share/", "/post/", "/artigo/", "sharesforyou.com"]):
            return href
    for li in links_info:
        icone = li.get("iconeClasse", "")
        if not any(skip in icone for skip in ["ti-eye", "ti-brand-facebook", "ti-share", "ti-copy"]):
            return li.get("href", "")
    return links_info[0].get("href", "") if links_info else ""


def salvar_links_noticias(noticias: list):
    """
    Exporta os links extraídos para links_noticias.json.
    """
    hoje = datetime.date.today().isoformat()
    try:
        existente = {"links": []}
        if os.path.exists("links_noticias.json"):
            with open("links_noticias.json", "r", encoding="utf-8") as f:
                existente = json.load(f)

        links_existentes = {item["link"] for item in existente.get("links", [])}
        novos = 0
        for n in noticias:
            if n["link"] not in links_existentes:
                existente["links"].append({
                    "titulo": n["title"],
                    "link":   n["link"],
                    "data":   hoje,
                })
                novos += 1

        existente["ultima_atualizacao"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with open("links_noticias.json", "w", encoding="utf-8") as f:
            json.dump(existente, f, indent=2, ensure_ascii=False)
        log.info(f"📤 links_noticias.json atualizado — {novos} links novos exportados.")
    except Exception as e:
        log.warning(f"⚠️ Não foi possível salvar links_noticias.json: {e}")


def get_noticias():
    import datetime
    from playwright.sync_api import sync_playwright
    res = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            log.info("Acessando SFY...")
            page.goto(SFY_LOGIN)
            page.fill("input[name='email']", SFY_EMAIL)
            page.fill("input[name='password']", SFY_PASSWORD)
            page.click("button[type='submit']")
            page.wait_for_url("**/dashboard**", timeout=40000)
            page.goto(SFY_SHARE)
            page.wait_for_timeout(7000)

            log.info("Selecionando bloco Sharesforyou...")
            try:
                page.click("button.change-order-by:has-text('Sharesforyou')", timeout=15000)
                page.wait_for_timeout(10000)
            except Exception as e:
                log.warning(f"Não foi possível clicar no botão Sharesforyou: {e}")

            cards = page.locator(".card").all()
            log.info(f"Encontrados {len(cards)} cards no bloco Sharesforyou.")

            for card in cards:
                try:
                    title = card.locator("h5, p.fs-4").first.inner_text().strip()
                    img = card.locator("img").first.get_attribute("src")

                    links_info = card.evaluate("""el => {
                        return Array.from(el.querySelectorAll('a[href]'))
                            .filter(a => {
                                const href = a.getAttribute('href') || '';
                                return href.length > 1 && !href.startsWith('#')
                                    && !href.includes('javascript:') && !a.querySelector('img');
                            })
                            .map(a => ({
                                href: a.getAttribute('href'),
                                iconeClasse: (a.querySelector('i') || {}).className || ''
                            }));
                    }""")

                    if not title or not links_info:
                        continue

                    link = _selecionar_link_correto(links_info)
                    if not link:
                        continue

                    if link.startswith("/"):  link = "https://www.sharesforyou.com" + link
                    if img and img.startswith("/"): img = "https://www.sharesforyou.com" + img

                    log.info(f"  ✅ Link extraído: {link[:80]}")
                    res.append({"id": make_article_id(title), "title": title,
                                "link": link, "img": img})
                except Exception as ce:
                    log.debug(f"Erro no card: {ce}")
                    continue
        except Exception as e:
            log.error(f"Erro Playwright: {e}")
        finally:
            browser.close()

    if res:
        salvar_links_noticias(res)

    return res

def main():
    log.info("🛍️ Bot Rainha da Shopee — Iniciado!")

    load_dotenv(override=True)
    FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "").strip()
    FB_TOKEN   = os.environ.get("FB_TOKEN", "").strip()

    if not FB_TOKEN or not FB_PAGE_ID:
        log.error("❌ FB_TOKEN ou FB_PAGE_ID não configurados. Encerrando.")
        return

    log.info(f"🔑 PAGE_ID: {FB_PAGE_ID}")
    log.info(f"🔑 TOKEN: {FB_TOKEN[:20]}...")

    posted_ids, posted_titles = load_state()
    news = get_noticias()
    if not news:
        log.warning("Nenhuma notícia encontrada.")
        return

    log.info(f"📰 {len(news)} notícias encontradas. Verificando duplicatas...")
    n_puladas = 0

    for n in news:
        # CAMADA 1: Hash exato pelo ID (título normalizado)
        if n["id"] in posted_ids:
            log.info(f"⏭️ [ID] Pulando: {n['title'][:60]}")
            n_puladas += 1
            continue

        # CAMADA 2: Fuzzy match semântico
        titulo_norm = normalizar_titulo(n["title"])
        similaridade_encontrada = False
        melhor_match = 0.0

        for titulo_hist in posted_titles:
            ratio = difflib.SequenceMatcher(None, titulo_norm, titulo_hist).ratio()
            if ratio > melhor_match:
                melhor_match = ratio
            if ratio >= 0.80:
                similaridade_encontrada = True
                log.info(f"⏭️ [Fuzzy {ratio*100:.1f}%] Pulando: {n['title'][:60]}")
                break

        if not similaridade_encontrada and melhor_match > 0:
            log.info(f"  ✅ Mais parecida encontrada: {melhor_match*100:.1f}% — permitida.")

        if similaridade_encontrada:
            n_puladas += 1
            continue

        log.info(f"🆕 Notícia inédita encontrada: {n['title'][:60]}")

        try:
            img_data = None
            if n.get("img"):
                log.info(f"📥 Baixando imagem: {n['img'][:50]}...")
                try:
                    r_img = requests.get(n["img"], headers=HEADERS, timeout=15)
                    if r_img.status_code == 200:
                        img_data = r_img.content
                        log.info(f"✅ Imagem baixada ({len(img_data)//1024}KB)")
                except Exception as e_img:
                    log.warning(f"⚠️ Erro no download simples: {e_img}")

            if not img_data:
                log.warning(f"⚠️ Sem imagem válida para: {n['title'][:50]}, pulando.")
                continue

            estetica = gerar_gancho(n["title"])
            img_reel_bg_b, img_reel_text_b, img_post_b = adicionar_texto_premium(img_data, estetica)

            temp_reel_bg = "temp_reel_bg.jpg"
            with open(temp_reel_bg, "wb") as f:
                f.write(img_reel_bg_b)

            temp_reel_text = "temp_reel_text.png"
            with open(temp_reel_text, "wb") as f:
                f.write(img_reel_text_b)

            temp_post_img = "temp_post.jpg"
            with open(temp_post_img, "wb") as f:
                f.write(img_post_b)

            audio_files = glob.glob("AUDIOS NEWS/*.mp3")
            if not audio_files:
                log.error("❌ Nenhum arquivo MP3 encontrado na pasta AUDIOS NEWS!")
                continue

            audio_sel = random.choice(audio_files)
            temp_video = "temp_reel.mp4"
            duracao_random = random.randint(20, 45)

            temp_tts = gerar_audio_tts(n["title"])

            if not gerar_video_ffmpeg(temp_reel_bg, temp_reel_text, audio_sel, temp_tts, temp_video, duration=duracao_random):
                continue

            hashtags = estetica.get("hashtags", "#shopee #rainhadashopee #achados").lower()
            misterio = estetica.get("misterio", "VEJA ESSE ACHADO INCRÍVEL DA SHOPEE")

            if "#viral" not in hashtags: hashtags += " #viral"
            if "#foryou" not in hashtags: hashtags += " #foryou"
            if "#shopee" not in hashtags: hashtags += " #shopee"

            msg = (
                f"🔴VEJA COMPLETO NO LINK🔗: {n['link']}\n"
                f".\n"
                f".\n"
                f"{hashtags}"
            )

            video_id = publicar_reel(FB_PAGE_ID, FB_TOKEN, temp_video, msg)

            if video_id:
                log.info(f"🔗 LINK REEL: https://www.facebook.com/reels/{video_id}/")

                img_post_id = publicar_imagem(FB_PAGE_ID, FB_TOKEN, temp_post_img, msg)
                if img_post_id:
                    log.info(f"📸 Sucesso! A imagem também foi postada.")

                # Salvar link para verificação posterior
                with open("ultimo_post.txt", "w", encoding="utf-8") as f:
                    f.write(f"https://www.facebook.com/reels/{video_id}/\n")
                    f.write(f"Notícia: {n['title']}\n")
                    f.write(f"Data: {datetime.datetime.now().isoformat()}\n")

                posted_ids.add(n["id"])
                posted_titles.append(normalizar_titulo(n["title"]))
                save_state(posted_ids, posted_titles)

                for f in [temp_reel_bg, temp_reel_text, temp_post_img, temp_video, temp_tts]:
                    if f and os.path.exists(f): os.remove(f)
                break
            else:
                log.error("Falha ao publicar Reel.")
                for f in [temp_reel_bg, temp_reel_text, temp_post_img, temp_video, temp_tts]:
                    if f and os.path.exists(f): os.remove(f)
                log.warning("🛑 Interrompendo execução por falha na publicação (verifique o TOKEN).")
                break
        except Exception as e:
            log.error(f"Erro no loop principal: {e}")
            log.error(traceback.format_exc())

if __name__ == "__main__": main()
