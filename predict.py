from cog import BasePredictor, Input, Path
import tempfile
from PIL import Image
from time import sleep

class Predictor(BasePredictor):
    def setup(self):
        """Load the model into memory to make running multiple predictions efficient"""
        pass
    # The arguments and types the model takes as input
    def predict(self,
                image: Path = Input(description="Grayscale input image"),
                prompt: str = Input(default="hello", max_length=1000, description="this is a prompt"),
                steps: int = Input(default=50, ge=0, le=1000, description="steps"),
                guidance_scale: float = Input(default=5.0, ge=0, le=20, description="guidance_scale"),
    ) -> Path:
        print(image)
        self.comfyui_instance()
        img = Image.open(image)
        original_width, original_height = img.size
        sleep(2)
        # Calculate new dimensions (50% of original)
        new_width = original_width // 2
        new_height = original_height // 2
        sleep(2)
        print(12345)
        # Resize the image
        resized_img = img.resize((new_width, new_height))
        sleep(2)
        print(image.stem)
        output_path = Path(tempfile.mkdtemp()) / f"{image.stem}_downscale.jpg"
        resized_img.save(output_path)        
        return output_path
