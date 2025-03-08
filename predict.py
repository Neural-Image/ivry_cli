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
                image: Path = Input(default="image.jpg"),
                prompt: str = Input(default="hello"),
                steps: int = Input(default=50),
                guidance_scale: float = Input(default=5.0),
    ) -> list[Path]:
        print("input image:", image)
        img = Image.open(image)
        original_width, original_height = img.size
        sleep(2)
        # Calculate new dimensions (50% of original)
        new_width = original_width // 2
        new_height = original_height // 2
        sleep(2)
        print(12345)
        # Resize the image
        # raise Exception("my error")
        resized_img = img.resize((new_width, new_height))
        sleep(4)
        print(image.stem)
        # raise ValueError("I'm a value erro")
        output_path = Path(tempfile.mkdtemp()) / f"{image.stem}_downscale.jpg"
        resized_img.save(output_path)        
        return [output_path]
