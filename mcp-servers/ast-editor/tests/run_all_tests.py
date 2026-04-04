import os
import sys
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ast_editor.applier import Applier

TESTS_DIR = os.path.dirname(__file__)
PASS = 0
FAIL = 0

# ──────────────────────────────────────────────
# Fixture helpers
# ──────────────────────────────────────────────

FIXTURES = {
    "py": {
        "file": "test_target.py",
        "content": """class LRUCache:
    def __init__(self):
        self.capacity = 10
        self.items = {}

    def get(self, key):
        return self.items.get(key)
""",
    },
    "py_decorated": {
        "file": "test_target_decorated.py",
        "content": """class MyApp:
    @staticmethod
    def hello():
        return "hello"

    @property
    def name(self):
        return self._name
""",
    },
    "js": {
        "file": "test_target.js",
        "content": """class LRUCache {
    constructor() {
        this.capacity = 10;
        this.items = new Map();
    }

    get(key) {
        return this.items.get(key);
    }
}
""",
    },
    "ts": {
        "file": "test_target.ts",
        "content": """class LRUCache {
    private capacity: number;
    private items: Map<string, number>;

    constructor() {
        this.capacity = 10;
        this.items = new Map();
    }

    get(key: string): number | undefined {
        return this.items.get(key);
    }
}
""",
    },
    "json": {
        "file": "test_target.json",
        "content": """{
    "project": {
        "name": "ast-editor",
        "version": "1.0.0"
    },
    "dependencies": {
        "tree-sitter": "^0.21.0"
    }
}
""",
    },
    "yaml": {
        "file": "test_target.yaml",
        "content": """project:
  name: "ast-editor"
  version: "1.0.0"
dependencies:
  tree-sitter: "^0.21.0"
""",
    },
    "toml": {
        "file": "test_target.toml",
        "content": """[project]
name = "ast-editor"
version = "1.0.0"

[dependencies]
tree-sitter = "^0.21.0"
""",
    },
    "c": {
        "file": "test_target.c",
        "content": """#include <stdio.h>

int add(int a, int b) {
    return a + b;
}

int multiply(int a, int b) {
    return a * b;
}
""",
    },
    "cpp": {
        "file": "test_target.cpp",
        "content": """#include <iostream>

class Calculator {
public:
    int add(int a, int b) {
        return a + b;
    }

    int subtract(int a, int b) {
        return a - b;
    }
};

int freeFunc(int x) {
    return x * 2;
}
""",
    },
}


def reset_fixture(lang: str):
    """Write fixture back to disk so tests are idempotent."""
    fixture = FIXTURES[lang]
    path = os.path.join(TESTS_DIR, fixture["file"])
    with open(path, "w") as f:
        f.write(fixture["content"])
    return path


