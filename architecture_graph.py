from agent.orchestrator import graph
from IPython.display import Image, display
from PIL import Image as PILImage
import io

# Get PNG bytes directly
png_bytes = graph.get_graph().draw_mermaid_png()

# Save bytes to file
with open("my_image.png", "wb") as f:
    f.write(png_bytes)

# Or use PIL for more options
pil_img = PILImage.open(io.BytesIO(png_bytes))
pil_img.save("my_image.png")

# Display
display(Image(png_bytes))