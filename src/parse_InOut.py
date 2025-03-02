import ast
import yaml
from pathlib import Path
import json


def clean_quotes(value):
    if isinstance(value, str) and value.startswith("'") and value.endswith("'"):
        return value[1:-1]  # Remove surrounding single quotes
    return value


def parse_predict(predict_filename, save_type='yaml'):
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
        with open('predict_signature.yaml', 'w') as file:
            yaml.dump(data, file, default_flow_style=False)

    elif save_type == "json":
        with open('predict_signature.json', 'w') as file:
            json.dump(data, file)


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
