#!/bin/bash
set -e

mkdir -p /app/checkpoints

# 1. SAM ViT-B súlyfájl ellenőrzése és letöltése (~375 MB)
SAM_CHECKPOINT="/app/checkpoints/sam_vit_b_01ec64.pth"
if [ ! -f "$SAM_CHECKPOINT" ]; then
    echo "[INFO] SAM súlyfájl nem található, letöltés folyamatban (ViT-B)..."
    curl -L --retry 3 -o "$SAM_CHECKPOINT" "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth"
    echo "[INFO] SAM súlyfájl sikeresen letöltve."
else
    echo "[INFO] SAM súlyfájl rendben (megtalálva)."
fi

# 2. Stable Diffusion Inpainting modell előtöltése a Hugging Face cache-be (~4 GB)
echo "[INFO] Stable Diffusion Inpainting modell ellenőrzése / előtöltése..."
python -c "
import sys
try:
    from diffusers import StableDiffusionInpaintPipeline
    print('[INFO] Keresés a lokális cache-ben vagy letöltés megkezdése (ez percekig tarthat első alkalommal)...')
    StableDiffusionInpaintPipeline.from_pretrained('runwayml/stable-diffusion-inpainting', safety_checker=None)
    print('[INFO] Stable Diffusion sikeresen a cache-ben.')
except Exception as e:
    print(f'[HIBA] Nem sikerült előtölteni a modellt: {e}')
    sys.exit(1)
"

# 3. Django adatbázis-migrációk automatikus futtatása
if [ -f "manage.py" ]; then
    echo "[INFO] Django migrációk ellenőrzése és futtatása..."
    python manage.py migrate --noinput
fi

# 4. A Docker CMD végrehajtása
exec "$@"