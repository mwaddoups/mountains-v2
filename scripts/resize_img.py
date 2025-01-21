from PIL import Image

with Image.open("images/cmc_full.png") as im:
    new_width = 512
    new_height = im.height // (im.width // new_width)
    resized = im.resize((new_width, new_height))
    resized.save(f"images/cmc_full_{new_width}.png")
