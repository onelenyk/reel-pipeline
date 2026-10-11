"""The CubiCasa5k network on a picture: what kind of room every pixel is, and where doors and windows are. It is what engine/plan.py builds on; this script shows the raw answer.
usage: ./reel run lab/plans/cubicasa_raw.py <picture> <out.png> [<picture> <out.png> ...]"""
import sys, time
sys.path.insert(0, "/work/models/cubicasa/repo")
import cv2, numpy as np, torch
from floortrans.models.hg_furukawa_original import hg_furukawa_original
ROOMS = ["Background", "Outdoor", "Wall", "Kitchen", "Living", "Bedroom", "Bath", "Entry", "Railing", "Storage", "Garage", "Undefined"]
TINT = [(255, 255, 255), (200, 230, 200), (0, 0, 0), (60, 60, 255), (255, 140, 40), (90, 180, 30), (0, 200, 240), (220, 70, 170), (120, 120, 120), (190, 180, 0), (150, 100, 60), (230, 230, 230)]
model = hg_furukawa_original(n_classes=51); model.conv4_ = torch.nn.Conv2d(256, 44, bias=True, kernel_size=1); model.upsample = torch.nn.ConvTranspose2d(44, 44, kernel_size=4, stride=4)
model.load_state_dict(torch.load("/work/models/cubicasa/weights.pkl", map_location="cpu", weights_only=True)["model_state"]); model.eval()
for path, out in zip(sys.argv[1::2], sys.argv[2::2]):
    colour = cv2.imread(path); h, w = colour.shape[:2]; H, W = (h + 31) // 32 * 32, (w + 31) // 32 * 32
    padded = cv2.copyMakeBorder(colour, 0, H - h, 0, W - w, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    began = time.time()
    with torch.no_grad(): answer = model(torch.from_numpy(cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)).permute(2, 0, 1)[None].float() / 127.5 - 1)[0]
    kind = answer[21:33].argmax(0).numpy()[:h, :w]; icon = answer[33:44].argmax(0).numpy()[:h, :w]
    shade = np.array(TINT, np.uint8)[kind]; seen = cv2.addWeighted(shade, 0.5, colour, 0.5, 0)
    seen[icon == 1] = (255, 0, 0); seen[icon == 2] = (0, 0, 255)  # windows blue, doors red
    cv2.imwrite(out, seen); np.save(out + ".npy", np.stack([kind, icon]).astype(np.uint8))
    print(path, f"{time.time() - began:.0f}s", {ROOMS[k]: round(float((kind == k).mean()), 2) for k in np.unique(kind)})
