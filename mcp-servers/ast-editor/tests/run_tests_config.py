import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ast_editor.applier import Applier

def main():
    json_path = os.path.join(os.path.dirname(__file__), 'test_target.json')
    yaml_path = os.path.join(os.path.dirname(__file__), 'test_target.yaml')
    toml_path = os.path.join(os.path.dirname(__file__), 'test_target.toml')
    
    print("Testing replace_value on JSON: dependencies.tree-sitter...")
    app_j = Applier(json_path)
    app_j.replace_value("dependencies.tree-sitter", "\"^0.23.0\"")
    
    print("\nTesting replace_value on YAML: project.version...")
    app_y = Applier(yaml_path)
    app_y.replace_value("project.version", "\"2.0.0\"")

    print("\nTesting replace_value on TOML: project.name...")
    app_t = Applier(toml_path)
    app_t.replace_value("project.name", "\"ast-editor-supercharged\"")
    
    print("\nAll config AST edits executed. Reading JSON file...")
    with open(json_path, 'r') as f:
        print(f.read())
        
    print("\nReading YAML file...")
    with open(yaml_path, 'r') as f:
        print(f.read())

    print("\nReading TOML file...")
    with open(toml_path, 'r') as f:
        print(f.read())
        
if __name__ == "__main__":
    main()
