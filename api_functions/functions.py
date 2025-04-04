from pydantic import BaseModel

def tool1():
    return "Tool 1 executed"
def tool2():
    return "Tool 2 executed"

# Create a dictionary with the functions in the same file
functions = {
    'tool1': tool1,
    'tool2': tool2,
    "tool3": tool2,
}