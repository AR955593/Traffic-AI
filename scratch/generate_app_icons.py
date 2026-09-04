import os
import glob
from PIL import Image

source_image_path = r"c:\Users\ankit\OneDrive\Desktop\project\ChatGPT Image Sep 2, 2026, 01_00_54 PM.png"
base_res_dir = r"c:\Users\ankit\OneDrive\Desktop\project\android-app\app\src\main\res"

sizes = {
    "mipmap-mdpi": (48, 48),
    "mipmap-hdpi": (72, 72),
    "mipmap-xhdpi": (96, 96),
    "mipmap-xxhdpi": (144, 144),
    "mipmap-xxxhdpi": (192, 192)
}

img = Image.open(source_image_path).convert("RGBA")

for folder, (w, h) in sizes.items():
    folder_path = os.path.join(base_res_dir, folder)
    os.makedirs(folder_path, exist_ok=True)
    
    # Clean out any old webp or png files to avoid duplicate resource errors
    for old_file in glob.glob(os.path.join(folder_path, "ic_launcher*")):
        try:
            os.remove(old_file)
        except Exception:
            pass

    resized = img.resize((w, h), Image.Resampling.LANCZOS)
    
    png_path = os.path.join(folder_path, "ic_launcher.png")
    round_png_path = os.path.join(folder_path, "ic_launcher_round.png")
    
    resized.save(png_path, "PNG")
    resized.save(round_png_path, "PNG")
    print(f"Cleaned & generated PNG icons for {folder}: {w}x{h}")

# Also update web favicon in assets
assets_dir = r"c:\Users\ankit\OneDrive\Desktop\project\android-app\app\src\main\assets"
favicon_path = os.path.join(assets_dir, "icon.png")
img.resize((192, 192), Image.Resampling.LANCZOS).save(favicon_path, "PNG")
print("Updated asset icon.png")
