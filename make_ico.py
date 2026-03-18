from PIL import Image
img = Image.open("assets/icons/tokens/very_rare.png").convert("RGBA")
img.save(
    "assets/icons/tokens/very_rare.ico",
    format="ICO",
    sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)],
)
print("ICO created.")

