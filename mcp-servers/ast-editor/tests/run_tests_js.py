import os
import sys

# Add parent dir to path so we can import ast_editor
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ast_editor.applier import Applier

def main():
    target_path = os.path.join(os.path.dirname(__file__), 'test_target.js')
    
    print("Testing replace_function_body on LRUCache.get...")
    app = Applier(target_path)
    # Notice we don't supply the enclosing braces if it's the body injection
    new_js_body = "        if (this.items.has(key)) {\n            console.log('Hit');\n            return this.items.get(key);\n        }\n        return null;"
    app.replace_function_body("LRUCache.get", new_js_body)
    
    print("Testing add_method on LRUCache...")
    app2 = Applier(target_path)
    new_js_method = "    set(key, value) {\n        this.items.set(key, value);\n    }"
    app2.add_method("LRUCache", new_js_method)
    
    print("All AST edits executed. Reading target file...")
    with open(target_path, 'r') as f:
        print(f.read())
        
if __name__ == "__main__":
    main()
