from PIL import Image

with Image.open("images/climbing.png") as im:
    new_width = 1024
    new_height = im.height // (im.width // new_width)
    resized = im.resize((new_width, new_height))
    resized.save(f"images/climbing_{new_width}.png")
