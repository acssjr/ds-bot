import os
import cv2
import numpy as np
from loguru import logger

def crop_android_screen(img: np.ndarray) -> np.ndarray:
    """Remove a barra de título superior do MEmu (~36px) e a barra de ferramentas direita (~40px)."""
    h, w = img.shape[:2]
    top_offset = 36
    right_offset = 40
    return img[top_offset:h, 0:w - right_offset]

def generate_templates():
    screenshot_dir = r"C:\Users\antonio.santos\Documents\draft-showndown-bot\screenshots"
    templates_base = r"c:\Users\antonio.santos\Documents\draft-showndown-bot\assets\templates"

    os.makedirs(templates_base, exist_ok=True)

    # Mapeamento de quais crops extrair de quais screenshots para criar ancoragens perfeitas
    # Cada entrada: (state_folder, template_filename, source_screenshot, norm_bbox: (min_x, min_y, max_x, max_y))
    crops_mapping = [
        # HOME
        ("home", "batalha_btn.png", "tela-inicial-pos-jogo-opcao-reinvindicar-cartas.png", (0.33, 0.70, 0.67, 0.81)),
        ("home", "reiv_home_btn.png", "tela-inicial-pos-jogo-opcao-reinvindicar-cartas.png", (0.30, 0.53, 0.70, 0.63)),

        # MATCHMAKING
        ("wait_matchmaking", "procurando_txt.png", "tela-procura-oponente.png", (0.20, 0.40, 0.80, 0.55)),

        # DRAFT
        ("draft_screen", "vs_banner.png", "primeira-selecao-cartas.png", (0.35, 0.05, 0.65, 0.13)),
        ("draft_screen", "comeback_banner.png", "bonus-de-recuperacao.png", (0.20, 0.35, 0.80, 0.43)),

        # VICTORY SUMMARY & ADS
        ("victory_summary", "vitoria_title.png", "tela vitoria 2 reinvindicar bonus ads.png", (0.30, 0.06, 0.70, 0.15)),
        ("victory_summary", "reiv_ad_btn.png", "tela vitoria 2 reinvindicar bonus ads.png", (0.25, 0.70, 0.75, 0.82)),
        ("victory_summary", "continuar_btn.png", "tela vitoria 2 reinvindicar bonus ads.png", (0.50, 0.87, 0.82, 0.95)),
        ("victory_summary", "timer_ad_btn.png", "anuncio-indisponivel.png", (0.25, 0.70, 0.75, 0.82)),

        # DOUBLE BITS
        ("double_bits", "x2_bits_btn.png", "dobro-bits-pos-reinvindicar.png", (0.25, 0.66, 0.75, 0.77)),
        ("double_bits", "continuar_green_btn.png", "dobro-bits-pos-reinvindicar.png", (0.25, 0.78, 0.75, 0.89)),

        # MASTERY BOOST
        ("mastery_boost", "vitoria_mastery_title.png", "impulso.png", (0.30, 0.23, 0.70, 0.32)),
        ("mastery_boost", "continuar_boost_btn.png", "impulso.png", (0.28, 0.78, 0.72, 0.89)),

        # BIT PACK OPENING
        ("bit_pack", "toque_pular_txt.png", "bit-pack.png", (0.20, 0.82, 0.80, 0.87)),

        # NEW UNIT UNLOCKED
        ("new_unit", "nova_unidade_title.png", "nova-unidade.png", (0.15, 0.18, 0.85, 0.26)),
        ("new_unit", "continuar_unit_btn.png", "nova-unidade.png", (0.25, 0.73, 0.75, 0.84)),

        # WATCHING ADS & CLOSE AD
        ("watching_ad", "close_x_btn.png", "tela-fechar-anuncio.png", (0.80, 0.04, 0.96, 0.11)),
        ("watching_ad", "reward_granted.png", "reward-granted-apos-os-2-anuncios.png", (0.20, 0.40, 0.80, 0.55)),

        # COLLECTION MENU
        ("collection_menu", "colecao_tab.png", "menu-colecao.png", (0.18, 0.85, 0.42, 0.98)),
        ("collection_menu", "batalha_tab.png", "menu-colecao.png", (0.42, 0.85, 0.58, 0.98)),
    ]

    count = 0
    for state_folder, template_filename, source_shot, (min_x, min_y, max_x, max_y) in crops_mapping:
        shot_path = os.path.join(screenshot_dir, source_shot)
        if not os.path.exists(shot_path):
            logger.warning(f"Screenshot fonte não encontrado: {source_shot}")
            continue

        img = cv2.imread(shot_path)
        android_img = crop_android_screen(img)
        h, w = android_img.shape[:2]

        x1 = int(round(min_x * w))
        y1 = int(round(min_y * h))
        x2 = int(round(max_x * w))
        y2 = int(round(max_y * h))

        tpl_crop = android_img[y1:y2, x1:x2]

        folder_path = os.path.join(templates_base, state_folder)
        os.makedirs(folder_path, exist_ok=True)
        save_path = os.path.join(folder_path, template_filename)

        cv2.imwrite(save_path, tpl_crop)
        count += 1
        logger.info(f"Template salvo: {state_folder}/{template_filename} ({tpl_crop.shape[1]}x{tpl_crop.shape[0]} px)")

    print(f"\n==========================================")
    print(f"Sucesso: {count} templates gerados a partir dos 24 screenshots!")
    print(f"==========================================")

if __name__ == "__main__":
    generate_templates()
