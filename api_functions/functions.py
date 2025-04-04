from pydantic import BaseModel
import asyncio

async def tool_1(image):
    await asyncio.sleep(2)
    return f"Tool 1 executed:{image}"

def tool_2(initial_param_1):
    print("tool_2:", initial_param_1)
    return {
        "scale": 3.14
    }

# Create a dictionary with the functions in the same file
functions = {
    'tool_1': tool_1,
    'tool_2': tool_2
}