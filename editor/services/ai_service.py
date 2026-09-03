import os
from pathlib import Path

import torch
import numpy as np
import cv2
from PIL import Image
from segment_anything import sam_model_registry, SamPredictor
from diffusers import StableDiffusionInpaintPipeline

class AIService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIService, cls).__new__(cls)
            # Itt jelezzük, hogy még nincs inicializálva, de NEM indítjuk el azonnal!
            cls._instance.initialized = False
        return cls._instance

    def _initialize(self):
        # Ha már be van töltve, azonnal visszatérünk
        if self.initialized:
            return

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        print(f"[AI Service] Inicializálás az alábbi hardveren: {self.device} ({self.dtype})")

        # A szolgáltatás fájljától függetlenül, mindig a projekt gyökeréből keressük a checkpointot.
        project_root = Path(__file__).resolve().parents[2]
        sam_checkpoint = project_root / "checkpoints" / "sam_vit_b_01ec64.pth"
        if not sam_checkpoint.is_file():
            raise FileNotFoundError(f"SAM checkpoint nem található: {sam_checkpoint}")

        sam = sam_model_registry["vit_b"](checkpoint=str(sam_checkpoint))
        sam.to(device=self.device)
        self.sam_predictor = SamPredictor(sam)
        print("[AI Service] SAM modell betöltve.")

        # 2. Stable Diffusion Inpainting Modell betöltése
        print("[AI Service] Stable Diffusion letöltése és betöltése (Ez első alkalommal hosszú percekig tarthat)...")
        self.sd_model_id = os.getenv(
            "SD_MODEL_ID", "runwayml/stable-diffusion-inpainting"
        )
        self.sd_pipe = StableDiffusionInpaintPipeline.from_pretrained(
            self.sd_model_id,
            torch_dtype=self.dtype,
            safety_checker=None
        )
        self.sd_pipe = self.sd_pipe.to(self.device)
        
        if torch.cuda.is_available():
            self.sd_pipe.enable_attention_slicing()
            
        print("[AI Service] Stable Diffusion modell sikeresen betöltve a memóriába.")
        self.initialized = True # Megjegyezzük, hogy többször ne fusson le

    def compute_embedding(self, image_bgr: np.ndarray):
        self._initialize() # Csak az első feltöltéskor fut le a letöltés
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        self.sam_predictor.set_image(image_rgb)
        print("[AI Service] Kép embedding kiszámítva.")

    def predict_mask(self, points=None, labels=None, box=None):
        self._initialize()
        input_points = np.array(points) if points is not None and len(points) > 0 else None
        input_labels = np.array(labels) if labels is not None and len(labels) > 0 else None
        input_box = np.array(box) if box is not None else None

        masks, scores, _ = self.sam_predictor.predict(
            point_coords=input_points,
            point_labels=input_labels,
            box=input_box,
            multimask_output=True
        )
        best_mask_idx = np.argmax(scores)
        return (masks[best_mask_idx] * 255).astype(np.uint8)

    def inpaint(self, image_bgr: np.ndarray, mask: np.ndarray, prompt: str, negative_prompt: str, steps: int, guidance: float) -> np.ndarray:
        self._initialize()
        
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        init_image = Image.fromarray(image_rgb)
        mask_image = Image.fromarray(mask)

        orig_w, orig_h = init_image.size

        max_size = 1024
        scale = 1.0
        if orig_w > max_size or orig_h > max_size:
            scale = max_size / max(orig_w, orig_h)
            
        new_w = int(orig_w * scale) // 8 * 8
        new_h = int(orig_h * scale) // 8 * 8
        
        init_image = init_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        mask_image = mask_image.resize((new_w, new_h), Image.Resampling.NEAREST)

        print(f"[AI Service] SD Inpainting indítása ({new_w}x{new_h})...")
        with torch.no_grad():
            result_image = self.sd_pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                image=init_image,
                mask_image=mask_image,
                num_inference_steps=steps,         # <--- Cserélve
                guidance_scale=guidance            # <--- Cserélve
            ).images[0]

        if result_image.size != (orig_w, orig_h):
            result_image = result_image.resize((orig_w, orig_h), Image.Resampling.LANCZOS)

        result_bgr = cv2.cvtColor(np.array(result_image), cv2.COLOR_RGB2BGR)
        return result_bgr

# Globális példány, de még üresen jön létre
ai_service = AIService()