def read_file(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def check(label: str, result: str, expected_substring: str):
    global PASS, FAIL
    if expected_substring in result:
        print(f"  [PASS] {label}")
        PASS += 1
    else:
        print(f"  [FAIL] {label}")
        print(f"     Expected to find: {repr(expected_substring)}")
        print(f"     Got:\n{result}")
        FAIL += 1


# ──────────────────────────────────────────────
# Python tests
# ──────────────────────────────────────────────

def test_python():
    print("\n═══ Python (.py) ═══")

    # Test replace_function_body
    path = reset_fixture("py")
    app = Applier(path)
    app.replace_function_body(
        "LRUCache.get",
        "        if key in self.items:\n            return self.items[key]\n        return None"
    )
    result = read_file(path)
    check("replace_function_body: new body injected", result, "if key in self.items:")
    check("replace_function_body: old body removed", result, "return None")
    check("replace_function_body: class intact", result, "class LRUCache:")

    # Test add_method
    path = reset_fixture("py")
    app = Applier(path)
    app.add_method("LRUCache", "    def set(self, key, value):\n        self.items[key] = value")
    result = read_file(path)
    check("add_method: method added", result, "def set(self, key, value):")
    check("add_method: original get intact", result, "def get(self, key):")


# ──────────────────────────────────────────────
# Python decorated function tests
# ──────────────────────────────────────────────

def test_python_decorated():
    print("\n═══ Python (decorated) ═══")

    # Test replace_function on a decorated function — should replace decorator + def
    path = reset_fixture("py_decorated")
    app = Applier(path)
    app.replace_function(
        "MyApp.hello",
        "    @classmethod\n    def hello(cls):\n        return \"hi from classmethod\""
    )
    result = read_file(path)
    check("replace_function: new decorator present", result, "@classmethod")
    check("replace_function: new body present", result, "hi from classmethod")
    check("replace_function: no orphaned @staticmethod", "PASS" if "@staticmethod" not in result else "FAIL", "PASS")

    # Test replace_function_body on a decorated function — should only replace body
    path = reset_fixture("py_decorated")
    app = Applier(path)
    app.replace_function_body(
        "MyApp.name",
        "        return \"fixed_name\""
    )
    result = read_file(path)
    check("replace_function_body: decorator preserved", result, "@property")
    check("replace_function_body: new body present", result, "fixed_name")
    check("replace_function_body: signature preserved", result, "def name(self):")

    # Test delete_symbol on a decorated function — should remove decorator + def
    path = reset_fixture("py_decorated")
    app = Applier(path)
    app.delete_symbol("MyApp.hello")
    result = read_file(path)
    check("delete_symbol: @staticmethod removed", "PASS" if "@staticmethod" not in result else "FAIL", "PASS")
    check("delete_symbol: def hello removed", "PASS" if "def hello" not in result else "FAIL", "PASS")
    check("delete_symbol: other method intact", result, "@property")


# ──────────────────────────────────────────────
# JavaScript tests
# ──────────────────────────────────────────────

def test_javascript():
    print("\n═══ JavaScript (.js) ═══")

    path = reset_fixture("js")
    app = Applier(path)
    app.replace_function_body(
        "LRUCache.get",
        "        if (this.items.has(key)) {\n            return this.items.get(key);\n        }\n        return null;"
    )
    result = read_file(path)
    check("replace_function_body: new body injected", result, "this.items.has(key)")
    check("replace_function_body: returns null", result, "return null;")

    path = reset_fixture("js")
    app = Applier(path)
    app.add_method("LRUCache", "    set(key, value) {\n        this.items.set(key, value);\n    }")
    result = read_file(path)
    check("add_method: set method added", result, "set(key, value)")
    check("add_method: closing brace intact", result, "}")
    # Verify blank line before closing brace
    lines = result.splitlines()
    closing_idx = next(i for i in reversed(range(len(lines))) if lines[i].strip() == "}")
    check("add_method: blank line before closing brace", lines[closing_idx - 1].strip(), "")


# ──────────────────────────────────────────────
# TypeScript tests
# ──────────────────────────────────────────────

def test_typescript():
    print("\n═══ TypeScript (.ts) ═══")

    path = reset_fixture("ts")
    app = Applier(path)
    app.replace_function_body(
        "LRUCache.get",
        "        if (this.items.has(key)) {\n            return this.items.get(key);\n        }\n        return undefined;"
    )
    result = read_file(path)
    check("replace_function_body: new body injected", result, "this.items.has(key)")
    check("replace_function_body: returns undefined", result, "return undefined;")
    check("replace_function_body: type annotation preserved", result, "get(key: string): number | undefined")

    path = reset_fixture("ts")
    app = Applier(path)
    app.add_method("LRUCache", "    set(key: string, value: number): void {\n        this.items.set(key, value);\n    }")
    result = read_file(path)
    check("add_method: typed set method added", result, "set(key: string, value: number): void")


# ──────────────────────────────────────────────
# JSON tests
# ──────────────────────────────────────────────

def test_json():
    print("\n═══ JSON (.json) ═══")

    path = reset_fixture("json")
    app = Applier(path)
    app.replace_value("dependencies.tree-sitter", "\"^0.23.0\"")
    result = read_file(path)
    check("replace_value: version updated", result, "^0.23.0")
    check("replace_value: project name untouched", result, "\"name\": \"ast-editor\"")
    check("replace_value: structure intact", result, "\"dependencies\"")


# ──────────────────────────────────────────────
# YAML tests
# ──────────────────────────────────────────────

def test_yaml():
    print("\n═══ YAML (.yaml) ═══")

    path = reset_fixture("yaml")
    app = Applier(path)
    app.replace_value("project.version", "\"2.0.0\"")
    result = read_file(path)
    check("replace_value: version updated", result, "2.0.0")
    check("replace_value: name untouched", result, "name: \"ast-editor\"")
    check("replace_value: dependencies untouched", result, "tree-sitter: \"^0.21.0\"")


# ──────────────────────────────────────────────
# TOML tests
# ──────────────────────────────────────────────

def test_toml():
    print("\n═══ TOML (.toml) ═══")

    path = reset_fixture("toml")
    app = Applier(path)
    app.replace_value("project.name", "\"ast-editor-pro\"")
    result = read_file(path)
    check("replace_value: name updated", result, "ast-editor-pro")
    check("replace_value: version untouched", result, 'version = "1.0.0"')
    check("replace_value: deps untouched", result, 'tree-sitter = "^0.21.0"')


# ──────────────────────────────────────────────
# C tests
# ──────────────────────────────────────────────

def test_c():
    print("\n═══ C (.c) ═══")

    # replace_function_body on free function
    path = reset_fixture("c")
    app = Applier(path)
    app.replace_function_body(
        "add",
        "    int result = a + b;\n    return result;"
    )
    result = read_file(path)
    check("replace_function_body: new body injected", result, "int result = a + b;")
    check("replace_function_body: signature preserved", result, "int add(int a, int b)")
    check("replace_function_body: other function intact", result, "int multiply(int a, int b)")

    # replace_function: replace entire function including signature
    path = reset_fixture("c")
    app = Applier(path)
    app.replace_function(
        "multiply",
        "long multiply(long a, long b) {\n    return a * b;\n}"
    )
    result = read_file(path)
    check("replace_function: new signature applied", result, "long multiply(long a, long b)")
    check("replace_function: add() untouched", result, "int add(int a, int b)")

    # delete_symbol: remove a function
    path = reset_fixture("c")
    app = Applier(path)
    app.delete_symbol("multiply")
    result = read_file(path)
    check("delete_symbol: multiply removed", "PASS" if "multiply" not in result else "FAIL", "PASS")
    check("delete_symbol: add intact", result, "int add(int a, int b)")


# ──────────────────────────────────────────────
# C++ tests
# ──────────────────────────────────────────────

def test_cpp():
    print("\n═══ C++ (.cpp) ═══")

    # replace_function_body on a class method
    path = reset_fixture("cpp")
    app = Applier(path)
    app.replace_function_body(
        "Calculator.add",
        "        return (a + b) * 2;"
    )
    result = read_file(path)
    check("replace_function_body: new body injected", result, "(a + b) * 2")
    check("replace_function_body: signature preserved", result, "int add(int a, int b)")
    check("replace_function_body: other method intact", result, "int subtract(int a, int b)")

    # replace_function_body on free function
    path = reset_fixture("cpp")
    app = Applier(path)
    app.replace_function_body(
        "freeFunc",
        "    return x + x;"
    )
    result = read_file(path)
    check("replace_function_body (free): body injected", result, "return x + x;")
    check("replace_function_body (free): signature preserved", result, "int freeFunc(int x)")

    # add_method on class
    path = reset_fixture("cpp")
    app = Applier(path)
    app.add_method(
        "Calculator",
        "    int divide(int a, int b) {\n        return a / b;\n    }"
    )
    result = read_file(path)
    check("add_method: new method present", result, "int divide(int a, int b)")
    check("add_method: existing method intact", result, "int add(int a, int b)")
    check("add_method: closing `};` preserved", result, "};")

    # delete_symbol on a class method
    path = reset_fixture("cpp")
    app = Applier(path)
    app.delete_symbol("Calculator.subtract")
    result = read_file(path)
    check("delete_symbol: subtract removed", "PASS" if "subtract" not in result else "FAIL", "PASS")
    check("delete_symbol: add intact", result, "int add(int a, int b)")


# ──────────────────────────────────────────────
# Phase 1: add_import / remove_import
# ──────────────────────────────────────────────

def test_imports():
    print("\n═══ Imports (add/remove) ═══")

    # Python: add a new import, verify duplicate detection, remove it
    path = reset_fixture("py")
    app = Applier(path)
    app.add_import("import os")
    result = read_file(path)
    check("py add_import: new import present", result, "import os")

    # Duplicate should not add a second line
    app2 = Applier(path)
    app2.add_import("import os")
    result2 = read_file(path)
    check("py add_import: duplicate skipped", "PASS" if result2.count("import os") == 1 else "FAIL", "PASS")

    app3 = Applier(path)
    app3.remove_import("import os")
    result3 = read_file(path)
    check("py remove_import: import removed", "PASS" if "import os" not in result3 else "FAIL", "PASS")

    # JavaScript: add an import at top of file
    path = reset_fixture("js")
    app = Applier(path)
    app.add_import("import foo from 'bar';")
    result = read_file(path)
    check("js add_import: import present", result, "import foo from 'bar';")

    # C: add an include
    path = reset_fixture("c")
    app = Applier(path)
    app.add_import("#include <stdlib.h>")
    result = read_file(path)
    check("c add_import: include present", result, "#include <stdlib.h>")
    check("c add_import: original include still present", result, "#include <stdio.h>")


# ──────────────────────────────────────────────
# Phase 1: add_function / add_class
# ──────────────────────────────────────────────

def test_add_function_class():
    print("\n═══ add_top_level (functions + classes) ═══")

    # Python: append a new top-level function
    path = reset_fixture("py")
    app = Applier(path)
    app.add_top_level("def new_helper():\n    return 42")
    result = read_file(path)
    check("py add_top_level: new function appended", result, "def new_helper():")
    check("py add_top_level: existing class intact", result, "class LRUCache:")

    # Python: append a new top-level class
    path = reset_fixture("py")
    app = Applier(path)
    app.add_top_level("class Extra:\n    pass")
    result = read_file(path)
    check("py add_top_level: new class appended", result, "class Extra:")

    # C: append a new function
    path = reset_fixture("c")
    app = Applier(path)
    app.add_top_level("int subtract(int a, int b) {\n    return a - b;\n}")
    result = read_file(path)
    check("c add_top_level: subtract appended", result, "int subtract(int a, int b)")
    check("c add_top_level: add intact", result, "int add(int a, int b)")


# ──────────────────────────────────────────────
# Phase 1: add_key / delete_key
# ──────────────────────────────────────────────

def test_add_delete_key():
    print("\n═══ add_key / delete_key (config files) ═══")

    # JSON: add a new key to dependencies, then delete it
    path = reset_fixture("json")
    app = Applier(path)
    app.add_key("dependencies", "mcp", "\"^1.2.0\"")
    result = read_file(path)
    check("json add_key: new key present", result, '"mcp": "^1.2.0"')
    check("json add_key: existing key intact", result, '"tree-sitter": "^0.21.0"')

    app2 = Applier(path)
    app2.delete_key("dependencies.mcp")
    result2 = read_file(path)
    check("json delete_key: key removed", "PASS" if '"mcp"' not in result2 else "FAIL", "PASS")
    check("json delete_key: sibling intact", result2, '"tree-sitter": "^0.21.0"')

    # YAML: add a new key under project
    path = reset_fixture("yaml")
    app = Applier(path)
    app.add_key("project", "author", '"akash"')
    result = read_file(path)
    check("yaml add_key: new key present", result, 'author: "akash"')
    check("yaml add_key: existing key intact", result, 'version: "1.0.0"')

    app2 = Applier(path)
    app2.delete_key("project.author")
    result2 = read_file(path)
    check("yaml delete_key: key removed", "PASS" if "author" not in result2 else "FAIL", "PASS")

    # TOML: add a new key under [project]
    path = reset_fixture("toml")
    app = Applier(path)
    app.add_key("project", "author", '"akash"')
    result = read_file(path)
    check("toml add_key: new key present", result, 'author = "akash"')
    check("toml add_key: existing key intact", result, 'version = "1.0.0"')

    app2 = Applier(path)
    app2.delete_key("project.author")
    result2 = read_file(path)
    check("toml delete_key: key removed", "PASS" if "author" not in result2 else "FAIL", "PASS")


# ──────────────────────────────────────────────
# Phase 2: append_to_array / remove_from_array
# ──────────────────────────────────────────────

def test_array_ops():
    print("\n═══ append_to_array / remove_from_array ═══")

    # JSON: add array fixture inline by rewriting
    path = os.path.join(TESTS_DIR, "test_array.json")
    with open(path, "w") as f:
        f.write('{\n  "deps": [\n    "a",\n    "b"\n  ]\n}\n')
    app = Applier(path)
    app.append_to_array("deps", '"c"')
    result = read_file(path)
    check("json append_to_array: new element present", result, '"c"')
    check("json append_to_array: existing elements intact", result, '"a"')

    app2 = Applier(path)
    app2.remove_from_array("deps", '"b"')
    result2 = read_file(path)
    check("json remove_from_array: element removed", "PASS" if '"b"' not in result2 else "FAIL", "PASS")
    check("json remove_from_array: other elements intact", result2, '"a"')
    os.remove(path)

    # TOML: multi-line array
    path = os.path.join(TESTS_DIR, "test_array.toml")
    with open(path, "w") as f:
        f.write('[project]\ndeps = [\n    "a",\n    "b"\n]\n')
    app = Applier(path)
    app.append_to_array("project.deps", '"c"')
    result = read_file(path)
    check("toml append_to_array: new element present", result, '"c"')
    os.remove(path)

    # YAML block sequence
    path = os.path.join(TESTS_DIR, "test_array.yaml")
    with open(path, "w") as f:
        f.write('deps:\n  - a\n  - b\n')
    app = Applier(path)
    app.append_to_array("deps", "c")
    result = read_file(path)
    check("yaml append_to_array: new element present", result, "- c")
    check("yaml append_to_array: existing elements intact", result, "- a")

    app2 = Applier(path)
    app2.remove_from_array("deps", "b")
    result2 = read_file(path)
    check("yaml remove_from_array: element removed", "PASS" if "- b" not in result2 else "FAIL", "PASS")
    os.remove(path)


# ──────────────────────────────────────────────
# Phase 2: add_field
# ──────────────────────────────────────────────

def test_add_field():
    print("\n═══ add_field ═══")

    # Python: add a class attribute
    path = reset_fixture("py")
    app = Applier(path)
    app.add_field("LRUCache", "    version = \"1.0\"")
    result = read_file(path)
    check("py add_field: field present", result, 'version = "1.0"')
    check("py add_field: existing method intact", result, "def get(self, key):")

    # C++: add a member variable
    path = reset_fixture("cpp")
    app = Applier(path)
    app.add_field("Calculator", "    int counter;")
    result = read_file(path)
    check("cpp add_field: field present", result, "int counter;")
    check("cpp add_field: existing method intact", result, "int add(int a, int b)")


# ──────────────────────────────────────────────
# Phase 2: replace_signature
# ──────────────────────────────────────────────

def test_replace_signature():
    print("\n═══ replace_signature ═══")

    # Python: change parameters
    path = reset_fixture("py")
    app = Applier(path)
    app.replace_signature("LRUCache.get", "    def get(self, key, default=None):")
    result = read_file(path)
    check("py replace_signature: new params applied", result, "def get(self, key, default=None):")
    check("py replace_signature: body preserved", result, "return self.items.get(key)")

    # JS: change parameters
    path = reset_fixture("js")
    app = Applier(path)
    app.replace_signature("LRUCache.get", "    get(key, defaultValue)")
    result = read_file(path)
    check("js replace_signature: new params applied", result, "get(key, defaultValue)")
    check("js replace_signature: body preserved", result, "return this.items.get(key);")

    # C: change return type
    path = reset_fixture("c")
    app = Applier(path)
    app.replace_signature("add", "long add(long a, long b)")
    result = read_file(path)
    check("c replace_signature: new return type applied", result, "long add(long a, long b)")
    check("c replace_signature: body preserved", result, "return a + b;")


# ──────────────────────────────────────────────
# Phase 3: list_symbols / get_signature
# ──────────────────────────────────────────────

def test_list_symbols():
    print("\n═══ list_symbols ═══")

    path = reset_fixture("py")
    app = Applier(path)
    outline = app.list_symbols()
    check("py list_symbols: class listed", outline, "class LRUCache")
    check("py list_symbols: method listed", outline, "method LRUCache.get")
    check("py list_symbols: includes line numbers", outline, "(line ")

    path = reset_fixture("cpp")
    app = Applier(path)
    outline = app.list_symbols()
    check("cpp list_symbols: class listed", outline, "Calculator")
    check("cpp list_symbols: method listed", outline, "method Calculator.add")
    check("cpp list_symbols: free function listed", outline, "function freeFunc")


def test_get_signature():
    print("\n═══ get_signature ═══")

    path = reset_fixture("py")
    app = Applier(path)
    sig = app.get_signature("LRUCache.get")
    check("py get_signature: correct sig returned", sig, "def get(self, key):")

    path = reset_fixture("cpp")
    app = Applier(path)
    sig = app.get_signature("Calculator.add")
    check("cpp get_signature: correct sig returned", sig, "int add(int a, int b)")

    path = reset_fixture("c")
    app = Applier(path)
    sig = app.get_signature("multiply")
    check("c get_signature: correct sig returned", sig, "int multiply(int a, int b)")


# ──────────────────────────────────────────────
# Phase A: prepend_to_body / append_to_body
# ──────────────────────────────────────────────

def test_body_insertions():
    print("\n═══ prepend_to_body / append_to_body ═══")

    # Python: prepend a log line to a function body
    path = reset_fixture("py")
    app = Applier(path)
    app.prepend_to_body("LRUCache.get", "        print(f'getting {key}')")
    result = read_file(path)
    check("py prepend_to_body: new line at top", result, "print(f'getting {key}')")
    check("py prepend_to_body: original body preserved", result, "return self.items.get(key)")

    # Python: append a log line
    path = reset_fixture("py")
    app = Applier(path)
    app.append_to_body("LRUCache.get", "        # end")
    result = read_file(path)
    check("py append_to_body: new line at bottom", result, "# end")
    check("py append_to_body: original body preserved", result, "return self.items.get(key)")

    # JS: prepend and append
    path = reset_fixture("js")
    app = Applier(path)
    app.prepend_to_body("LRUCache.get", "        console.log('get');")
    result = read_file(path)
    check("js prepend_to_body: new line at top", result, "console.log('get');")
    check("js prepend_to_body: original body preserved", result, "return this.items.get(key);")

    # C: append to a free function
    path = reset_fixture("c")
    app = Applier(path)
    app.append_to_body("add", "    /* end marker */")
    result = read_file(path)
    check("c append_to_body: marker present", result, "/* end marker */")
    check("c append_to_body: original return preserved", result, "return a + b;")


# ──────────────────────────────────────────────
# Phase A: insert_before / insert_after / add_statement
# ──────────────────────────────────────────────

def test_sibling_placement():
    print("\n═══ insert_before / insert_after / add_top_level (statements) ═══")

    # Python: insert_before a class
    path = reset_fixture("py")
    app = Applier(path)
    app.insert_before("LRUCache", "CONST = 42")
    result = read_file(path)
    lines = result.splitlines()
    const_idx = next(i for i, l in enumerate(lines) if "CONST = 42" in l)
    class_idx = next(i for i, l in enumerate(lines) if "class LRUCache" in l)
    check("py insert_before: const before class", "PASS" if const_idx < class_idx else "FAIL", "PASS")

    # Python: insert_after a class
    path = reset_fixture("py")
    app = Applier(path)
    app.insert_after("LRUCache", "OTHER = 1")
    result = read_file(path)
    lines = result.splitlines()
    class_idx = next(i for i, l in enumerate(lines) if "class LRUCache" in l)
    other_idx = next(i for i, l in enumerate(lines) if "OTHER = 1" in l)
    check("py insert_after: const after class", "PASS" if other_idx > class_idx else "FAIL", "PASS")

    # C: insert_after a function
    path = reset_fixture("c")
    app = Applier(path)
    app.insert_after("add", "int middle() { return 0; }")
    result = read_file(path)
    lines = result.splitlines()
    add_end = max(i for i, l in enumerate(lines) if "return a + b;" in l)
    middle_idx = next(i for i, l in enumerate(lines) if "int middle()" in l)
    check("c insert_after: middle after add", "PASS" if middle_idx > add_end else "FAIL", "PASS")

    # Python: add_top_level for a constant
    path = reset_fixture("py")
    app = Applier(path)
    app.add_top_level("TAIL_CONST = 99")
    result = read_file(path)
    check("py add_top_level: const appended", result, "TAIL_CONST = 99")
    check("py add_top_level: original class intact", result, "class LRUCache:")


# ──────────────────────────────────────────────
# Phase B: Python dict/list literal ops
# ──────────────────────────────────────────────

def test_python_literals():
    print("\n═══ add_key / delete_key / append_to_array / remove_from_array on Python literals ═══")

    # Set up a file with a dict and a list at module level
    path = os.path.join(TESTS_DIR, "test_literals.py")
    with open(path, "w") as f:
        f.write('CONFIG = {\n    "a": 1,\n    "b": 2,\n}\n\nITEMS = [\n    "x",\n    "y",\n]\n')

    # add_key on a Python dict
    app = Applier(path)
    app.add_key("CONFIG", '"c"', "3")
    result = read_file(path)
    check("py add_key (dict): new entry present", result, '"c": 3')
    check("py add_key (dict): existing entry intact", result, '"a": 1')

    # delete_key on a Python dict (via 'DictName.keyExpr')
    app2 = Applier(path)
    app2.delete_key('CONFIG."b"')
    result2 = read_file(path)
    check("py delete_key (dict): entry removed", "PASS" if '"b": 2' not in result2 else "FAIL", "PASS")
    check("py delete_key (dict): sibling intact", result2, '"a": 1')

    # append_to_array on a Python list
    app3 = Applier(path)
    app3.append_to_array("ITEMS", '"z"')
    result3 = read_file(path)
    check("py append_to_array (list): new item present", result3, '"z"')
    check("py append_to_array (list): existing items intact", result3, '"x"')

    # remove_from_array on a Python list
    app4 = Applier(path)
    app4.remove_from_array("ITEMS", '"y"')
    result4 = read_file(path)
    check("py remove_from_array (list): item removed", "PASS" if '"y"' not in result4 else "FAIL", "PASS")
    check("py remove_from_array (list): other items intact", result4, '"x"')

    os.remove(path)


# ──────────────────────────────────────────────
# Phase B: import-name editing
# ──────────────────────────────────────────────

def test_import_names():
    print("\n═══ add_import_name / remove_import_name ═══")

    # Set up a file with a from-import
    path = os.path.join(TESTS_DIR, "test_imports_names.py")
    with open(path, "w") as f:
        f.write('from typing import Optional, List\nimport os\n')

    # add_import_name
    app = Applier(path)
    app.add_import_name("typing", "Union")
    result = read_file(path)
    check("py add_import_name: new name present", result, "Union")
    check("py add_import_name: existing names intact", result, "Optional")
    check("py add_import_name: single line", result, "from typing import Optional, List, Union")

    # Duplicate should be a no-op
    app2 = Applier(path)
    app2.add_import_name("typing", "Optional")
    result2 = read_file(path)
    check("py add_import_name: duplicate skipped", "PASS" if result2.count("Optional") == 1 else "FAIL", "PASS")

    # remove_import_name
    app3 = Applier(path)
    app3.remove_import_name("typing", "List")
    result3 = read_file(path)
    check("py remove_import_name: name removed", "PASS" if "List" not in result3 else "FAIL", "PASS")
    check("py remove_import_name: other names intact", result3, "Optional")

    os.remove(path)


# ──────────────────────────────────────────────
# Phase C: Parameter editing
# ──────────────────────────────────────────────

def test_parameter_ops():
    print("\n═══ add_parameter / remove_parameter ═══")

    # Python: add a parameter at end
    path = reset_fixture("py")
    app = Applier(path)
    app.add_parameter("LRUCache.get", "default=None")
    result = read_file(path)
    check("py add_parameter: new param present", result, "default=None")
    check("py add_parameter: existing param intact", result, "def get(self, key, default=None):")

    # Python: remove a parameter by name
    path = reset_fixture("py")
    app = Applier(path)
    app.add_parameter("LRUCache.get", "extra=1")
    app2 = Applier(path)
    app2.remove_parameter("LRUCache.get", "extra")
    result = read_file(path)
    check("py remove_parameter: param removed", "PASS" if "extra" not in result else "FAIL", "PASS")
    check("py remove_parameter: original param intact", result, "def get(self, key):")

    # C: add a parameter to a function
    path = reset_fixture("c")
    app = Applier(path)
    app.add_parameter("add", "int c")
    result = read_file(path)
    check("c add_parameter: new param present", result, "int c")
    check("c add_parameter: existing params intact", result, "int add(int a, int b, int c)")

    # C: remove a parameter
    path = reset_fixture("c")
    app = Applier(path)
    app.remove_parameter("add", "b")
    result = read_file(path)
    check("c remove_parameter: param removed", result, "int add(int a)")


# ──────────────────────────────────────────────
# Phase D: Comment ops
# ──────────────────────────────────────────────

def test_comment_ops():
    print("\n═══ add_comment_before / remove_leading_comment / replace_leading_comment ═══")

    # Python: add a comment before a function
    path = reset_fixture("py")
    app = Applier(path)
    app.add_comment_before("LRUCache.get", "    # Get an item by key")
    result = read_file(path)
    check("py add_comment_before: comment present", result, "# Get an item by key")
    check("py add_comment_before: function intact", result, "def get(self, key):")

    # Verify the comment is immediately before the def
    lines = result.splitlines()
    def_idx = next(i for i, l in enumerate(lines) if "def get(self, key):" in l)
    check("py add_comment_before: comment on prior line", lines[def_idx - 1].strip(), "# Get an item by key")

    # Python: remove the leading comment we just added
    app2 = Applier(path)
    app2.remove_leading_comment("LRUCache.get")
    result2 = read_file(path)
    check("py remove_leading_comment: comment removed", "PASS" if "# Get an item by key" not in result2 else "FAIL", "PASS")
    check("py remove_leading_comment: function intact", result2, "def get(self, key):")

    # Python: replace_leading_comment
    path = reset_fixture("py")
    app = Applier(path)
    app.add_comment_before("LRUCache.get", "    # Old comment")
    app2 = Applier(path)
    app2.replace_leading_comment("LRUCache.get", "    # New comment")
    result = read_file(path)
    check("py replace_leading_comment: new comment present", result, "# New comment")
    check("py replace_leading_comment: old comment gone", "PASS" if "# Old comment" not in result else "FAIL", "PASS")

    # JS: add and remove a line comment
    path = reset_fixture("js")
    app = Applier(path)
    app.add_comment_before("LRUCache.get", "    // Get item by key")
    result = read_file(path)
    check("js add_comment_before: comment present", result, "// Get item by key")
    app2 = Applier(path)
    app2.remove_leading_comment("LRUCache.get")
    result2 = read_file(path)
    check("js remove_leading_comment: comment removed", "PASS" if "// Get item by key" not in result2 else "FAIL", "PASS")

    # TypeScript: add and remove
    path = reset_fixture("ts")
    app = Applier(path)
    app.add_comment_before("LRUCache.get", "    // TS doc comment")
    result = read_file(path)
    check("ts add_comment_before: comment present", result, "// TS doc comment")

    # C: line comment add + remove
    path = reset_fixture("c")
    app = Applier(path)
    app.add_comment_before("add", "// Adds two integers")
    result = read_file(path)
    check("c add_comment_before: comment present", result, "// Adds two integers")
    app2 = Applier(path)
    app2.remove_leading_comment("add")
    result2 = read_file(path)
    check("c remove_leading_comment: line comment removed", "PASS" if "Adds two integers" not in result2 else "FAIL", "PASS")

    # C: single-line block comment /* ... */
    path = os.path.join(TESTS_DIR, "test_block_c.c")
    with open(path, "w") as f:
        f.write("/* Doubles an integer */\nint dbl(int x) {\n    return x * 2;\n}\n")
    app = Applier(path)
    app.remove_leading_comment("dbl")
    result = read_file(path)
    check("c remove_leading_comment: single-line block removed", "PASS" if "Doubles an integer" not in result else "FAIL", "PASS")
    check("c remove_leading_comment: function intact", result, "int dbl(int x)")
    os.remove(path)

    # C: multi-line block comment /* ... */
    path = os.path.join(TESTS_DIR, "test_block_multi.c")
    with open(path, "w") as f:
        f.write("/*\n * Multi-line block\n * comment\n */\nint foo(int x) {\n    return x;\n}\n")
    app = Applier(path)
    app.remove_leading_comment("foo")
    result = read_file(path)
    check("c remove_leading_comment: multi-line block removed", "PASS" if "Multi-line block" not in result else "FAIL", "PASS")
    check("c remove_leading_comment: closing */ removed", "PASS" if " */" not in result else "FAIL", "PASS")
    check("c remove_leading_comment: function intact", result, "int foo(int x)")
    os.remove(path)

    # C++: mixed line + block comments
    path = os.path.join(TESTS_DIR, "test_block_cpp.cpp")
    with open(path, "w") as f:
        f.write("// line comment\n/* block */\nint bar() {\n    return 0;\n}\n")
    app = Applier(path)
    app.remove_leading_comment("bar")
    result = read_file(path)
    check("cpp remove_leading_comment: line comment removed", "PASS" if "line comment" not in result else "FAIL", "PASS")
    check("cpp remove_leading_comment: block comment removed", "PASS" if "/* block */" not in result else "FAIL", "PASS")
    os.remove(path)

    # YAML: add and remove comment
    path = reset_fixture("yaml")
    app = Applier(path)
    app.add_comment_before("project", "# Project section")
    result = read_file(path)
    check("yaml add_comment_before: comment present", result, "# Project section")
    app2 = Applier(path)
    app2.remove_leading_comment("project")
    result2 = read_file(path)
    check("yaml remove_leading_comment: comment removed", "PASS" if "# Project section" not in result2 else "FAIL", "PASS")

    # TOML: add and remove comment
    path = reset_fixture("toml")
    app = Applier(path)
    app.add_comment_before("project", "# Project table")
    result = read_file(path)
    check("toml add_comment_before: comment present", result, "# Project table")
    app2 = Applier(path)
    app2.remove_leading_comment("project")
    result2 = read_file(path)
    check("toml remove_leading_comment: comment removed", "PASS" if "# Project table" not in result2 else "FAIL", "PASS")


# ──────────────────────────────────────────────
# Phase D: replace_docstring
# ──────────────────────────────────────────────

def test_replace_docstring():
    print("\n═══ replace_docstring ═══")

    # Set up a file with an existing docstring
    path = os.path.join(TESTS_DIR, "test_docstring.py")
    with open(path, "w") as f:
        f.write('def foo():\n    """Old docstring."""\n    return 42\n')

    # Replace existing docstring
    app = Applier(path)
    app.replace_docstring("foo", '"""New docstring."""')
    result = read_file(path)
    check("py replace_docstring: new docstring present", result, "New docstring")
    check("py replace_docstring: old docstring removed", "PASS" if "Old docstring" not in result else "FAIL", "PASS")
    check("py replace_docstring: body preserved", result, "return 42")

    # Insert a new docstring where none exists
    with open(path, "w") as f:
        f.write('def bar():\n    return 1\n')
    app = Applier(path)
    app.replace_docstring("bar", '"""Added docstring."""')
    result = read_file(path)
    check("py replace_docstring: inserted when missing", result, "Added docstring")
    check("py replace_docstring: body preserved after insert", result, "return 1")

    os.remove(path)


# ──────────────────────────────────────────────
# Phase D: find_references
# ──────────────────────────────────────────────

def test_find_references():
    print("\n═══ find_references ═══")

    # Python: find references to LRUCache
    path = reset_fixture("py")
    app = Applier(path)
    output = app.find_references("key")
    check("py find_references: output includes 'line'", output, "line ")
    check("py find_references: 'key' found", output, "key")

    # No references
    app2 = Applier(path)
    output2 = app2.find_references("nonexistent_symbol_xyz")
    check("py find_references: not found message", output2, "no references")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

if __name__ == "__main__":
    test_python()
    test_python_decorated()
    test_javascript()
    test_typescript()
    test_json()
    test_yaml()
    test_toml()
    test_c()
    test_cpp()
    test_imports()
    test_add_function_class()
    test_add_delete_key()
    test_array_ops()
    test_add_field()
    test_replace_signature()
    test_list_symbols()
    test_get_signature()
    test_body_insertions()
    test_sibling_placement()
    test_python_literals()
    test_import_names()
    test_parameter_ops()
    test_comment_ops()
    test_replace_docstring()
    test_find_references()

    # Reset all fixtures to clean state after tests
    for lang in FIXTURES:
        reset_fixture(lang)

    print(f"\n{'═' * 40}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        print("SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
