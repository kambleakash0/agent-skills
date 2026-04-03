import os
import sys

# Add parent dir to path so we can import ast_editor
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ast_editor.applier import Applier

def main():
    target_path = os.path.join(os.path.dirname(__file__), 'test_target.py')
    
    print("Testing replace_function_body on LRUCache.get...")
    app = Applier(target_path)
    app.replace_function_body("LRUCache.get", "        if key in self.items:\n            print('Hit')\n            return self.items[key]\n        return None")
    
    print("Testing add_method on LRUCache...")
    app2 = Applier(target_path)
    app2.add_method("LRUCache", "    def set(self, key, value):\n        self.items[key] = value")
    
    print("All AST edits executed. Reading target file...")
    with open(target_path, 'r') as f:
        print(f.read())
        
if __name__ == "__main__":
    main()
