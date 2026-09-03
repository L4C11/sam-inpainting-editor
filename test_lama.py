import os
import torch
import numpy as np
import cv2

def run_lama_test():
    image_path = "test_person.jpg"
    checkpoint_path = "checkpoints/big-lama.pt"
    output_path = "test_inpainted_output.png"

    if not os.path.exists(image_path):
        print(f"[HIBA] A tesztkép nem található: {image_path}")
        return

    if not os.path.exists(checkpoint_path):
        print(f"[HIBA] A modell nem található: {checkpoint_path}")
        return

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] TorchScript modell betöltése ({device})...")
    model = torch.jit.load(checkpoint_path, map_location=device)
    model.eval()

    # Kép betöltése
    img_bgr = cv2.imread(image_path)
    h_orig, w_orig, _ = img_bgr.shape

    # Méretezés 8-cal osztható felbontásra
    h_pad = (h_orig // 8) * 8
    w_pad = (w_orig // 8) * 8
    img_bgr = cv2.resize(img_bgr, (w_pad, h_pad), interpolation=cv2.INTER_AREA)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    # Maszk létrehozása a kép közepére/alanyára
    mask = np.zeros((h_pad, w_pad), dtype=np.uint8)
    # Függőleges ovális az emberi alak kitakarásához
    cv2.ellipse(mask, (w_pad // 2, int(h_pad * 0.55)), (int(w_pad * 0.28), int(h_pad * 0.4)), 0, 0, 360, 255, -1)

    # Normalizálás és tenzorrá alakítás
    img_tensor = torch.from_numpy(img_rgb).float() / 255.0
    img_tensor = img_tensor.permute(2, 0, 1).unsqueeze(0).to(device)

    mask_tensor = torch.from_numpy(mask).float() / 255.0
    mask_tensor = (mask_tensor > 0).float().unsqueeze(0).unsqueeze(0).to(device)

    print("[INFO] Inpainting inferencia futtatása...")
    with torch.no_grad():
        result_tensor = model(img_tensor, mask_tensor)

    # Visszaalakítás képpé
    result_np = result_tensor[0].permute(1, 2, 0).detach().cpu().numpy()
    result_np = np.clip(result_np * 255.0, 0, 255).astype(np.uint8)
    result_bgr = cv2.cvtColor(result_np, cv2.COLOR_RGB2BGR)

    # Eredeti képméret visszaállítása (ha szükséges)
    result_bgr = cv2.resize(result_bgr, (w_orig, h_orig), interpolation=cv2.INTER_CUBIC)
    mask = cv2.resize(mask, (w_orig, h_orig), interpolation=cv2.INTER_NEAREST)

    cv2.imwrite("test_mask.png", mask)
    cv2.imwrite(output_path, result_bgr)
    print(f"[SIKER] Eredmény mentve: {output_path} és test_mask.png")

if __name__ == "__main__":
    run_lama_test()