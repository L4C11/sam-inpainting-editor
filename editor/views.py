import os
import uuid
import base64
import numpy as np
import cv2
import io
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from editor.services.ai_service import ai_service

# Munkamenetek: session_id -> {image, width, height, objects: {obj_id: mask}, inpainted_b64}
SESSIONS = {}

def index(request):
    return render(request, 'editor/index.html')

class UploadImageView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('image')
        if not file_obj:
            return Response({'error': 'No image provided.'}, status=status.HTTP_400_BAD_REQUEST)

        file_bytes = np.frombuffer(file_obj.read(), np.uint8)
        img_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

        if img_bgr is None:
            return Response({'error': 'Invalid image format.'}, status=status.HTTP_400_BAD_REQUEST)

        h, w, _ = img_bgr.shape
        session_id = str(uuid.uuid4())

        # SAM embedding előszámítása
        ai_service.compute_embedding(img_bgr)

        SESSIONS[session_id] = {
            'image': img_bgr,
            'width': w,
            'height': h,
            'objects': {},  # obj_id -> binary mask (uint8)
            'inpainted_b64': None
        }

        return Response({
            'session_id': session_id,
            'width': w,
            'height': h
        }, status=status.HTTP_201_CREATED)


class SegmentLassoView(APIView):
    parser_classes = (JSONParser,)

    def post(self, request, *args, **kwargs):
        session_id = request.data.get('session_id')
        obj_id = request.data.get('obj_id')
        polygon = request.data.get('polygon', [])  # [[x, y], ...]
        box = request.data.get('box', None)        # [x1, y1, x2, y2]
        refine = request.data.get('refine', True)

        if not session_id or session_id not in SESSIONS:
            return Response({'error': 'Invalid session.'}, status=status.HTTP_404_NOT_FOUND)

        session_data = SESSIONS[session_id]
        img_bgr = session_data['image']
        h, w = session_data['height'], session_data['width']

        # Bounding box kiszámítása a poligonból ha nincs külön megadva
        if polygon and len(polygon) > 2 and not box:
            pts = np.array(polygon, dtype=np.int32)
            x, y, bw, bh = cv2.boundingRect(pts)
            box = [x, y, x + bw, y + bh]

        # SAM maszk predikció Bounding Box alapján
        mask = ai_service.predict_mask(box=box)

        # Ha a rajzolt poligon rendelkezésre áll, kombináljuk a SAM maszkkal
        if polygon and len(polygon) > 2:
            poly_mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(poly_mask, [np.array(polygon, dtype=np.int32)], 255)
            # Metszet és unió optimalizálása
            mask = cv2.bitwise_and(mask, poly_mask)
            if refine:
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        session_data['objects'][obj_id] = mask

        # RGBA kivágott PNG készítése
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        rgba = np.dstack((img_rgb, mask))
        _, buf_obj = cv2.imencode('.png', cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        obj_base64 = base64.b64encode(buf_obj).decode('utf-8')

        # Vörös transzparens overlay
        red_overlay = np.zeros((h, w, 4), dtype=np.uint8)
        red_overlay[mask > 0] = [0, 0, 255, 140]
        _, buf_mask = cv2.imencode('.png', red_overlay)
        mask_base64 = base64.b64encode(buf_mask).decode('utf-8')

        return Response({
            'obj_id': obj_id,
            'mask_overlay_base64': f"data:image/png;base64,{mask_base64}",
            'object_base64': f"data:image/png;base64,{obj_base64}"
        }, status=status.HTTP_200_OK)


class InpaintView(APIView):
    parser_classes = (JSONParser,)

    def post(self, request, *args, **kwargs):
        session_id = request.data.get('session_id')
        dilation_pixels = int(request.data.get('dilation', 5))
        
        # Új SD paraméterek lekérése
        prompt = request.data.get('prompt', 'background, seamless, high quality, realistic')
        negative_prompt = request.data.get('negative_prompt', 'artifact, messy, ugly, object, person')
        steps = int(request.data.get('steps', 25))
        guidance = float(request.data.get('guidance', 7.5))

        if not session_id or session_id not in SESSIONS:
            return Response({'error': 'Invalid session.'}, status=status.HTTP_404_NOT_FOUND)

        session_data = SESSIONS[session_id]
        img_bgr = session_data['image'].copy()
        objects = session_data.get('objects', {})

        if not objects:
            return Response({'error': 'No object selected in the image.'}, status=status.HTTP_400_BAD_REQUEST)

        combined_mask = np.zeros((session_data['height'], session_data['width']), dtype=np.uint8)
        for mask in objects.values():
            combined_mask = cv2.bitwise_or(combined_mask, mask)

        if dilation_pixels > 0:
            k_size = dilation_pixels * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
            dilated_mask = cv2.dilate(combined_mask, kernel, iterations=1)
        else:
            dilated_mask = combined_mask

        img_bgr[dilated_mask > 0] = 0

        # Most már az új paramétereket is beküldjük!
        inpainted_bgr = ai_service.inpaint(img_bgr, dilated_mask, prompt, negative_prompt, steps, guidance)

        # --- KÉP MENTÉSE METAADATOKKAL ---
        
        # 1. OpenCV formátum (BGR) átalakítása PIL formátumra (RGB)
        inpainted_rgb = cv2.cvtColor(inpainted_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(inpainted_rgb)

        # 2. Metaadatok (PngInfo) összeállítása
        metadata = PngInfo()
        metadata.add_text("Software", "SAM Inpainting App")
        metadata.add_text("Prompt", prompt)
        metadata.add_text("NegativePrompt", negative_prompt)
        metadata.add_text("Steps", str(steps))
        metadata.add_text("GuidanceScale", str(guidance))
        metadata.add_text("MaskDilation", f"{dilation_pixels}px")

        # 3. Kép mentése a memóriába (BytesIO) a metaadatokkal együtt
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG", pnginfo=metadata)
        
        # 4. Base64 kódolás a frontend számára
        inpainted_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        # -----------------------------------

        session_data['inpainted_b64'] = f"data:image/png;base64,{inpainted_base64}"

        return Response({
            'inpainted_base64': session_data['inpainted_b64']
        }, status=status.HTTP_200_OK)
        session_data['inpainted_b64'] = f"data:image/png;base64,{inpainted_base64}"

        return Response({
            'inpainted_base64': session_data['inpainted_b64']
        }, status=status.HTTP_200_OK)


class UpdateMaskView(APIView):
    parser_classes = (JSONParser,)

    def post(self, request, *args, **kwargs):
        session_id = request.data.get('session_id')
        obj_id = request.data.get('obj_id')
        mask_b64 = request.data.get('mask_base64')

        if not session_id or session_id not in SESSIONS:
            return Response({'error': 'Invalid session.'}, status=404)
        if obj_id not in SESSIONS[session_id]['objects']:
            return Response({'error': 'Object not found.'}, status=404)

        # Base64 kép dekódolása BGRA mátrixba
        img_data = base64.b64decode(mask_b64.split(',')[1])
        np_arr = np.frombuffer(img_data, np.uint8)
        img_bgra = cv2.imdecode(np_arr, cv2.IMREAD_UNCHANGED)

        if img_bgra is None or img_bgra.shape[2] != 4:
            return Response({'error': 'Invalid mask image.'}, status=400)

        # Aktuális bináris maszk betöltése
        old_mask = SESSIONS[session_id]['objects'][obj_id].copy()

        # Színcsatornák szétválasztása (OpenCV formátum: B, G, R, A)
        b_channel = img_bgra[:, :, 0]
        g_channel = img_bgra[:, :, 1]
        r_channel = img_bgra[:, :, 2]
        a_channel = img_bgra[:, :, 3]

        # 1. Hozzáadás (Kék ecset): Ahol a kék dominál
        add_mask = (b_channel > 150) & (r_channel < 100) & (a_channel > 50)
        
        # 2. Radírozás (Fekete ecset): Ahol minden sötét
        sub_mask = (b_channel < 50) & (g_channel < 50) & (r_channel < 50) & (a_channel > 50)

        # Maszk módosítása
        old_mask[add_mask] = 255
        old_mask[sub_mask] = 0

        # Módosított maszk elmentése a memóriába (így a SAM finomhangolás is ezt fogja látni)
        SESSIONS[session_id]['objects'][obj_id] = old_mask

        # Frissített transzparens vörös overlay (BGRA) visszaküldése a frontendnek
        red_overlay = np.zeros((SESSIONS[session_id]['height'], SESSIONS[session_id]['width'], 4), dtype=np.uint8)
        red_overlay[old_mask > 0] = [0, 0, 255, 140]
        _, buf_mask = cv2.imencode('.png', red_overlay)
        new_mask_base64 = base64.b64encode(buf_mask).decode('utf-8')

        # Az objektum kivágott PNG változatának frissítése
        img_bgr = SESSIONS[session_id]['image']
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        rgba = np.dstack((img_rgb, old_mask))
        _, buf_obj = cv2.imencode('.png', cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        obj_base64 = base64.b64encode(buf_obj).decode('utf-8')

        return Response({
            'mask_overlay_base64': f"data:image/png;base64,{new_mask_base64}",
            'object_base64': f"data:image/png;base64,{obj_base64}"
        }, status=200)


class RefineMaskView(APIView):
    parser_classes = (JSONParser,)

    def post(self, request, *args, **kwargs):
        session_id = request.data.get('session_id')
        obj_id = request.data.get('obj_id')

        if not session_id or session_id not in SESSIONS:
            return Response({'error': 'Invalid session.'}, status=404)

        session_data = SESSIONS[session_id]
        mask = session_data['objects'].get(obj_id)
        
        if mask is None:
            return Response({'error': 'Object not found.'}, status=400)

        # 1. Megkeressük az aktuális (manuálisan rajzolt) maszk pontos befoglaló keretét
        coords = cv2.findNonZero(mask)
        if coords is not None:
            x, y, w, h = cv2.boundingRect(coords)
            box = [x, y, x + w, y + h]
            
            # 2. Visszaküldjük a SAM neurális hálónak a keretet!
            # A SAM így megérti, hogy ezen a területen belül kell megkeresnie a valós objektumhatárokat,
            # és a durva ecsetvonások helyett egy pixelpontos, élre illesztett maszkot ad vissza.
            refined_mask = ai_service.predict_mask(box=box)
            
            # Kicseréljük a régi maszkot a SAM által finomítottra
            mask = refined_mask

        SESSIONS[session_id]['objects'][obj_id] = mask

        # 3. Frissített transzparens vörös overlay (BGRA) előállítása a frontendnek
        red_overlay = np.zeros((session_data['height'], session_data['width'], 4), dtype=np.uint8)
        red_overlay[mask > 0] = [0, 0, 255, 140]
        _, buf_mask = cv2.imencode('.png', red_overlay)
        mask_base64 = base64.b64encode(buf_mask).decode('utf-8')

        # 4. Objektum kivágott PNG változatának frissítése (hogy a jobb oldali menüből lementhető legyen)
        img_rgb = cv2.cvtColor(session_data['image'], cv2.COLOR_BGR2RGB)
        rgba = np.dstack((img_rgb, mask))
        _, buf_obj = cv2.imencode('.png', cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        obj_base64 = base64.b64encode(buf_obj).decode('utf-8')

        return Response({
            'mask_overlay_base64': f"data:image/png;base64,{mask_base64}",
            'object_base64': f"data:image/png;base64,{obj_base64}"
        }, status=200)