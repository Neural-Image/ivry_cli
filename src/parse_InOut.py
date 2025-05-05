import ast
import yaml
from pathlib import Path
import json


def clean_quotes(value):
    if isinstance(value, str) and value.startswith("'") and value.endswith("'"):
        return value[1:-1]  # Remove surrounding single quotes
    return value

def recoverType(data_type, val_dict):
    if(data_type in ["str", "Path"]): return {**val_dict, **({"max_length": int(val_dict["max_length"])} if "max_length" in val_dict else {})}
    converter = int if data_type == "int" else float
    return {k: converter(v) for k, v in val_dict.items()}

def check_default_validation(config_data):
    """
    Check if any input parameter's validation is missing a default value.
    
    Args:
        config_data (dict): Configuration data containing inputs with validation.
        
    Returns:
        tuple: (bool, str) - (True, None) if all validations have defaults,
                             (False, error_message) otherwise.
    """
    if 'inputs' not in config_data:
        return False, "Error: No 'inputs' field found in configuration"
    
    missing_defaults = []
    
    for i, input_param in enumerate(config_data['inputs']):
        # Check if input has name and validation fields
        if 'name' not in input_param:
            missing_defaults.append(f"Input at index {i} is missing 'name' field")
            continue
            
        name = input_param['name']
        
        # Check if validation exists
        if 'validation' not in input_param:
            missing_defaults.append(f"Input '{name}' is missing 'validation' field")
            continue
            
        # Check if default exists in validation
        validation = input_param['validation']
        if not isinstance(validation, dict):
            missing_defaults.append(f"Input '{name}' has invalid validation format (not a dictionary)")
            continue
            
        if 'default' not in validation:
            missing_defaults.append(f"Input '{name}' is missing 'default' in validation")
    
    if missing_defaults:
        error_message = "The following inputs are missing default values:\n" + "\n".join(missing_defaults)
        return False, error_message
    
    return True, None

def parse_predict(predict_filename, save_type='json'):
    with open(predict_filename, encoding="utf-8") as file:
        source_code = file.read()

    # Parse the source code into an AST
    tree = ast.parse(source_code)


    # Extract the predict method and its input/output types
    class PredictMethodVisitor(ast.NodeVisitor):
        def __init__(self):
            self.inputs = []
            self.output_type = None
            self.validation_rules = []

        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name == "predict":
                # Extract input arguments and their annotations
                for arg in node.args.args:
                    if arg.annotation:
                        self.inputs.append((arg.arg, clean_quotes(ast.unparse(arg.annotation))))

                # Extract return type annotation
                if node.returns:
                    self.output_type = clean_quotes(ast.unparse(node.returns))

                for arg in node.args.defaults:
                    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "Input":
                        # Extract the keyword arguments of Input()
                        self.validation_rules.append({
                            kw.arg: clean_quotes(ast.unparse(kw.value)) for kw in arg.keywords
                        })

    # Create a visitor instance and visit the AST
    visitor = PredictMethodVisitor()
    visitor.visit(tree)

    # Output the extracted input and output types
    inputs = visitor.inputs
    output_type = visitor.output_type
    validation_rules = visitor.validation_rules

    # print("inputs:", inputs)
    # print("outputs:", output_type)
    # print("validations:", validation_rules)
    # import pdb; pdb.set_trace()

    data = {
        "inputs": [ {"name": inp[0], "type": inp[1], "validation": recoverType(inp[1], val)} for inp, val in zip(inputs, validation_rules)],
        "outputs": output_type
    }

    check_result = check_default_validation(data)
 
    if check_result[0] == False:
        return "error, " + check_result[1]
    # Optional: Save YAML to a file
    else:
        if save_type == "yaml":
            with open('predict_signature.yaml', 'w') as file:
                yaml.dump(data, file, default_flow_style=False)
            return "Created predict_signature.yaml"
        elif save_type == "json":
            with open('predict_signature.json', 'w') as file:
                json.dump(data, file)
            return "Created predict_signature.json"

def parse_predict_return(predict_filename, save_type='yaml'):
    with open(predict_filename, encoding="utf-8") as file:
        source_code = file.read()

    # Parse the source code into an AST
    tree = ast.parse(source_code)


    # Extract the predict method and its input/output types
    class PredictMethodVisitor(ast.NodeVisitor):
        def __init__(self):
            self.inputs = []
            self.output_type = None
            self.validation_rules = []

        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name == "predict":
                # Extract input arguments and their annotations
                for arg in node.args.args:
                    if arg.annotation:
                        self.inputs.append((arg.arg, clean_quotes(ast.unparse(arg.annotation))))

                # Extract return type annotation
                if node.returns:
                    self.output_type = clean_quotes(ast.unparse(node.returns))

                for arg in node.args.defaults:
                    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "Input":
                        # Extract the keyword arguments of Input()
                        self.validation_rules.append({
                            kw.arg: clean_quotes(ast.unparse(kw.value)) for kw in arg.keywords
                        })

    # Create a visitor instance and visit the AST
    visitor = PredictMethodVisitor()
    visitor.visit(tree)

    # Output the extracted input and output types
    inputs = visitor.inputs
    output_type = visitor.output_type
    validation_rules = visitor.validation_rules

    # print("inputs:", inputs)
    # print("outputs:", output_type)
    # print("validations:", validation_rules)

    data = {
        "inputs": [ {"name": inp[0], "type": inp[1], "validation": val} for inp, val in zip(inputs, validation_rules)],
        "outputs": output_type
    }

    # Optional: Save YAML to a file
    if save_type == "yaml":
        return data


    elif save_type == "json":
        return data
