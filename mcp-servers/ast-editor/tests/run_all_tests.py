import os
import sys
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from ast_editor.applier import Applier, ApplierError

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
    "rb": {
        "file": "test_target.rb",
        "content": """require 'json'

class LRUCache
  def initialize(capacity)
    @capacity = capacity
    @items = {}
  end

  def get(key)
    @items[key]
  end
end

def helper(x)
  x * 2
end
""",
    },
    "go": {
        "file": "test_target.go",
        "content": """package main

import (
\t"fmt"
\t"strings"
)

type Cache struct {
\tcapacity int
\titems    map[string]string
}

func NewCache(capacity int) *Cache {
\treturn &Cache{capacity: capacity, items: make(map[string]string)}
}

func (c *Cache) Get(key string) string {
\treturn c.items[key]
}

func (c *Cache) Set(key, value string) {
\tc.items[key] = value
}
""",
    },
    "java": {
        "file": "test_target.java",
        "content": """package com.example;

import java.util.HashMap;
import java.util.Map;

public class LRUCache {
    private int capacity;
    private Map<String, String> items;

    public LRUCache(int capacity) {
        this.capacity = capacity;
        this.items = new HashMap<>();
    }

    @Override
    public String toString() {
        return "LRUCache";
    }

    public String get(String key) {
        return items.get(key);
    }
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
        "        if key in self.items:\n            return self.items[key]\n        return None",
    )
    result = read_file(path)
    check("replace_function_body: new body injected", result, "if key in self.items:")
    check("replace_function_body: old body removed", result, "return None")
    check("replace_function_body: class intact", result, "class LRUCache:")

    # Test add_method
    path = reset_fixture("py")
    app = Applier(path)
    app.add_method(
        "LRUCache", "    def set(self, key, value):\n        self.items[key] = value"
    )
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
        '    @classmethod\n    def hello(cls):\n        return "hi from classmethod"',
    )
    result = read_file(path)
    check("replace_function: new decorator present", result, "@classmethod")
    check("replace_function: new body present", result, "hi from classmethod")
    check(
        "replace_function: no orphaned @staticmethod",
        "PASS" if "@staticmethod" not in result else "FAIL",
        "PASS",
    )

    # Test replace_function_body on a decorated function — should only replace body
    path = reset_fixture("py_decorated")
    app = Applier(path)
    app.replace_function_body("MyApp.name", '        return "fixed_name"')
    result = read_file(path)
    check("replace_function_body: decorator preserved", result, "@property")
    check("replace_function_body: new body present", result, "fixed_name")
    check("replace_function_body: signature preserved", result, "def name(self):")

    # Test delete_symbol on a decorated function — should remove decorator + def
    path = reset_fixture("py_decorated")
    app = Applier(path)
    app.delete_symbol("MyApp.hello")
    result = read_file(path)
    check(
        "delete_symbol: @staticmethod removed",
        "PASS" if "@staticmethod" not in result else "FAIL",
        "PASS",
    )
    check(
        "delete_symbol: def hello removed",
        "PASS" if "def hello" not in result else "FAIL",
        "PASS",
    )
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
        "        if (this.items.has(key)) {\n            return this.items.get(key);\n        }\n        return null;",
    )
    result = read_file(path)
    check("replace_function_body: new body injected", result, "this.items.has(key)")
    check("replace_function_body: returns null", result, "return null;")

    path = reset_fixture("js")
    app = Applier(path)
    app.add_method(
        "LRUCache", "    set(key, value) {\n        this.items.set(key, value);\n    }"
    )
    result = read_file(path)
    check("add_method: set method added", result, "set(key, value)")
    # One blank line after get(), as between the existing methods, and none
    # before the class's closing brace.
    _exact(
        "add_method: separated like the other methods, no blank line before }",
        result,
        FIXTURES["js"]["content"].replace(
            "    }\n}\n",
            "    }\n\n    set(key, value) {\n        this.items.set(key, value);\n    }\n}\n",
        ),
    )


# ──────────────────────────────────────────────
# TypeScript tests
# ──────────────────────────────────────────────


def test_typescript():
    print("\n═══ TypeScript (.ts) ═══")

    path = reset_fixture("ts")
    app = Applier(path)
    app.replace_function_body(
        "LRUCache.get",
        "        if (this.items.has(key)) {\n            return this.items.get(key);\n        }\n        return undefined;",
    )
    result = read_file(path)
    check("replace_function_body: new body injected", result, "this.items.has(key)")
    check("replace_function_body: returns undefined", result, "return undefined;")
    check(
        "replace_function_body: type annotation preserved",
        result,
        "get(key: string): number | undefined",
    )

    path = reset_fixture("ts")
    app = Applier(path)
    app.add_method(
        "LRUCache",
        "    set(key: string, value: number): void {\n        this.items.set(key, value);\n    }",
    )
    result = read_file(path)
    check(
        "add_method: typed set method added",
        result,
        "set(key: string, value: number): void",
    )


# ──────────────────────────────────────────────
# JSON tests
# ──────────────────────────────────────────────


def test_json():
    print("\n═══ JSON (.json) ═══")

    path = reset_fixture("json")
    app = Applier(path)
    app.replace_value("dependencies.tree-sitter", '"^0.23.0"')
    result = read_file(path)
    check("replace_value: version updated", result, "^0.23.0")
    check("replace_value: project name untouched", result, '"name": "ast-editor"')
    check("replace_value: structure intact", result, '"dependencies"')


# ──────────────────────────────────────────────
# YAML tests
# ──────────────────────────────────────────────


def test_yaml():
    print("\n═══ YAML (.yaml) ═══")

    path = reset_fixture("yaml")
    app = Applier(path)
    app.replace_value("project.version", '"2.0.0"')
    result = read_file(path)
    check("replace_value: version updated", result, "2.0.0")
    check("replace_value: name untouched", result, 'name: "ast-editor"')
    check("replace_value: dependencies untouched", result, 'tree-sitter: "^0.21.0"')

def test_yaml_sequence_fixes():
    """
    Regression tests for the three YAML-sequence bugs that previously forced
    callers to fall back to the plain Edit tool for structured edits.
    """
    print("\n═══ YAML sequence fixes (replace_value + append_to_array) ═══")

    # 1. replace_value on a block_sequence with bare items (no leading indent)
    path = os.path.join(TESTS_DIR, "test_seq.yaml")
    with open(path, "w") as f:
        f.write("superpowers:\n    - old1\n    - old2\n")
    app = Applier(path)
    app.replace_value("superpowers", '- "new1"\n- "new2"')
    result = read_file(path)
    check("bare items: new1 present", result, '- "new1"')
    check("bare items: new2 present", result, '- "new2"')
    check("bare items: old gone", "PASS" if "old1" not in result else "FAIL", "PASS")
    # Each item sits at the original 4-space column
    check("bare items: first item indented correctly", result, '    - "new1"')
    check("bare items: second item indented correctly", result, '    - "new2"')
    check("bare items: no double-indent on first item", "PASS" if '        - "new1"' not in result else "FAIL", "PASS")
    # No blank line between key and first item
    check("bare items: no blank line after key", "PASS" if "superpowers:\n\n" not in result else "FAIL", "PASS")
    os.remove(path)

    # 2. replace_value on a block_sequence WITH pre-indented content
    # (this was the "indentation doubling" case: passing '    - x' used to
    # produce 8 spaces on the first item while the rest stayed at 4).
    with open(path, "w") as f:
        f.write("superpowers:\n    - old1\n    - old2\n")
    app = Applier(path)
    app.replace_value("superpowers", '    - "A"\n    - "B"\n    - "C"')
    result = read_file(path)
    check("pre-indented: no doubling on first item", "PASS" if '        - "A"' not in result else "FAIL", "PASS")
    check("pre-indented: all items at same column", result, '    - "A"\n    - "B"\n    - "C"')
    os.remove(path)

    # 3. replace_value on a block_sequence with a LEADING \n in content
    # (used to produce a gratuitous blank line after the key).
    with open(path, "w") as f:
        f.write("superpowers:\n    - old1\n    - old2\n")
    app = Applier(path)
    app.replace_value("superpowers", '\n- "X"\n- "Y"')
    result = read_file(path)
    check("leading-newline: no blank line after key", "PASS" if "superpowers:\n\n" not in result else "FAIL", "PASS")
    check("leading-newline: X present", result, '- "X"')
    check("leading-newline: Y present", result, '- "Y"')
    os.remove(path)

    # 4. append_to_array with a multi-line mapping value (lists-of-mappings)
    # -- previously the `-` landed on its own line and the continuation keys
    # were emitted at column 0.
    with open(path, "w") as f:
        f.write('proof_points:\n  - name: "First"\n    url: "https://a"\n')
    app = Applier(path)
    app.append_to_array("proof_points", 'name: "Second"\nurl: "https://b"\nmetric: "fast"')
    result = read_file(path)
    check("multi-line: first line carries `-` marker", result, '  - name: "Second"')
    check("multi-line: url continuation indented under `-`", result, '    url: "https://b"')
    check("multi-line: metric continuation indented under `-`", result, '    metric: "fast"')
    check("multi-line: original item intact", result, '  - name: "First"')
    # Regression sanity: keys should NOT end up at column 0
    check("multi-line: continuation NOT at column 0", "PASS" if "\nurl: " not in result else "FAIL", "PASS")
    os.remove(path)

    # 5. append_to_array with a simple scalar value (regression check -- the
    # single-line path must still work exactly as before).
    with open(path, "w") as f:
        f.write("deps:\n  - a\n  - b\n")
    app = Applier(path)
    app.append_to_array("deps", "c")
    result = read_file(path)
    check("scalar append: element present", result, "- c")
    check("scalar append: previous items intact", result, "- a")
    check("scalar append: no multi-line artifacts", result, "deps:\n  - a\n  - b\n  - c")
    os.remove(path)




# ──────────────────────────────────────────────
# TOML tests
# ──────────────────────────────────────────────


def test_toml():
    print("\n═══ TOML (.toml) ═══")

    path = reset_fixture("toml")
    app = Applier(path)
    app.replace_value("project.name", '"ast-editor-pro"')
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
    app.replace_function_body("add", "    int result = a + b;\n    return result;")
    result = read_file(path)
    check("replace_function_body: new body injected", result, "int result = a + b;")
    check("replace_function_body: signature preserved", result, "int add(int a, int b)")
    check(
        "replace_function_body: other function intact",
        result,
        "int multiply(int a, int b)",
    )

    # replace_function: replace entire function including signature
    path = reset_fixture("c")
    app = Applier(path)
    app.replace_function(
        "multiply", "long multiply(long a, long b) {\n    return a * b;\n}"
    )
    result = read_file(path)
    check(
        "replace_function: new signature applied",
        result,
        "long multiply(long a, long b)",
    )
    check("replace_function: add() untouched", result, "int add(int a, int b)")

    # delete_symbol: remove a function
    path = reset_fixture("c")
    app = Applier(path)
    app.delete_symbol("multiply")
    result = read_file(path)
    check(
        "delete_symbol: multiply removed",
        "PASS" if "multiply" not in result else "FAIL",
        "PASS",
    )
    check("delete_symbol: add intact", result, "int add(int a, int b)")


# ──────────────────────────────────────────────
# C++ tests
# ──────────────────────────────────────────────


def test_cpp():
    print("\n═══ C++ (.cpp) ═══")

    # replace_function_body on a class method
    path = reset_fixture("cpp")
    app = Applier(path)
    app.replace_function_body("Calculator.add", "        return (a + b) * 2;")
    result = read_file(path)
    check("replace_function_body: new body injected", result, "(a + b) * 2")
    check("replace_function_body: signature preserved", result, "int add(int a, int b)")
    check(
        "replace_function_body: other method intact",
        result,
        "int subtract(int a, int b)",
    )

    # replace_function_body on free function
    path = reset_fixture("cpp")
    app = Applier(path)
    app.replace_function_body("freeFunc", "    return x + x;")
    result = read_file(path)
    check("replace_function_body (free): body injected", result, "return x + x;")
    check(
        "replace_function_body (free): signature preserved",
        result,
        "int freeFunc(int x)",
    )

    # add_method on class
    path = reset_fixture("cpp")
    app = Applier(path)
    app.add_method(
        "Calculator", "    int divide(int a, int b) {\n        return a / b;\n    }"
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
    check(
        "delete_symbol: subtract removed",
        "PASS" if "subtract" not in result else "FAIL",
        "PASS",
    )
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
    check(
        "py add_import: duplicate skipped",
        "PASS" if result2.count("import os") == 1 else "FAIL",
        "PASS",
    )

    app3 = Applier(path)
    app3.remove_import("import os")
    result3 = read_file(path)
    check(
        "py remove_import: import removed",
        "PASS" if "import os" not in result3 else "FAIL",
        "PASS",
    )

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
    app.add_key("dependencies", "mcp", '"^1.2.0"')
    result = read_file(path)
    check("json add_key: new key present", result, '"mcp": "^1.2.0"')
    check("json add_key: existing key intact", result, '"tree-sitter": "^0.21.0"')

    app2 = Applier(path)
    app2.delete_key("dependencies.mcp")
    result2 = read_file(path)
    check(
        "json delete_key: key removed",
        "PASS" if '"mcp"' not in result2 else "FAIL",
        "PASS",
    )
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
    check(
        "yaml delete_key: key removed",
        "PASS" if "author" not in result2 else "FAIL",
        "PASS",
    )

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
    check(
        "toml delete_key: key removed",
        "PASS" if "author" not in result2 else "FAIL",
        "PASS",
    )


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
    check(
        "json remove_from_array: element removed",
        "PASS" if '"b"' not in result2 else "FAIL",
        "PASS",
    )
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
        f.write("deps:\n  - a\n  - b\n")
    app = Applier(path)
    app.append_to_array("deps", "c")
    result = read_file(path)
    check("yaml append_to_array: new element present", result, "- c")
    check("yaml append_to_array: existing elements intact", result, "- a")

    app2 = Applier(path)
    app2.remove_from_array("deps", "b")
    result2 = read_file(path)
    check(
        "yaml remove_from_array: element removed",
        "PASS" if "- b" not in result2 else "FAIL",
        "PASS",
    )
    os.remove(path)


# ──────────────────────────────────────────────
# Phase 2: add_field
# ──────────────────────────────────────────────


def test_add_field():
    print("\n═══ add_field ═══")

    # Python: add a class attribute
    path = reset_fixture("py")
    app = Applier(path)
    app.add_field("LRUCache", '    version = "1.0"')
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
    check(
        "py replace_signature: new params applied",
        result,
        "def get(self, key, default=None):",
    )
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
    check(
        "c replace_signature: new return type applied",
        result,
        "long add(long a, long b)",
    )
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
    sig = app.read_symbol("LRUCache.get", depth="signature")
    check("py get_signature: correct sig returned", sig, "def get(self, key):")

    path = reset_fixture("cpp")
    app = Applier(path)
    sig = app.read_symbol("Calculator.add", depth="signature")
    check("cpp get_signature: correct sig returned", sig, "int add(int a, int b)")

    path = reset_fixture("c")
    app = Applier(path)
    sig = app.read_symbol("multiply", depth="signature")
    check("c get_signature: correct sig returned", sig, "int multiply(int a, int b)")


# ──────────────────────────────────────────────
# Phase A: prepend_to_body / append_to_body
# ──────────────────────────────────────────────


def test_body_insertions():
    print("\n═══ prepend_to_body / append_to_body ═══")

    # Python: prepend a log line to a function body
    path = reset_fixture("py")
    app = Applier(path)
    app.insert_in_body("LRUCache.get", "        print(f'getting {key}')", at="top")
    result = read_file(path)
    check("py prepend_to_body: new line at top", result, "print(f'getting {key}')")
    check(
        "py prepend_to_body: original body preserved",
        result,
        "return self.items.get(key)",
    )

    # Python: append a log line
    path = reset_fixture("py")
    app = Applier(path)
    app.insert_in_body("LRUCache.get", "        # end", at="bottom")
    result = read_file(path)
    check("py append_to_body: new line at bottom", result, "# end")
    check(
        "py append_to_body: original body preserved",
        result,
        "return self.items.get(key)",
    )

    # JS: prepend and append
    path = reset_fixture("js")
    app = Applier(path)
    app.insert_in_body("LRUCache.get", "        console.log('get');", at="top")
    result = read_file(path)
    check("js prepend_to_body: new line at top", result, "console.log('get');")
    check(
        "js prepend_to_body: original body preserved",
        result,
        "return this.items.get(key);",
    )

    # C: append to a free function
    path = reset_fixture("c")
    app = Applier(path)
    app.insert_in_body("add", "    /* end marker */", at="bottom")
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
    app.insert_sibling("LRUCache", "CONST = 42", "before")
    result = read_file(path)
    lines = result.splitlines()
    const_idx = next(i for i, l in enumerate(lines) if "CONST = 42" in l)
    class_idx = next(i for i, l in enumerate(lines) if "class LRUCache" in l)
    check(
        "py insert_before: const before class",
        "PASS" if const_idx < class_idx else "FAIL",
        "PASS",
    )

    # Python: insert_after a class
    path = reset_fixture("py")
    app = Applier(path)
    app.insert_sibling("LRUCache", "OTHER = 1", "after")
    result = read_file(path)
    lines = result.splitlines()
    class_idx = next(i for i, l in enumerate(lines) if "class LRUCache" in l)
    other_idx = next(i for i, l in enumerate(lines) if "OTHER = 1" in l)
    check(
        "py insert_after: const after class",
        "PASS" if other_idx > class_idx else "FAIL",
        "PASS",
    )

    # C: insert_after a function
    path = reset_fixture("c")
    app = Applier(path)
    app.insert_sibling("add", "int middle() { return 0; }", "after")
    result = read_file(path)
    lines = result.splitlines()
    add_end = max(i for i, l in enumerate(lines) if "return a + b;" in l)
    middle_idx = next(i for i, l in enumerate(lines) if "int middle()" in l)
    check(
        "c insert_after: middle after add",
        "PASS" if middle_idx > add_end else "FAIL",
        "PASS",
    )

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
    print(
        "\n═══ add_key / delete_key / append_to_array / remove_from_array on Python literals ═══"
    )

    # Set up a file with a dict and a list at module level
    path = os.path.join(TESTS_DIR, "test_literals.py")
    with open(path, "w") as f:
        f.write(
            'CONFIG = {\n    "a": 1,\n    "b": 2,\n}\n\nITEMS = [\n    "x",\n    "y",\n]\n'
        )

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
    check(
        "py delete_key (dict): entry removed",
        "PASS" if '"b": 2' not in result2 else "FAIL",
        "PASS",
    )
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
    check(
        "py remove_from_array (list): item removed",
        "PASS" if '"y"' not in result4 else "FAIL",
        "PASS",
    )
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
        f.write("from typing import Optional, List\nimport os\n")

    # add_import_name
    app = Applier(path)
    app.add_import_name("typing", "Union")
    result = read_file(path)
    check("py add_import_name: new name present", result, "Union")
    check("py add_import_name: existing names intact", result, "Optional")
    check(
        "py add_import_name: single line",
        result,
        "from typing import Optional, List, Union",
    )

    # Duplicate should be a no-op
    app2 = Applier(path)
    app2.add_import_name("typing", "Optional")
    result2 = read_file(path)
    check(
        "py add_import_name: duplicate skipped",
        "PASS" if result2.count("Optional") == 1 else "FAIL",
        "PASS",
    )

    # remove_import_name
    app3 = Applier(path)
    app3.remove_import_name("typing", "List")
    result3 = read_file(path)
    check(
        "py remove_import_name: name removed",
        "PASS" if "List" not in result3 else "FAIL",
        "PASS",
    )
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
    check(
        "py add_parameter: existing param intact",
        result,
        "def get(self, key, default=None):",
    )

    # Python: remove a parameter by name
    path = reset_fixture("py")
    app = Applier(path)
    app.add_parameter("LRUCache.get", "extra=1")
    app2 = Applier(path)
    app2.remove_parameter("LRUCache.get", "extra")
    result = read_file(path)
    check(
        "py remove_parameter: param removed",
        "PASS" if "extra" not in result else "FAIL",
        "PASS",
    )
    check("py remove_parameter: original param intact", result, "def get(self, key):")

    # C: add a parameter to a function
    path = reset_fixture("c")
    app = Applier(path)
    app.add_parameter("add", "int c")
    result = read_file(path)
    check("c add_parameter: new param present", result, "int c")
    check(
        "c add_parameter: existing params intact",
        result,
        "int add(int a, int b, int c)",
    )

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
    print(
        "\n═══ add_comment_before / remove_leading_comment / replace_leading_comment ═══"
    )

    # Python: add a comment before a function
    path = reset_fixture("py")
    app = Applier(path)
    app.edit_leading_comment("LRUCache.get", "add", "    # Get an item by key")
    result = read_file(path)
    check("py add_comment_before: comment present", result, "# Get an item by key")
    check("py add_comment_before: function intact", result, "def get(self, key):")

    # Verify the comment is immediately before the def
    lines = result.splitlines()
    def_idx = next(i for i, l in enumerate(lines) if "def get(self, key):" in l)
    check(
        "py add_comment_before: comment on prior line",
        lines[def_idx - 1].strip(),
        "# Get an item by key",
    )

    # Python: remove the leading comment we just added
    app2 = Applier(path)
    app2.edit_leading_comment("LRUCache.get", "remove")
    result2 = read_file(path)
    check(
        "py remove_leading_comment: comment removed",
        "PASS" if "# Get an item by key" not in result2 else "FAIL",
        "PASS",
    )
    check("py remove_leading_comment: function intact", result2, "def get(self, key):")

    # Python: replace_leading_comment
    path = reset_fixture("py")
    app = Applier(path)
    app.edit_leading_comment("LRUCache.get", "add", "    # Old comment")
    app2 = Applier(path)
    app2.edit_leading_comment("LRUCache.get", "replace", "    # New comment")
    result = read_file(path)
    check("py replace_leading_comment: new comment present", result, "# New comment")
    check(
        "py replace_leading_comment: old comment gone",
        "PASS" if "# Old comment" not in result else "FAIL",
        "PASS",
    )

    # JS: add and remove a line comment
    path = reset_fixture("js")
    app = Applier(path)
    app.edit_leading_comment("LRUCache.get", "add", "    // Get item by key")
    result = read_file(path)
    check("js add_comment_before: comment present", result, "// Get item by key")
    app2 = Applier(path)
    app2.edit_leading_comment("LRUCache.get", "remove")
    result2 = read_file(path)
    check(
        "js remove_leading_comment: comment removed",
        "PASS" if "// Get item by key" not in result2 else "FAIL",
        "PASS",
    )

    # TypeScript: add and remove
    path = reset_fixture("ts")
    app = Applier(path)
    app.edit_leading_comment("LRUCache.get", "add", "    // TS doc comment")
    result = read_file(path)
    check("ts add_comment_before: comment present", result, "// TS doc comment")

    # C: line comment add + remove
    path = reset_fixture("c")
    app = Applier(path)
    app.edit_leading_comment("add", "add", "// Adds two integers")
    result = read_file(path)
    check("c add_comment_before: comment present", result, "// Adds two integers")
    app2 = Applier(path)
    app2.edit_leading_comment("add", "remove")
    result2 = read_file(path)
    check(
        "c remove_leading_comment: line comment removed",
        "PASS" if "Adds two integers" not in result2 else "FAIL",
        "PASS",
    )

    # C: single-line block comment /* ... */
    path = os.path.join(TESTS_DIR, "test_block_c.c")
    with open(path, "w") as f:
        f.write("/* Doubles an integer */\nint dbl(int x) {\n    return x * 2;\n}\n")
    app = Applier(path)
    app.edit_leading_comment("dbl", "remove")
    result = read_file(path)
    check(
        "c remove_leading_comment: single-line block removed",
        "PASS" if "Doubles an integer" not in result else "FAIL",
        "PASS",
    )
    check("c remove_leading_comment: function intact", result, "int dbl(int x)")
    os.remove(path)

    # C: multi-line block comment /* ... */
    path = os.path.join(TESTS_DIR, "test_block_multi.c")
    with open(path, "w") as f:
        f.write(
            "/*\n * Multi-line block\n * comment\n */\nint foo(int x) {\n    return x;\n}\n"
        )
    app = Applier(path)
    app.edit_leading_comment("foo", "remove")
    result = read_file(path)
    check(
        "c remove_leading_comment: multi-line block removed",
        "PASS" if "Multi-line block" not in result else "FAIL",
        "PASS",
    )
    check(
        "c remove_leading_comment: closing */ removed",
        "PASS" if " */" not in result else "FAIL",
        "PASS",
    )
    check("c remove_leading_comment: function intact", result, "int foo(int x)")
    os.remove(path)

    # C++: mixed line + block comments
    path = os.path.join(TESTS_DIR, "test_block_cpp.cpp")
    with open(path, "w") as f:
        f.write("// line comment\n/* block */\nint bar() {\n    return 0;\n}\n")
    app = Applier(path)
    app.edit_leading_comment("bar", "remove")
    result = read_file(path)
    check(
        "cpp remove_leading_comment: line comment removed",
        "PASS" if "line comment" not in result else "FAIL",
        "PASS",
    )
    check(
        "cpp remove_leading_comment: block comment removed",
        "PASS" if "/* block */" not in result else "FAIL",
        "PASS",
    )
    os.remove(path)

    # YAML: add and remove comment
    path = reset_fixture("yaml")
    app = Applier(path)
    app.edit_leading_comment("project", "add", "# Project section")
    result = read_file(path)
    check("yaml add_comment_before: comment present", result, "# Project section")
    app2 = Applier(path)
    app2.edit_leading_comment("project", "remove")
    result2 = read_file(path)
    check(
        "yaml remove_leading_comment: comment removed",
        "PASS" if "# Project section" not in result2 else "FAIL",
        "PASS",
    )

    # TOML: add and remove comment
    path = reset_fixture("toml")
    app = Applier(path)
    app.edit_leading_comment("project", "add", "# Project table")
    result = read_file(path)
    check("toml add_comment_before: comment present", result, "# Project table")
    app2 = Applier(path)
    app2.edit_leading_comment("project", "remove")
    result2 = read_file(path)
    check(
        "toml remove_leading_comment: comment removed",
        "PASS" if "# Project table" not in result2 else "FAIL",
        "PASS",
    )


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
    check(
        "py replace_docstring: old docstring removed",
        "PASS" if "Old docstring" not in result else "FAIL",
        "PASS",
    )
    check("py replace_docstring: body preserved", result, "return 42")

    # Insert a new docstring where none exists
    with open(path, "w") as f:
        f.write("def bar():\n    return 1\n")
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
# Ruby tests
# ──────────────────────────────────────────────


def test_ruby():
    print("\n═══ Ruby (.rb) ═══")

    # replace_function_body on an instance method
    path = reset_fixture("rb")
    app = Applier(path)
    app.replace_function_body("LRUCache.get", "    @items.fetch(key, nil)")
    result = read_file(path)
    check(
        "rb replace_function_body: new body injected", result, "@items.fetch(key, nil)"
    )
    check("rb replace_function_body: signature preserved", result, "def get(key)")
    check("rb replace_function_body: class intact", result, "class LRUCache")

    # add_method to a Ruby class
    path = reset_fixture("rb")
    app = Applier(path)
    app.add_method("LRUCache", "  def set(key, value)\n    @items[key] = value\n  end")
    result = read_file(path)
    check("rb add_method: new method added", result, "def set(key, value)")
    check("rb add_method: existing method intact", result, "def get(key)")

    # add_field (option a: caller provides literal text)
    path = reset_fixture("rb")
    app = Applier(path)
    app.add_field("LRUCache", "  attr_accessor :capacity")
    result = read_file(path)
    check("rb add_field: attr_accessor inserted", result, "attr_accessor :capacity")

    # delete_symbol on a top-level function
    path = reset_fixture("rb")
    app = Applier(path)
    app.delete_symbol("helper")
    result = read_file(path)
    check(
        "rb delete_symbol: helper removed",
        "PASS" if "def helper" not in result else "FAIL",
        "PASS",
    )
    check("rb delete_symbol: class intact", result, "class LRUCache")

    # add_import (require)
    path = reset_fixture("rb")
    app = Applier(path)
    app.add_import("require 'set'")
    result = read_file(path)
    check("rb add_import: new require present", result, "require 'set'")
    check("rb add_import: original require intact", result, "require 'json'")

    # list_symbols
    path = reset_fixture("rb")
    app = Applier(path)
    outline = app.list_symbols()
    check("rb list_symbols: class listed", outline, "class LRUCache")
    check("rb list_symbols: method listed", outline, "method LRUCache.get")
    check("rb list_symbols: top-level function listed", outline, "function helper")

    # get_signature
    path = reset_fixture("rb")
    app = Applier(path)
    sig = app.read_symbol("LRUCache.get", depth="signature")
    check("rb get_signature: correct sig returned", sig, "def get(key)")

    # add_comment_before
    path = reset_fixture("rb")
    app = Applier(path)
    app.edit_leading_comment("LRUCache.get", "add", "  # Fetch an item by key")
    result = read_file(path)
    check("rb add_comment_before: comment present", result, "# Fetch an item by key")


# ──────────────────────────────────────────────
# Go tests
# ──────────────────────────────────────────────


def test_go():
    print("\n═══ Go (.go) ═══")

    # replace_function_body on a free function
    path = reset_fixture("go")
    app = Applier(path)
    app.replace_function_body("NewCache", "\treturn &Cache{capacity: capacity}")
    result = read_file(path)
    check(
        "go replace_function_body: new body injected",
        result,
        "return &Cache{capacity: capacity}",
    )
    check(
        "go replace_function_body: signature preserved",
        result,
        "func NewCache(capacity int) *Cache",
    )

    # replace_function_body on a method (dotted receiver addressing)
    path = reset_fixture("go")
    app = Applier(path)
    app.replace_function_body(
        "Cache.Get", '\tif v, ok := c.items[key]; ok {\n\t\treturn v\n\t}\n\treturn ""'
    )
    result = read_file(path)
    check(
        "go method replace_function_body: new body injected",
        result,
        "if v, ok := c.items[key]; ok",
    )
    check(
        "go method replace_function_body: signature preserved",
        result,
        "func (c *Cache) Get(key string) string",
    )

    # add_method on a struct (option a: inserts after type declaration as top-level sibling)
    path = reset_fixture("go")
    app = Applier(path)
    app.add_method(
        "Cache",
        "func (c *Cache) Has(key string) bool {\n\t_, ok := c.items[key]\n\treturn ok\n}",
    )
    result = read_file(path)
    check(
        "go add_method: new method present",
        result,
        "func (c *Cache) Has(key string) bool",
    )
    check(
        "go add_method: existing Get intact",
        result,
        "func (c *Cache) Get(key string) string",
    )

    # add_field on a struct (option a: caller provides literal text)
    path = reset_fixture("go")
    app = Applier(path)
    app.add_field("Cache", "\tversion int")
    result = read_file(path)
    check("go add_field: new field present", result, "version int")
    check("go add_field: existing fields intact", result, "capacity int")

    # delete_symbol on a top-level function
    path = reset_fixture("go")
    app = Applier(path)
    app.delete_symbol("NewCache")
    result = read_file(path)
    check(
        "go delete_symbol: NewCache removed",
        "PASS" if "func NewCache" not in result else "FAIL",
        "PASS",
    )
    check("go delete_symbol: struct intact", result, "type Cache struct")

    # add_import: full `import "io"` form -- should strip the keyword and
    # insert inside the existing parenthesized block
    path = reset_fixture("go")
    app = Applier(path)
    app.add_import('import "io"')
    result = read_file(path)
    check("go add_import (full form): spec inside block", result, '\t"io"')
    check("go add_import (full form): existing fmt intact", result, '"fmt"')
    check("go add_import (full form): block preserved", result, "import (")
    check(
        "go add_import (full form): no bare `import \"io\"` line outside block",
        "PASS" if '\nimport "io"' not in result else "FAIL",
        "PASS",
    )

    # add_import: spec-only `"path/filepath"` form -- the original bug case.
    # Previously produced a bare `"path/filepath"` line after `)` (syntax error).
    # Now inserts as a spec inside the block.
    path = reset_fixture("go")
    app = Applier(path)
    app.add_import('"path/filepath"')
    result = read_file(path)
    check("go add_import (spec-only): spec inside block", result, '\t"path/filepath"')
    check(
        "go add_import (spec-only): no orphan line after `)`",
        "PASS" if ')\n"path/filepath"' not in result else "FAIL",
        "PASS",
    )
    check("go add_import (spec-only): block still closed properly", result, "\n)\n")

    # add_import: duplicate detection inside the block
    app2 = Applier(path)
    msg = app2.add_import('"path/filepath"')
    check("go add_import (duplicate): detected", msg, "already exists")
    # File unchanged -- no second `"path/filepath"` line
    result = read_file(path)
    check(
        "go add_import (duplicate): not added twice",
        "PASS" if result.count('"path/filepath"') == 1 else "FAIL",
        "PASS",
    )

    # add_import: aliased spec form
    path = reset_fixture("go")
    app = Applier(path)
    app.add_import('f "path/filepath"')
    result = read_file(path)
    check("go add_import (aliased): alias preserved", result, '\tf "path/filepath"')

    # add_import: file with no existing imports at all -- falls through to generic path
    import os as _os
    noimp_path = _os.path.join(TESTS_DIR, "test_target_noimp.go")
    with open(noimp_path, "w") as f:
        f.write("package main\n\nfunc Hello() {}\n")
    app = Applier(noimp_path)
    app.add_import('import "fmt"')
    result = read_file(noimp_path)
    check("go add_import (no prior imports): top-level line added", result, 'import "fmt"')
    _os.remove(noimp_path)

    # list_symbols
    path = reset_fixture("go")
    app = Applier(path)
    outline = app.list_symbols()
    check("go list_symbols: struct listed", outline, "struct Cache")
    check("go list_symbols: method listed under struct", outline, "method Cache.Get")
    check("go list_symbols: top-level function listed", outline, "function NewCache")

    # get_signature on a method
    path = reset_fixture("go")
    app = Applier(path)
    sig = app.read_symbol("Cache.Get", depth="signature")
    check(
        "go get_signature: correct sig returned",
        sig,
        "func (c *Cache) Get(key string) string",
    )

    # add_comment_before (// style)
    path = reset_fixture("go")
    app = Applier(path)
    app.edit_leading_comment("Cache.Get", "add", "// Retrieves an item by key")
    result = read_file(path)
    check(
        "go add_comment_before: comment present", result, "// Retrieves an item by key"
    )


# ──────────────────────────────────────────────
# Java tests
# ──────────────────────────────────────────────


def test_java():
    print("\n═══ Java (.java) ═══")

    # replace_function_body on a regular method
    path = reset_fixture("java")
    app = Applier(path)
    app.replace_function_body(
        "LRUCache.get", '        return items.getOrDefault(key, "default");'
    )
    result = read_file(path)
    check(
        "java replace_function_body: new body injected",
        result,
        'getOrDefault(key, "default")',
    )
    check(
        "java replace_function_body: signature preserved",
        result,
        "public String get(String key)",
    )
    check("java replace_function_body: class intact", result, "public class LRUCache")

    # replace_function_body on a constructor (constructor_body type)
    path = reset_fixture("java")
    app = Applier(path)
    app.replace_function_body(
        "LRUCache.LRUCache",
        "        this.capacity = capacity * 2;\n        this.items = new HashMap<>();",
    )
    result = read_file(path)
    check(
        "java replace_function_body: constructor body updated",
        result,
        "this.capacity = capacity * 2",
    )
    # `LRUCache.LRUCache` used to resolve to the class itself, so the whole
    # class body was replaced (and the file left unparsable).
    check(
        "java replace_function_body: constructor target is not the class",
        result,
        "    public LRUCache(int capacity) {\n"
        "        this.capacity = capacity * 2;\n"
        "        this.items = new HashMap<>();\n"
        "    }\n\n    @Override",
    )

    # add_method to a class
    path = reset_fixture("java")
    app = Applier(path)
    app.add_method(
        "LRUCache", "    public void clear() {\n        items.clear();\n    }"
    )
    result = read_file(path)
    check("java add_method: new method present", result, "public void clear()")
    check(
        "java add_method: existing method intact",
        result,
        "public String get(String key)",
    )

    # add_field (option a: caller provides literal text)
    path = reset_fixture("java")
    app = Applier(path)
    app.add_field("LRUCache", "    private long createdAt;")
    result = read_file(path)
    check("java add_field: new field present", result, "private long createdAt")

    # delete_symbol on a method -- annotations should go with it
    path = reset_fixture("java")
    app = Applier(path)
    app.delete_symbol("LRUCache.toString")
    result = read_file(path)
    check(
        "java delete_symbol: method removed",
        "PASS" if "toString()" not in result else "FAIL",
        "PASS",
    )
    check(
        "java delete_symbol: @Override removed with method",
        "PASS" if "@Override" not in result else "FAIL",
        "PASS",
    )
    check("java delete_symbol: class intact", result, "public class LRUCache")

    # add_import
    path = reset_fixture("java")
    app = Applier(path)
    app.add_import("import java.util.List;")
    result = read_file(path)
    check("java add_import: new import present", result, "import java.util.List;")
    check(
        "java add_import: existing import intact", result, "import java.util.HashMap;"
    )

    # list_symbols
    path = reset_fixture("java")
    app = Applier(path)
    outline = app.list_symbols()
    check("java list_symbols: class listed", outline, "class LRUCache")
    check("java list_symbols: method listed", outline, "method LRUCache.get")
    check("java list_symbols: constructor listed", outline, "LRUCache.LRUCache")
    check("java list_symbols: toString listed", outline, "method LRUCache.toString")

    # get_signature on a method
    path = reset_fixture("java")
    app = Applier(path)
    sig = app.read_symbol("LRUCache.get", depth="signature")
    check(
        "java get_signature: correct sig returned", sig, "public String get(String key)"
    )

    # add_comment_before (// style)
    path = reset_fixture("java")
    app = Applier(path)
    app.edit_leading_comment("LRUCache.get", "add", "    // Retrieves an item by key")
    result = read_file(path)
    check(
        "java add_comment_before: comment present",
        result,
        "// Retrieves an item by key",
    )

    # Javadoc /** */ block comment recognition (remove_leading_comment)
    path = os.path.join(TESTS_DIR, "test_javadoc.java")
    with open(path, "w") as f:
        f.write("""public class Foo {
    /**
     * Javadoc comment for bar.
     */
    public void bar() {
    }
}
""")
    app = Applier(path)
    app.edit_leading_comment("Foo.bar", "remove")
    result = read_file(path)
    check(
        "java remove_leading_comment: Javadoc block removed",
        "PASS" if "Javadoc comment" not in result else "FAIL",
        "PASS",
    )
    check("java remove_leading_comment: method intact", result, "public void bar()")
    os.remove(path)

    # Interface with bodyless method
    path = os.path.join(TESTS_DIR, "test_interface.java")
    with open(path, "w") as f:
        f.write("""public interface Store {
    String get(String key);
    void set(String key, String value);
}
""")
    app = Applier(path)
    outline = app.list_symbols()
    check("java list_symbols: interface listed", outline, "interface Store")
    check("java list_symbols: interface method listed", outline, "method Store.get")
    os.remove(path)

    # Enum with methods
    path = os.path.join(TESTS_DIR, "test_enum.java")
    with open(path, "w") as f:
        f.write("""public enum Status {
    OK, ERROR;

    public boolean isOk() {
        return this == OK;
    }
}
""")
    app = Applier(path)
    outline = app.list_symbols()
    check("java list_symbols: enum listed", outline, "enum Status")
    check("java list_symbols: enum method listed", outline, "method Status.isOk")
    os.remove(path)


# ──────────────────────────────────────────────
# Merged-API tests (merge pass -- v2.0.0)
# ──────────────────────────────────────────────

def test_merged_apis():
    print("\n═══ merged APIs (edit_leading_comment, read_symbol depth, insert_in_body at, insert_sibling) ═══")
    import os as _os

    # -- edit_leading_comment: add / replace / remove dispatch --
    py_path = _os.path.join(TESTS_DIR, "test_merged_elc.py")
    with open(py_path, "w") as f:
        f.write("def foo():\n    return 1\n")
    Applier(py_path).edit_leading_comment("foo", "add", "# Does a thing")
    check("edit_leading_comment (add): inserted", read_file(py_path), "# Does a thing")

    Applier(py_path).edit_leading_comment("foo", "replace", "# Updated doc")
    result = read_file(py_path)
    check("edit_leading_comment (replace): new comment",
          "PASS" if "# Updated doc" in result and "Does a thing" not in result else "FAIL", "PASS")

    Applier(py_path).edit_leading_comment("foo", "remove")
    result = read_file(py_path)
    check("edit_leading_comment (remove): comment gone",
          "PASS" if "# Updated doc" not in result else "FAIL", "PASS")
    check("edit_leading_comment (remove): function intact", result, "def foo():")

    # Error: missing `comment` for add/replace
    bad = False
    try:
        Applier(py_path).edit_leading_comment("foo", "add")
    except Exception as e:
        bad = "required" in str(e) and "add" in str(e)
    check("edit_leading_comment: missing comment on add raises",
          "PASS" if bad else "FAIL", "PASS")

    bad = False
    try:
        Applier(py_path).edit_leading_comment("foo", "replace", "")
    except Exception as e:
        bad = "required" in str(e) and "replace" in str(e)
    check("edit_leading_comment: missing comment on replace raises",
          "PASS" if bad else "FAIL", "PASS")

    # Error: unknown op
    bad = False
    try:
        Applier(py_path).edit_leading_comment("foo", "bogus", "# x")
    except Exception as e:
        bad = "unknown op" in str(e)
    check("edit_leading_comment: unknown op raises",
          "PASS" if bad else "FAIL", "PASS")
    _os.remove(py_path)

    # -- read_symbol with depth --
    py_path = _os.path.join(TESTS_DIR, "test_merged_read.py")
    with open(py_path, "w") as f:
        f.write("class A:\n    def x(self, n):\n        return n + 1\n    def y(self):\n        return 2\n")

    app = Applier(py_path)
    # depth="full" (default)
    full = app.read_symbol("A.x")
    check("read_symbol depth=full: has body", full, "return n + 1")

    # depth="signature"
    sig = app.read_symbol("A.x", depth="signature")
    check("read_symbol depth=signature: has def line", sig, "def x(self, n):")
    check("read_symbol depth=signature: no body",
          "PASS" if "return n + 1" not in sig else "FAIL", "PASS")

    # depth="interface" on a class
    iface = app.read_symbol("A", depth="interface")
    check("read_symbol depth=interface: has class header", iface, "class A:")
    check("read_symbol depth=interface: has method stubs", iface, "def x(self, n)")
    check("read_symbol depth=interface: stub uses ...", iface, "...")
    check("read_symbol depth=interface: no body details",
          "PASS" if "return n + 1" not in iface else "FAIL", "PASS")

    # Default matches depth="full"
    check("read_symbol (no depth): matches depth=full", full, app.read_symbol("A.x"))

    # Error: unknown depth
    bad = False
    try:
        app.read_symbol("A.x", depth="bogus")
    except Exception as e:
        bad = "unknown depth" in str(e)
    check("read_symbol: unknown depth raises",
          "PASS" if bad else "FAIL", "PASS")
    _os.remove(py_path)

    # -- insert_in_body: at="top" / at="bottom" / after / before, exactly-one rule --
    py_path = _os.path.join(TESTS_DIR, "test_merged_iib.py")
    with open(py_path, "w") as f:
        f.write("def f(x):\n    validate(x)\n    return x\n")

    Applier(py_path).insert_in_body("f", "    log('start')", at="top")
    result = read_file(py_path)
    # "log('start')" should appear BEFORE "validate(x)"
    log_idx = result.find("log('start')")
    val_idx = result.find("validate(x)")
    check("insert_in_body at=top: prepended",
          "PASS" if 0 < log_idx < val_idx else "FAIL", "PASS")

    Applier(py_path).insert_in_body("f", "    log('end')", at="bottom")
    result = read_file(py_path)
    ret_idx = result.find("return x")
    end_idx = result.find("log('end')")
    check("insert_in_body at=bottom: appended",
          "PASS" if ret_idx < end_idx else "FAIL", "PASS")

    Applier(py_path).insert_in_body("f", "    audit(x)\n", after="    validate(x)\n")
    result = read_file(py_path)
    val_idx = result.find("validate(x)")
    aud_idx = result.find("audit(x)")
    check("insert_in_body after anchor: placed correctly",
          "PASS" if val_idx < aud_idx else "FAIL", "PASS")

    Applier(py_path).insert_in_body("f", "    auth(x)\n", before="    validate(x)\n")
    result = read_file(py_path)
    auth_idx = result.find("auth(x)")
    val_idx = result.find("validate(x)")
    check("insert_in_body before anchor: placed correctly",
          "PASS" if auth_idx < val_idx else "FAIL", "PASS")

    # Error: zero anchors
    bad = False
    try:
        Applier(py_path).insert_in_body("f", "x = 1")
    except Exception as e:
        bad = "exactly one" in str(e)
    check("insert_in_body: zero anchors raises",
          "PASS" if bad else "FAIL", "PASS")

    # Error: two anchors (at + after)
    bad = False
    try:
        Applier(py_path).insert_in_body("f", "x = 1", at="top", after="y")
    except Exception as e:
        bad = "exactly one" in str(e)
    check("insert_in_body: two anchors raises",
          "PASS" if bad else "FAIL", "PASS")

    # Error: three anchors
    bad = False
    try:
        Applier(py_path).insert_in_body("f", "x = 1", at="top", after="a", before="b")
    except Exception as e:
        bad = "exactly one" in str(e)
    check("insert_in_body: three anchors raises",
          "PASS" if bad else "FAIL", "PASS")

    # Error: bad at value
    bad = False
    try:
        Applier(py_path).insert_in_body("f", "x = 1", at="middle")
    except Exception as e:
        bad = "top" in str(e) and "bottom" in str(e)
    check("insert_in_body: bad at raises",
          "PASS" if bad else "FAIL", "PASS")
    _os.remove(py_path)

    # -- insert_sibling: before / after --
    py_path = _os.path.join(TESTS_DIR, "test_merged_sib.py")
    with open(py_path, "w") as f:
        f.write("class Foo:\n    pass\n")

    Applier(py_path).insert_sibling("Foo", "X = 1", "before")
    result = read_file(py_path)
    x_idx = result.find("X = 1")
    foo_idx = result.find("class Foo")
    check("insert_sibling before: placed before",
          "PASS" if 0 <= x_idx < foo_idx else "FAIL", "PASS")

    Applier(py_path).insert_sibling("Foo", "Y = 2", "after")
    result = read_file(py_path)
    foo_idx = result.find("class Foo")
    y_idx = result.find("Y = 2")
    check("insert_sibling after: placed after",
          "PASS" if foo_idx < y_idx else "FAIL", "PASS")

    # Error: bad position
    bad = False
    try:
        Applier(py_path).insert_sibling("Foo", "Z = 3", "middle")
    except Exception as e:
        bad = "before" in str(e) and "after" in str(e)
    check("insert_sibling: bad position raises",
          "PASS" if bad else "FAIL", "PASS")
    _os.remove(py_path)


# ──────────────────────────────────────────────
# replace_in_body / delete_in_body / insert_in_body (Phase 3.C)
# ──────────────────────────────────────────────

def test_in_body_family():
    print("\n═══ replace_in_body / delete_in_body / insert_in_body ═══")
    import os as _os

    # Python
    py_path = _os.path.join(TESTS_DIR, "test_inbody.py")
    with open(py_path, "w") as f:
        f.write('''def handle(request):
    log("start")
    validate(request)
    result = compute(request)
    log("end")
    return result


def other():
    return 42
''')

    # replace_in_body: swap one statement
    app = Applier(py_path)
    app.replace_in_body("handle", "result = compute(request)", "result = compute_v2(request)")
    result = read_file(py_path)
    check("py replace_in_body: new snippet present", result, "compute_v2(request)")
    check("py replace_in_body: old snippet removed",
          "PASS" if "compute(request)" not in result else "FAIL", "PASS")
    check("py replace_in_body: surrounding lines intact", result, 'log("start")')
    check("py replace_in_body: other function untouched", result, "def other")

    # delete_in_body: remove a line (with leading indent + trailing newline)
    app = Applier(py_path)
    app.delete_in_body("handle", '    log("start")\n')
    result = read_file(py_path)
    check("py delete_in_body: line removed",
          "PASS" if 'log("start")' not in result else "FAIL", "PASS")
    check("py delete_in_body: other statements intact", result, "validate(request)")

    # insert_in_body: after anchor
    app = Applier(py_path)
    app.insert_in_body(
        "handle",
        '    metrics.incr("calls")\n',
        after='    validate(request)\n',
    )
    result = read_file(py_path)
    check("py insert_in_body (after): new line present", result, 'metrics.incr("calls")')
    # Should be after validate, before compute
    v_idx = result.find("validate(request)")
    m_idx = result.find('metrics.incr("calls")')
    c_idx = result.find("compute_v2")
    check("py insert_in_body (after): ordered correctly",
          "PASS" if v_idx < m_idx < c_idx else "FAIL", "PASS")

    # insert_in_body: before anchor
    app = Applier(py_path)
    app.insert_in_body(
        "handle",
        '    auth_check(request)\n',
        before='    validate(request)\n',
    )
    result = read_file(py_path)
    a_idx = result.find("auth_check(request)")
    v_idx = result.find("validate(request)")
    check("py insert_in_body (before): new line present", result, "auth_check(request)")
    check("py insert_in_body (before): placed before anchor",
          "PASS" if 0 < a_idx < v_idx else "FAIL", "PASS")

    # Error: snippet not found
    bad = False
    app = Applier(py_path)
    try:
        app.replace_in_body("handle", "nonexistent_snippet", "new")
    except Exception as e:
        bad = "not found" in str(e)
    check("py replace_in_body: missing snippet raises", "PASS" if bad else "FAIL", "PASS")

    # Error: ambiguous match (multiple occurrences)
    app = Applier(py_path)
    bad = False
    try:
        # "return" appears twice (handle's return, other's return). But those
        # are in different bodies so scoping should prevent cross-body matches.
        # Let's test within-body ambiguity: the word "request" appears many times.
        app.replace_in_body("handle", "request", "req")
    except Exception as e:
        bad = "matches" in str(e) and "more" in str(e)
    check("py replace_in_body: ambiguous match raises", "PASS" if bad else "FAIL", "PASS")

    # Scope check: match in one body does NOT match text in sibling body
    # (`other`'s body is "    return 42\n" -- try replacing "return" inside `other`
    # while `handle` also has a return statement)
    app = Applier(py_path)
    app.replace_in_body("other", "return 42", "return 999")
    result = read_file(py_path)
    check("py replace_in_body: scoped to target body (other updated)", result, "return 999")
    check("py replace_in_body: scoped (handle's return untouched)", result, "return result")

    # insert_in_body: no anchor raises
    bad = False
    app = Applier(py_path)
    try:
        app.insert_in_body("handle", "x = 1")
    except Exception as e:
        bad = "exactly one" in str(e)
    check("py insert_in_body: no anchor raises", "PASS" if bad else "FAIL", "PASS")

    # insert_in_body: both anchors raises
    bad = False
    app = Applier(py_path)
    try:
        app.insert_in_body("handle", "x = 1", after="a", before="b")
    except Exception as e:
        bad = "exactly one" in str(e)
    check("py insert_in_body: both anchors raises", "PASS" if bad else "FAIL", "PASS")

    _os.remove(py_path)

    # Go (braces language)
    go_path = _os.path.join(TESTS_DIR, "test_inbody.go")
    with open(go_path, "w") as f:
        f.write('''package main

import "fmt"

func Process(items []string) error {
\tif len(items) == 0 {
\t\treturn nil
\t}
\tfor _, item := range items {
\t\tfmt.Println(item)
\t}
\treturn nil
}
''')

    app = Applier(go_path)
    app.replace_in_body("Process", "fmt.Println(item)", "fmt.Printf(\"%s\\n\", item)")
    result = read_file(go_path)
    check("go replace_in_body: new call present", result, 'fmt.Printf("%s\\n", item)')
    check("go replace_in_body: other structure intact", result, "for _, item := range items")

    # Delete the entire if block
    app = Applier(go_path)
    app.delete_in_body("Process", "\tif len(items) == 0 {\n\t\treturn nil\n\t}\n")
    result = read_file(go_path)
    check("go delete_in_body: if block removed",
          "PASS" if "if len(items) == 0" not in result else "FAIL", "PASS")
    check("go delete_in_body: for loop intact", result, "for _, item")

    _os.remove(go_path)


# ──────────────────────────────────────────────
# Closure addressing (Phase 3.B.7)
# ──────────────────────────────────────────────

def test_closure_addressing():
    print("\n═══ closure addressing (Go + JS/TS) ═══")
    import os as _os

    # Go: var ( stdioCmd = &cobra.Command{ RunE: func(...) {...} } )
    go_path = _os.path.join(TESTS_DIR, "test_closure.go")
    with open(go_path, "w") as f:
        f.write('''package main

import "fmt"

var (
\tstdioCmd = &cobra.Command{
\t\tUse:   "stdio",
\t\tShort: "Run stdio server",
\t\tRunE: func(cmd *cobra.Command, args []string) error {
\t\t\tfmt.Println("running")
\t\t\treturn nil
\t\t},
\t}
)

var single = &Foo{
\tHandler: func(x int) int {
\t\treturn x * 2
\t},
}
''')

    # Resolution: find the func_literal inside stdioCmd.RunE
    app = Applier(go_path)
    node = app.parser.find_node_by_name("stdioCmd.RunE")
    check("go find stdioCmd.RunE: resolves",
          "PASS" if node is not None and node.type == "func_literal" else "FAIL", "PASS")

    # replace_function_body on a Go closure
    app = Applier(go_path)
    app.replace_function_body("stdioCmd.RunE", "\t\t\treturn fmt.Errorf(\"not impl\")")
    result = read_file(go_path)
    check("go closure replace_function_body: new body present", result, 'return fmt.Errorf("not impl")')
    check("go closure replace_function_body: old body removed",
          "PASS" if 'fmt.Println("running")' not in result else "FAIL", "PASS")
    check("go closure replace_function_body: surrounding struct intact", result, "Use:   \"stdio\"")

    # get_signature on a Go closure
    app = Applier(go_path)
    sig = app.read_symbol("stdioCmd.RunE", depth="signature")
    check("go closure get_signature: returns func signature", sig, "func(cmd *cobra.Command, args []string) error")

    # Plain (non-block) var_spec closure
    app = Applier(go_path)
    node = app.parser.find_node_by_name("single.Handler")
    check("go plain var closure: resolves",
          "PASS" if node is not None and node.type == "func_literal" else "FAIL", "PASS")
    app.replace_function_body("single.Handler", "\t\treturn x + 1")
    result = read_file(go_path)
    check("go plain closure replace_function_body: new body present", result, "return x + 1")
    _os.remove(go_path)

    # TS: arrow_function as object property value
    ts_path = _os.path.join(TESTS_DIR, "test_closure.ts")
    with open(ts_path, "w") as f:
        f.write('''const app = {
  handler: (req: Request, res: Response) => {
    res.send("ok");
  },
  middleware: function(req: Request) {
    return req;
  },
};

export const config = {
  onStart: async () => {
    console.log("started");
  },
};
''')

    app = Applier(ts_path)
    node = app.parser.find_node_by_name("app.handler")
    check("ts find app.handler: resolves to arrow_function",
          "PASS" if node is not None and node.type == "arrow_function" else "FAIL", "PASS")

    app = Applier(ts_path)
    app.replace_function_body("app.handler", "    res.status(500).send(\"err\");")
    result = read_file(ts_path)
    check("ts arrow_function replace_function_body: new body present", result, 'res.status(500).send("err")')
    check("ts arrow_function replace_function_body: old body removed",
          "PASS" if 'res.send("ok")' not in result else "FAIL", "PASS")
    check("ts arrow_function replace_function_body: sibling property intact", result, "middleware: function")

    # function_expression form
    app = Applier(ts_path)
    node = app.parser.find_node_by_name("app.middleware")
    check("ts find app.middleware: resolves to function_expression",
          "PASS" if node is not None and node.type == "function_expression" else "FAIL", "PASS")

    # export const form with async arrow
    app = Applier(ts_path)
    node = app.parser.find_node_by_name("config.onStart")
    check("ts find config.onStart (export const + async): resolves",
          "PASS" if node is not None and node.type == "arrow_function" else "FAIL", "PASS")
    _os.remove(ts_path)

    # Missing var -> returns None (no raise)
    ts_path = _os.path.join(TESTS_DIR, "test_closure_nope.ts")
    with open(ts_path, "w") as f:
        f.write("const a = 1;\n")
    app = Applier(ts_path)
    node = app.parser.find_node_by_name("missing.field")
    check("ts closure: missing var returns None",
          "PASS" if node is None else "FAIL", "PASS")
    _os.remove(ts_path)


# ──────────────────────────────────────────────
# JS/TS delete_key support (Phase 2.B.4)
# ──────────────────────────────────────────────

def test_delete_key_jsts():
    print("\n═══ delete_key (JS/TS object literals) ═══")
    import os as _os

    ts_path = _os.path.join(TESTS_DIR, "test_delkey.ts")
    with open(ts_path, "w") as f:
        f.write('''const CONFIG = {
  port: 3000,
  debug: true,
  "complex-key": "v",
  name,
};

export const EXPORTED = {
  a: 1,
  b: 2,
};
''')

    # Delete a regular pair by bare name
    app = Applier(ts_path)
    app.delete_key("CONFIG.debug")
    result = read_file(ts_path)
    check("ts delete_key: regular pair removed",
          "PASS" if "debug: true" not in result else "FAIL", "PASS")
    check("ts delete_key: other pairs intact", result, "port: 3000")

    # Delete a shorthand property
    app = Applier(ts_path)
    app.delete_key("CONFIG.name")
    result = read_file(ts_path)
    check("ts delete_key: shorthand removed",
          "PASS" if "  name,\n" not in result else "FAIL", "PASS")

    # Delete a quoted key
    app = Applier(ts_path)
    app.delete_key('CONFIG."complex-key"')
    result = read_file(ts_path)
    check("ts delete_key: quoted key removed",
          "PASS" if '"complex-key"' not in result else "FAIL", "PASS")
    # Only `port` should remain in CONFIG
    check("ts delete_key: remaining key intact", result, "port: 3000")

    # Delete from an exported const
    app = Applier(ts_path)
    app.delete_key("EXPORTED.a")
    result = read_file(ts_path)
    check("ts delete_key: works on `export const`",
          "PASS" if "a: 1" not in result else "FAIL", "PASS")
    check("ts delete_key: sibling preserved in export const", result, "b: 2")

    # Missing key -> error
    bad_raised = False
    app = Applier(ts_path)
    try:
        app.delete_key("CONFIG.nothere")
    except Exception as e:
        bad_raised = "not found" in str(e)
    check("ts delete_key: missing key raises",
          "PASS" if bad_raised else "FAIL", "PASS")

    # Missing variable -> error
    bad_raised = False
    app = Applier(ts_path)
    try:
        app.delete_key("MISSING.a")
    except Exception as e:
        bad_raised = "not found" in str(e).lower() or "not found" in str(e)
    check("ts delete_key: missing variable raises",
          "PASS" if bad_raised else "FAIL", "PASS")

    # Bad target format -> error
    bad_raised = False
    app = Applier(ts_path)
    try:
        app.delete_key("noDot")
    except Exception as e:
        bad_raised = "VarName.keyName" in str(e) or "must be" in str(e)
    check("ts delete_key: bad target format raises",
          "PASS" if bad_raised else "FAIL", "PASS")
    _os.remove(ts_path)

    # JS variant (same grammar shape)
    js_path = _os.path.join(TESTS_DIR, "test_delkey.js")
    with open(js_path, "w") as f:
        f.write('const SETTINGS = { host: "localhost", timeout: 30 };\n')
    app = Applier(js_path)
    app.delete_key("SETTINGS.timeout")
    result = read_file(js_path)
    check("js delete_key: regular pair removed",
          "PASS" if "timeout" not in result else "FAIL", "PASS")
    check("js delete_key: other pair intact", result, 'host: "localhost"')
    _os.remove(js_path)


# ──────────────────────────────────────────────
# JS/TS named-import support (Phase 2.B.2 / B.3)
# ──────────────────────────────────────────────

def test_import_names_jsts():
    print("\n═══ add_import_name / remove_import_name (JS/TS) ═══")
    import os as _os

    # TypeScript add_import_name -- add to existing { a, b }
    ts_path = _os.path.join(TESTS_DIR, "test_imp_names.ts")
    with open(ts_path, "w") as f:
        f.write('''import { foo, bar } from "./utils";
import Default, { named } from "other";
import { alone } from "solo";

export function use() {
  return foo + bar + named + alone;
}
''')
    app = Applier(ts_path)
    app.add_import_name("./utils", "baz")
    result = read_file(ts_path)
    check("ts add_import_name: added to named imports", result, "foo, bar, baz")

    # Dedupe: adding same name again is a no-op
    app = Applier(ts_path)
    msg = app.add_import_name("./utils", "baz")
    check("ts add_import_name: duplicate detected", msg, "already present")

    # Add to the mixed-binding form `import Default, { named } from ...`
    # (one name counts as sorted: the new one goes at its sorted place)
    app = Applier(ts_path)
    app.add_import_name("other", "extra")
    result = read_file(ts_path)
    check(
        "ts add_import_name: works with default+named import",
        result,
        "{ extra, named }",
    )
    check(
        "ts add_import_name: default binding preserved",
        result,
        "import Default",
    )

    # remove_import_name: remove bar from utils
    app = Applier(ts_path)
    app.remove_import_name("./utils", "bar")
    result = read_file(ts_path)
    check(
        "ts remove_import_name: name removed",
        "PASS" if "bar" not in result.split("\n")[0] else "FAIL",
        "PASS",
    )
    check("ts remove_import_name: other names intact", result, "foo, baz")

    # Remove the only named import (no other bindings) -> whole statement removed
    app = Applier(ts_path)
    app.remove_import_name("solo", "alone")
    result = read_file(ts_path)
    check(
        "ts remove_import_name: last named (no default) removes whole line",
        "PASS" if '"solo"' not in result else "FAIL",
        "PASS",
    )

    # Remove the last named from `import Default, { x } from ...` -> error, not destructive
    bad_raised = False
    app = Applier(ts_path)
    try:
        # `other` has `import Default, { named, extra } from "other"` now
        app.remove_import_name("other", "named")
        app.remove_import_name("other", "extra")
    except Exception as e:
        bad_raised = "empty braces fragment" in str(e) or "Removing the last name" in str(e)
    check(
        "ts remove_import_name: refuses to leave `Default, {}`",
        "PASS" if bad_raised else "FAIL",
        "PASS",
    )
    # File should still be valid -- `import Default, { extra } from "other"` remains
    result = read_file(ts_path)
    check(
        "ts remove_import_name (refusal): file unchanged for that attempt",
        "PASS" if "import Default" in result else "FAIL",
        "PASS",
    )

    # Name not found -> error
    bad_raised = False
    app = Applier(ts_path)
    try:
        app.remove_import_name("./utils", "nonexistent")
    except Exception as e:
        bad_raised = "not found" in str(e)
    check(
        "ts remove_import_name: missing name raises",
        "PASS" if bad_raised else "FAIL",
        "PASS",
    )

    # Module not found -> error
    bad_raised = False
    app = Applier(ts_path)
    try:
        app.add_import_name("nope", "anything")
    except Exception as e:
        bad_raised = "not found" in str(e)
    check(
        "ts add_import_name: missing module raises",
        "PASS" if bad_raised else "FAIL",
        "PASS",
    )

    _os.remove(ts_path)

    # JavaScript form (same grammar shape)
    js_path = _os.path.join(TESTS_DIR, "test_imp_names.js")
    with open(js_path, "w") as f:
        f.write('import { readFile } from "fs";\n\nexport const x = readFile;\n')
    app = Applier(js_path)
    app.add_import_name("fs", "writeFile")
    result = read_file(js_path)
    check("js add_import_name: added", result, "readFile, writeFile")
    _os.remove(js_path)

    # Aliased specifier: `import { foo as bar } from "mod"` -- duplicate check
    # should match on the imported name, not the alias.
    ts_path = _os.path.join(TESTS_DIR, "test_imp_alias.ts")
    with open(ts_path, "w") as f:
        f.write('import { foo as bar } from "mod";\n')
    app = Applier(ts_path)
    msg = app.add_import_name("mod", "foo")
    check(
        "ts add_import_name: dedupe matches imported name, not alias",
        msg,
        "already present",
    )
    _os.remove(ts_path)


# ──────────────────────────────────────────────
# add_top_level: position parameter (Phase 1.B.6)
# ──────────────────────────────────────────────

def test_add_top_level_position():
    print("\n═══ add_top_level position ═══")
    import os as _os

    # Python: position="top" inserts after imports and module docstring
    py_path = _os.path.join(TESTS_DIR, "test_pos.py")
    with open(py_path, "w") as f:
        f.write('''"""Module docstring."""
import os
import sys


def existing():
    return 1
''')
    app = Applier(py_path)
    app.add_top_level("CACHE_SIZE = 100", position="top")
    result = read_file(py_path)
    # CACHE_SIZE must appear AFTER imports but BEFORE existing()
    cache_pos = result.find("CACHE_SIZE = 100")
    import_pos = result.find("import sys")
    existing_pos = result.find("def existing")
    check("py add_top_level top: inserted", result, "CACHE_SIZE = 100")
    check(
        "py add_top_level top: after imports",
        "PASS" if import_pos < cache_pos else "FAIL",
        "PASS",
    )
    check(
        "py add_top_level top: before existing symbol",
        "PASS" if cache_pos < existing_pos else "FAIL",
        "PASS",
    )
    check("py add_top_level top: docstring intact", result, '"""Module docstring."""')
    _os.remove(py_path)

    # Python: position="bottom" (default) behavior unchanged
    py_path = _os.path.join(TESTS_DIR, "test_pos_bottom.py")
    with open(py_path, "w") as f:
        f.write("import os\n\n\ndef existing():\n    return 1\n")
    app = Applier(py_path)
    app.add_top_level("TAIL = True")  # default position
    result = read_file(py_path)
    check(
        "py add_top_level bottom: at end",
        "PASS" if result.rstrip().endswith("TAIL = True") else "FAIL",
        "PASS",
    )
    _os.remove(py_path)

    # Go: position="top" inserts after package + import block
    go_path = _os.path.join(TESTS_DIR, "test_pos.go")
    with open(go_path, "w") as f:
        f.write('''package main

import (
\t"fmt"
)

func Existing() { fmt.Println("hi") }
''')
    app = Applier(go_path)
    app.add_top_level("const MaxConnections = 10", position="top")
    result = read_file(go_path)
    const_pos = result.find("const MaxConnections")
    import_pos = result.find('"fmt"')
    existing_pos = result.find("func Existing")
    check("go add_top_level top: inserted", result, "const MaxConnections = 10")
    check(
        "go add_top_level top: after import block",
        "PASS" if import_pos < const_pos else "FAIL",
        "PASS",
    )
    check(
        "go add_top_level top: before existing function",
        "PASS" if const_pos < existing_pos else "FAIL",
        "PASS",
    )
    _os.remove(go_path)

    # Java: position="top" inserts after package + imports
    java_path = _os.path.join(TESTS_DIR, "test_pos.java")
    with open(java_path, "w") as f:
        f.write('''package com.example;

import java.util.List;

public class Foo {
}
''')
    app = Applier(java_path)
    app.add_top_level("import java.util.Map;", position="top")
    result = read_file(java_path)
    new_pos = result.find("import java.util.Map;")
    existing_import_pos = result.find("import java.util.List;")
    class_pos = result.find("public class Foo")
    check("java add_top_level top: inserted", result, "import java.util.Map;")
    check(
        "java add_top_level top: after package+imports",
        "PASS" if existing_import_pos < new_pos else "FAIL",
        "PASS",
    )
    check(
        "java add_top_level top: before class",
        "PASS" if new_pos < class_pos else "FAIL",
        "PASS",
    )
    _os.remove(java_path)

    # File with no preamble: position="top" inserts at line 0
    py_path = _os.path.join(TESTS_DIR, "test_pos_empty.py")
    with open(py_path, "w") as f:
        f.write("def only():\n    return 1\n")
    app = Applier(py_path)
    app.add_top_level("FIRST = 1", position="top")
    result = read_file(py_path)
    check(
        "py add_top_level top (no preamble): at file start",
        "PASS" if result.startswith("FIRST = 1") else "FAIL",
        "PASS",
    )
    _os.remove(py_path)

    # Invalid position raises ApplierError
    py_path = _os.path.join(TESTS_DIR, "test_pos_bad.py")
    with open(py_path, "w") as f:
        f.write("x = 1\n")
    app = Applier(py_path)
    bad_raised = False
    try:
        app.add_top_level("y = 2", position="middle")
    except Exception as e:
        bad_raised = "middle" in str(e)
    check(
        "py add_top_level: invalid position rejected",
        "PASS" if bad_raised else "FAIL",
        "PASS",
    )
    _os.remove(py_path)


# ──────────────────────────────────────────────
# delete_symbol: leading-comment consumption (Phase 1.B.5)
# ──────────────────────────────────────────────

def test_delete_symbol_leading_comments():
    print("\n═══ delete_symbol: leading comments ═══")

    import os as _os

    # Python: `#` comment above function -- consumed by default
    py_path = _os.path.join(TESTS_DIR, "test_delcmt.py")
    with open(py_path, "w") as f:
        f.write('''# Helper used by downstream code.
# Uses quadratic time but that is fine for small inputs.
def legacy_calc(xs):
    total = 0
    for x in xs:
        total += x
    return total


def keep_me():
    return 1
''')
    app = Applier(py_path)
    app.delete_symbol("legacy_calc")
    result = read_file(py_path)
    check(
        "py delete_symbol: function removed",
        "PASS" if "def legacy_calc" not in result else "FAIL",
        "PASS",
    )
    check(
        "py delete_symbol: leading # comment removed",
        "PASS" if "Helper used by downstream code" not in result else "FAIL",
        "PASS",
    )
    check(
        "py delete_symbol: second comment line removed",
        "PASS" if "quadratic time" not in result else "FAIL",
        "PASS",
    )
    check("py delete_symbol: other symbols intact", result, "def keep_me")
    _os.remove(py_path)

    # Python: opt-out keeps the comment
    py_path = _os.path.join(TESTS_DIR, "test_delcmt_keep.py")
    with open(py_path, "w") as f:
        f.write('''# Important notice: do not remove.
def legacy_calc():
    return 0


def keep_me():
    return 1
''')
    app = Applier(py_path)
    app.delete_symbol("legacy_calc", include_leading_comments=False)
    result = read_file(py_path)
    check("py delete_symbol (keep): function removed",
          "PASS" if "def legacy_calc" not in result else "FAIL", "PASS")
    check("py delete_symbol (keep): leading comment preserved", result,
          "# Important notice: do not remove.")
    _os.remove(py_path)

    # Go: godoc comment above function
    go_path = _os.path.join(TESTS_DIR, "test_delcmt.go")
    with open(go_path, "w") as f:
        f.write('''package main

// LegacyCalc is the old implementation.
// It is kept here only for reference and will be removed.
func LegacyCalc(xs []int) int {
\ttotal := 0
\tfor _, x := range xs {
\t\ttotal += x
\t}
\treturn total
}

// KeepMe stays.
func KeepMe() int { return 1 }
''')
    app = Applier(go_path)
    app.delete_symbol("LegacyCalc")
    result = read_file(go_path)
    check("go delete_symbol: function removed",
          "PASS" if "func LegacyCalc" not in result else "FAIL", "PASS")
    check("go delete_symbol: godoc line 1 removed",
          "PASS" if "LegacyCalc is the old implementation" not in result else "FAIL", "PASS")
    check("go delete_symbol: godoc line 2 removed",
          "PASS" if "kept here only for reference" not in result else "FAIL", "PASS")
    check("go delete_symbol: KeepMe godoc intact", result, "// KeepMe stays.")
    check("go delete_symbol: KeepMe function intact", result, "func KeepMe")
    _os.remove(go_path)

    # Java: Javadoc /** ... */ block above method
    java_path = _os.path.join(TESTS_DIR, "test_delcmt.java")
    with open(java_path, "w") as f:
        f.write('''package com.example;

public class Util {
    /**
     * Legacy implementation.
     * Do not use in new code.
     */
    public int legacy(int n) {
        return n * 2;
    }

    public int keep(int n) {
        return n;
    }
}
''')
    app = Applier(java_path)
    app.delete_symbol("Util.legacy")
    result = read_file(java_path)
    check("java delete_symbol: method removed",
          "PASS" if "public int legacy" not in result else "FAIL", "PASS")
    check("java delete_symbol: Javadoc removed",
          "PASS" if "Legacy implementation." not in result else "FAIL", "PASS")
    check("java delete_symbol: Javadoc closing removed",
          "PASS" if "Do not use in new code" not in result else "FAIL", "PASS")
    check("java delete_symbol: other method intact", result, "public int keep")
    _os.remove(java_path)

    # C++: C-style /* ... */ block comment above function
    cpp_path = _os.path.join(TESTS_DIR, "test_delcmt.cpp")
    with open(cpp_path, "w") as f:
        f.write('''#include <iostream>

/* Old behavior, no longer used.
 * Replaced by newBehavior(). */
int oldBehavior(int x) {
    return x * 2;
}

int keep(int x) {
    return x;
}
''')
    app = Applier(cpp_path)
    app.delete_symbol("oldBehavior")
    result = read_file(cpp_path)
    check("cpp delete_symbol: function removed",
          "PASS" if "int oldBehavior" not in result else "FAIL", "PASS")
    check("cpp delete_symbol: block comment removed",
          "PASS" if "Old behavior, no longer used" not in result else "FAIL", "PASS")
    check("cpp delete_symbol: keep intact", result, "int keep")
    _os.remove(cpp_path)

    # No leading comment present -- should still work (no-op on comment side)
    py_path = _os.path.join(TESTS_DIR, "test_delcmt_nocmt.py")
    with open(py_path, "w") as f:
        f.write("def foo():\n    return 1\n\n\ndef bar():\n    return 2\n")
    app = Applier(py_path)
    app.delete_symbol("foo")
    result = read_file(py_path)
    check("py delete_symbol (no comment): function removed",
          "PASS" if "def foo" not in result else "FAIL", "PASS")
    check("py delete_symbol (no comment): bar intact", result, "def bar")
    _os.remove(py_path)

    # A /* ... */ that trails code on the line above is not a leading
    # comment, so the code stays; real block comments still go.
    for label, name, content, target, expected in [
        ("c trailing block comment", "test_delcmt.c",
         "int x = 1; /* trailing */\nint f(void) { return 0; }\n", "f",
         "int x = 1; /* trailing */\n"),
        ("java field with trailing block comment", "test_delcmt.java",
         "class A {\n    int x = 1; /* n */\n    void f() {}\n}\n", "A.f",
         "class A {\n    int x = 1; /* n */\n}\n"),
        ("c single-line block comment", "test_delcmt.c",
         "int x = 1;\n/* doc */\nint f(void) { return 0; }\n", "f", "int x = 1;\n"),
        ("c multi-line block comment", "test_delcmt.c",
         "int x = 1;\n/*\n * doc\n */\nint f(void) { return 0; }\n", "f", "int x = 1;\n"),
    ]:
        result = _edit_result(name, content, lambda a: a.delete_symbol(target))
        _exact(f"delete_symbol ({label})", result, expected)


# ──────────────────────────────────────────────
# AST Reader tests (read_symbol, read_imports, read_interface)
# ──────────────────────────────────────────────


def test_ast_reader():
    print("\n═══ AST Reader (read_symbol, read_imports, read_interface) ═══")

    # ── read_symbol ──

    # Python: read a method
    path = reset_fixture("py")
    app = Applier(path)
    result = app.read_symbol("LRUCache.get")
    check("read_symbol py method: has def", result, "def get(self, key):")
    check("read_symbol py method: has body", result, "return self.items.get(key)")

    # Python: read a class
    result = app.read_symbol("LRUCache")
    check("read_symbol py class: has class", result, "class LRUCache:")
    check("read_symbol py class: has init", result, "def __init__")
    check("read_symbol py class: has get", result, "def get")

    # JS: read a method
    path = reset_fixture("js")
    app = Applier(path)
    result = app.read_symbol("LRUCache.get")
    check("read_symbol js method: has get", result, "get(key)")
    check("read_symbol js method: has body", result, "return this.items.get(key)")

    # Go: read a receiver method
    path = reset_fixture("go")
    app = Applier(path)
    result = app.read_symbol("Cache.Get")
    check("read_symbol go method: has func", result, "func (c *Cache) Get")
    check("read_symbol go method: has body", result, "return c.items[key]")

    # Java: read a method
    path = reset_fixture("java")
    app = Applier(path)
    result = app.read_symbol("LRUCache.get")
    check("read_symbol java method: has get", result, "public String get")
    check("read_symbol java method: has body", result, "return items.get(key)")

    # JSON: read a config key
    path = reset_fixture("json")
    app = Applier(path)
    result = app.read_symbol("project.version")
    check("read_symbol json: value", result, "1.0.0")

    # Ruby: read a method
    path = reset_fixture("rb")
    app = Applier(path)
    result = app.read_symbol("LRUCache.get")
    check("read_symbol rb method: has def", result, "def get")
    check("read_symbol rb method: has body", result, "@items[key]")

    # ── read_imports ──

    # Python
    path = reset_fixture("py")
    app = Applier(path)
    result = app.read_imports()
    check("read_imports py: no imports", result, "(no imports found)")

    # Java
    path = reset_fixture("java")
    app = Applier(path)
    result = app.read_imports()
    check("read_imports java: has HashMap", result, "java.util.HashMap")
    check("read_imports java: has Map", result, "java.util.Map")

    # Go
    path = reset_fixture("go")
    app = Applier(path)
    result = app.read_imports()
    check("read_imports go: has fmt", result, "fmt")
    check("read_imports go: has strings", result, "strings")

    # Ruby
    path = reset_fixture("rb")
    app = Applier(path)
    result = app.read_imports()
    check("read_imports rb: has json", result, "require 'json'")

    # C
    path = reset_fixture("c")
    app = Applier(path)
    result = app.read_imports()
    check("read_imports c: has stdio", result, "#include <stdio.h>")

    # ── read_interface ──

    # Python class: should show signatures without bodies
    path = reset_fixture("py")
    app = Applier(path)
    result = app.read_symbol("LRUCache", depth="interface")
    check("read_interface py: has class header", result, "class LRUCache:")
    check("read_interface py: has init sig", result, "def __init__(self)")
    check("read_interface py: has get sig", result, "def get(self, key)")
    check("read_interface py: has ellipsis", result, "...")
    check(
        "read_interface py: no body detail",
        "PASS" if "self.items.get(key)" not in result else "FAIL",
        "PASS",
    )

    # JS class
    path = reset_fixture("js")
    app = Applier(path)
    result = app.read_symbol("LRUCache", depth="interface")
    check("read_interface js: has class header", result, "class LRUCache")
    check("read_interface js: has constructor sig", result, "constructor()")
    check("read_interface js: has get sig", result, "get(key)")
    check("read_interface js: has ellipsis", result, "...")

    # Java class
    path = reset_fixture("java")
    app = Applier(path)
    result = app.read_symbol("LRUCache", depth="interface")
    check("read_interface java: has class header", result, "class LRUCache")
    check("read_interface java: has fields", result, "private int capacity")
    check("read_interface java: has get sig", result, "public String get")
    check("read_interface java: has ellipsis", result, "...")
    check(
        "read_interface java: no body detail",
        "PASS" if "return items.get(key)" not in result else "FAIL",
        "PASS",
    )

    # Go struct: struct definition + receiver method signatures
    path = reset_fixture("go")
    app = Applier(path)
    result = app.read_symbol("Cache", depth="interface")
    check("read_interface go: has struct", result, "type Cache struct")
    check("read_interface go: has fields", result, "capacity int")
    check("read_interface go: has Get sig", result, "func (c *Cache) Get")
    check("read_interface go: has Set sig", result, "func (c *Cache) Set")
    check("read_interface go: has ellipsis", result, "...")
    check(
        "read_interface go: no body detail",
        "PASS" if "return c.items[key]" not in result else "FAIL",
        "PASS",
    )

    # C++ class
    path = reset_fixture("cpp")
    app = Applier(path)
    result = app.read_symbol("Calculator", depth="interface")
    check("read_interface cpp: has class header", result, "class Calculator")
    check("read_interface cpp: has add sig", result, "int add")
    check("read_interface cpp: has subtract sig", result, "int subtract")
    check("read_interface cpp: has ellipsis", result, "...")

    # Ruby class
    path = reset_fixture("rb")
    app = Applier(path)
    result = app.read_symbol("LRUCache", depth="interface")
    check("read_interface rb: has class header", result, "class LRUCache")
    check("read_interface rb: has init sig", result, "def initialize")
    check("read_interface rb: has get sig", result, "def get")
    check("read_interface rb: has end", result, "end")
    check("read_interface rb: has ellipsis", result, "...")

    # Function target: should return just its signature
    path = reset_fixture("py")
    app = Applier(path)
    result = app.read_symbol("LRUCache.get", depth="interface")
    check("read_interface py func: returns signature", result, "def get(self, key)")
    check(
        "read_interface py func: no body",
        "PASS" if "return self.items" not in result else "FAIL",
        "PASS",
    )


# ──────────────────────────────────────────────
# MCP schema tests (annotations, parameter descriptions, server metadata)
# ──────────────────────────────────────────────


def test_tool_schemas():
    print("\n═══ MCP tool schemas & server metadata ═══")

    import asyncio
    import json
    from importlib.metadata import version as _pkg_version

    from ast_editor.server import mcp

    tools = asyncio.run(mcp.list_tools())
    check(
        "schema: 28 tools registered",
        "PASS" if len(tools) == 28 else f"FAIL: {len(tools)} tools",
        "PASS",
    )

    unannotated = [t.name for t in tools if t.annotations is None]
    check(
        "schema: every tool has annotations",
        "PASS" if not unannotated else f"FAIL: {unannotated}",
        "PASS",
    )

    undescribed = [
        f"{t.name}.{prop}"
        for t in tools
        for prop, spec in t.input_schema.get("properties", {}).items()
        if not str(spec.get("description", "")).strip()
    ]
    check(
        "schema: every parameter has a description",
        "PASS" if not undescribed else f"FAIL: {undescribed}",
        "PASS",
    )

    check(
        "schema: server instructions are set",
        "PASS" if (mcp.instructions or "").strip() else "FAIL",
        "PASS",
    )
    # Clients show the instructions in addition to AST-EDITOR.md, which many
    # users include as well, so they stay short.
    size = len(mcp.instructions or "")
    check(
        "schema: server instructions are at most 1000 characters",
        "PASS" if size <= 1000 else f"FAIL: {size} characters",
        "PASS",
    )
    # What a client sends the model for each tool: its name, description and
    # input schema, as JSON. Every character costs tokens on every request.
    facing = sum(
        len(
            json.dumps(
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.input_schema,
                }
            )
        )
        for t in tools
    )
    check(
        "schema: model-facing tool text is at most 40000 characters",
        "PASS" if facing <= 40000 else f"FAIL: {facing} characters",
        "PASS",
    )
    # AST-EDITOR.md is the short guide many users load into every session;
    # the README is the full reference.
    with open(os.path.join(TESTS_DIR, "..", "AST-EDITOR.md"), encoding="utf-8") as f:
        guide_size = len(f.read())
    check(
        "schema: AST-EDITOR.md is at most 5000 characters",
        "PASS" if guide_size <= 5000 else f"FAIL: {guide_size} characters",
        "PASS",
    )
    for phrase in ("list_symbols", "replace_in_body", "parse-checked", "normal edit tool", '"editor.fontSize"'):
        check(f"schema: server instructions mention {phrase}", mcp.instructions or "", phrase)
    expected_version = _pkg_version("ast-editor-mcp")
    check(
        "schema: server version matches package metadata",
        "PASS" if mcp.version == expected_version else f"FAIL: {mcp.version!r}",
        "PASS",
    )


# ──────────────────────────────────────────────
# Save-time syntax guard, line endings, signature indentation
# ──────────────────────────────────────────────


def _write_temp(name: str, content: str, newline: str = "\n") -> str:
    """Write LF `content` to tests/<name> as raw bytes with the given line endings."""
    path = os.path.join(TESTS_DIR, name)
    with open(path, "wb") as f:
        f.write(content.replace("\n", newline).encode("utf-8"))
    return path


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _line_endings(data: bytes) -> str:
    """Classify the line breaks in data as 'crlf', 'lf', 'mixed' or 'none'."""
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    if b"\r\r" in data or (crlf and lf):
        return "mixed"
    if crlf:
        return "crlf"
    return "lf" if lf else "none"


def _refusal(action) -> str:
    """Run action() and return the ApplierError message, or 'NOT REFUSED'."""
    try:
        action()
    except ApplierError as e:
        return str(e)
    return "NOT REFUSED"


def test_syntax_guard():
    print("\n═══ Save-time syntax guard ═══")

    # One edit per language family that would break the parse. Each must be
    # refused, name the first error's position, and leave the file untouched.
    # (fixture, label, edit, substrings expected in the error message)
    cases = [
        (
            "js",
            "replace_in_body: unclosed block",
            lambda a: a.replace_in_body(
                "LRUCache.get",
                "return this.items.get(key);",
                "if (key) {\n            return this.items.get(key);",
            ),
            ("at line 11, column 2 (missing '}')",),
        ),
        (
            "ts",
            "add_method: unclosed method",
            lambda a: a.add_method(
                "LRUCache", "    clear(): void {\n        this.items.clear();"
            ),
            ("at line 16, column 2 (missing '}')",),
        ),
        (
            "c",
            "insert_in_body: unclosed if",
            lambda a: a.insert_in_body("add", "    if (a) {", at="bottom"),
            ("at line 10, column 2 (missing '}')",),
        ),
        (
            "cpp",
            "add_top_level: unclosed class",
            lambda a: a.add_top_level("class Broken {\npublic:\n    int x;"),
            ("at line 18, column 1 (cannot parse 'class Broken {')",),
        ),
        (
            "java",
            "add_method: unclosed method",
            lambda a: a.add_method(
                "LRUCache", "    public void clear() {\n        items.clear();"
            ),
            ("at line 26, column 2 (missing '}')",),
        ),
        (
            "go",
            "add_top_level: unclosed func",
            lambda a: a.add_top_level("func broken() {\n\treturn"),
            ("at line 27, column 1 (missing '}')",),
        ),
        (
            "rb",
            "add_top_level: def without end",
            lambda a: a.add_top_level("def broken\n  1"),
            ("at line 18, column 1 (cannot parse 'def broken')",),
        ),
        (
            "py",
            "replace_in_body: inconsistent dedent",
            lambda a: a.replace_in_body(
                "LRUCache.get",
                "        return self.items.get(key)",
                "        x = 1\n      return x",
            ),
            ("at line 8, column ", "(unindent does not match any outer indentation level)"),
        ),
        (
            "py",
            "replace_in_body: unexpected indent",
            lambda a: a.replace_in_body(
                "LRUCache.get",
                "        return self.items.get(key)",
                "        x = 1\n            return x",
            ),
            ("at line 8, column ", "(unexpected indent)"),
        ),
        (
            "py",
            "add_top_level: unclosed parenthesis",
            lambda a: a.add_top_level("def broken(:\n    pass"),
            ("at line 10, column 12 (missing ')')",),
        ),
        (
            "json",
            "replace_value: invalid literal",
            lambda a: a.replace_value("project.version", "tru e"),
            # tree-sitter puts its error on the comma ending line 3; json's
            # position wins when the two disagree on the line.
            ("at line 4, column 20 (Expecting value)",),
        ),
        (
            "json",
            "add_key: unterminated string",
            lambda a: a.add_key("project", "license", '"MIT'),
            ("at line 5, column 24 (missing '\"')",),
        ),
        (
            "yaml",
            "add_key: unclosed flow sequence",
            lambda a: a.add_key("project", "tags", "[a, b"),
            ("at line 4, column 9 (cannot parse '[a, b')",),
        ),
        (
            "yaml",
            "replace_value: unclosed flow mapping",
            lambda a: a.replace_value("project.version", "{x: 1"),
            ("at line 3, column 12 (cannot parse '{x: 1')",),
        ),
        (
            "toml",
            "replace_value: unterminated string",
            lambda a: a.replace_value("project.version", '"2.0.0'),
            ("at line 3, column 1 (cannot parse 'version = \"2.0.0')",),
        ),
        (
            "toml",
            "add_key: missing value",
            lambda a: a.add_key("project", "license", ""),
            ("at line 4, column 1 (cannot parse 'license =')",),
        ),
    ]
    for lang, label, action, expected in cases:
        path = reset_fixture(lang)
        before = _read_bytes(path)
        message = _refusal(lambda: action(Applier(path)))
        check(f"{lang} {label}: refused", message, "Edit refused: the result would have a syntax error ")
        for fragment in expected:
            check(f"{lang} {label}: names the error position", message, fragment)
        check(f"{lang} {label}: says the file was not modified", message, f"{path} was not modified.")
        check(
            f"{lang} {label}: points to the normal edit tool for valid code",
            message,
            "If you are sure the code is valid (the parser may not support very new "
            "or macro-heavy syntax), make this edit with your normal edit tool.",
        )
        check(
            f"{lang} {label}: file byte-identical",
            "PASS" if _read_bytes(path) == before else "FAIL",
            "PASS",
        )

    # The MCP tool surfaces the refusal as a normal "Cannot perform edit" reply.
    from ast_editor import server

    path = reset_fixture("py")
    reply = server.add_top_level(path, "def broken(:\n    pass")
    check("server add_top_level: refusal reported", reply, "Cannot perform edit: Edit refused: ")
    check("server add_top_level: file untouched", read_file(path), FIXTURES["py"]["content"])

    # After a refusal the same Applier still mirrors the untouched file, so a
    # following valid edit does not carry the refused lines along.
    path = reset_fixture("py")
    app = Applier(path)
    _refusal(lambda: app.add_top_level("def broken(:\n    pass"))
    app.add_top_level("def fine():\n    return 1")
    result = read_file(path)
    check("after a refusal: valid edit on the same Applier applies", result, "\n\ndef fine():\n    return 1\n")
    check(
        "after a refusal: refused content not written",
        "PASS" if "broken" not in result else "FAIL",
        "PASS",
    )

    # A valid edit goes straight through (the rest of the suite exercises
    # valid edits in every language, all under the guard).
    path = reset_fixture("go")
    Applier(path).add_top_level("func ok() int {\n\treturn 1\n}")
    check("valid go edit: applied", read_file(path), "func ok() int {\n\treturn 1\n}\n")

    # .tsx files use the TSX grammar, so adding JSX to a clean file is valid.
    path = _write_temp("test_guard.tsx", "function add(a: number, b: number): number {\n  return a + b;\n}\n")
    message = _refusal(lambda: Applier(path).add_top_level("export const Hello = () => <div className=\"x\">hi</div>;"))
    check("tsx: JSX edit on a clean file allowed", message, "NOT REFUSED")
    check("tsx: JSX edit written", read_file(path), "<div className=\"x\">hi</div>")
    check("tsx: symbols still resolve", Applier(path).list_symbols(), "function add")
    os.remove(path)

    # Files that already fail to parse are not guarded, so work on them is
    # never blocked -- even edits that add further errors.
    path = _write_temp("test_broken.js", "function broken() {\n  return 1;\n")
    message = _refusal(lambda: Applier(path).add_top_level("const added = [1, 2;"))
    check("already-broken js: edit allowed", message, "NOT REFUSED")
    check("already-broken js: edit written", read_file(path), "const added = [1, 2;")
    os.remove(path)

    # Python that only Python's own parser rejects (bad dedent) counts as
    # already broken too.
    path = _write_temp("test_broken.py", "def f():\n    a = 1\n  b = 2\n")
    message = _refusal(lambda: Applier(path).add_top_level("def g(:\n    pass"))
    check("already-broken py: edit allowed", message, "NOT REFUSED")
    check("already-broken py: edit written", read_file(path), "def g(:")
    os.remove(path)

    # Valid Python that the tree-sitter grammar misparses (PEP 696 type
    # parameter defaults, Python 3.13+) is still guarded by Python's parser.
    if sys.version_info >= (3, 13):
        path = _write_temp("test_guard_pep696.py", "def f[T = int](x: T) -> T:\n    return x\n")
        message = _refusal(lambda: Applier(path).add_top_level("def g():\n    a = 1\n  b = 2"))
        check("py misparsed by tree-sitter: bad dedent refused", message, "(unindent does not match any outer indentation level)")
        message = _refusal(lambda: Applier(path).add_top_level("def h():\n    return 1"))
        check("py misparsed by tree-sitter: valid edit allowed", message, "NOT REFUSED")
        os.remove(path)

        # Python's parser also lets such syntax into a clean file, and when
        # both parsers object on different lines its position is reported.
        path = _write_temp("test_guard_pep696.py", "import os\n\n\ndef a():\n    return 1\n")
        message = _refusal(lambda: Applier(path).add_top_level("def g[T = int](x: T) -> T:\n    return x"))
        check("py PEP 696 into a clean file: allowed", message, "NOT REFUSED")
        check("py PEP 696 into a clean file: written", read_file(path), "\ndef g[T = int](x: T) -> T:\n    return x\n")
        path = _write_temp("test_guard_pep696.py", "import os\n\n\ndef a():\n    return 1\n")
        message = _refusal(
            lambda: Applier(path).add_top_level("def g[T = int](x: T) -> T:\n    return x\n\ndef h(:\n    pass")
        )
        check("py PEP 696 plus a real error: refused at the real error", message, "syntax error at line 11, column ")
        os.remove(path)

    # JSON that tree-sitter-json rejects but RFC 8259 allows (an exponent
    # with an explicit +) is allowed; NaN and real errors are still refused.
    # (label, edit, text written, or None if the edit must be refused)
    for label, action, written in [
        ("exponent with + via replace_value", lambda a: a.replace_value("a", "1e+2"), '"a": 1e+2\n'),
        ("exponent with + via add_key", lambda a: a.add_key("", "b", "6.02E+23"), '"b": 6.02E+23\n'),
        ("NaN", lambda a: a.replace_value("a", "NaN"), None),
        ("unclosed array", lambda a: a.replace_value("a", "[1,"), None),
    ]:
        path = _write_temp("test_guard.json", '{\n  "a": 1\n}\n')
        before = _read_bytes(path)
        message = _refusal(lambda: action(Applier(path)))
        if written is not None:
            check(f"json {label}: allowed", message, "NOT REFUSED")
            check(f"json {label}: written", read_file(path), written)
        else:
            check(f"json {label}: refused", message, "Edit refused: ")
            check(f"json {label}: file untouched", "PASS" if _read_bytes(path) == before else "FAIL", "PASS")
    path = _write_temp("test_guard.json", '{\n  "a": 1\n}\n')
    Applier(path).add_key("", "b", "6.02E+23")
    # Such a file parses cleanly (the parser masks the exponent signs for
    # tree-sitter), so a later broken edit is refused, at tree-sitter's
    # position on the line json reports too.
    check("json with + exponents: file parses cleanly",
          "PASS" if not Applier(path).parser.tree.root_node.has_error else "FAIL", "PASS")
    message = _refusal(lambda: Applier(path).replace_value("a", "[1,"))
    check("json with + exponents: broken edit refused", message,
          "Edit refused: the result would have a syntax error at line 2, column 6 (cannot parse ': [1,,')")
    os.remove(path)
    # JSONC: comments stay allowed (json rejects them, but tree-sitter
    # accepts the result), and a real error is still refused.
    path = _write_temp("test_guard.json", '{\n  // settings\n  "a": 1\n}\n')
    check("jsonc: valid edit allowed", _refusal(lambda: Applier(path).add_key("", "b", "2")), "NOT REFUSED")
    check("jsonc: broken edit refused", _refusal(lambda: Applier(path).add_key("", "c", "[1,")), "Edit refused: ")
    os.remove(path)

    # An already-broken config file is not guarded either.
    path = _write_temp("test_broken.toml", 'a = \n[t]\nb = 1\n')
    message = _refusal(lambda: Applier(path).add_key("t", "c", "2"))
    check("already-broken toml: edit allowed", message, "NOT REFUSED")
    check("already-broken toml: edit written", read_file(path), "b = 1\nc = 2\n")
    os.remove(path)


def test_line_endings():
    print("\n═══ Line endings ═══")

    # Every fixture is rewritten with CRLF endings; each edit must keep CRLF
    # on every line (no LF-only or doubled endings). Snippets and anchors are
    # written with \n, as callers normally send them.
    # (fixture, label, edit, text expected in the result once CRLF -> LF)
    cases = [
        # Line-based tools
        (
            "py",
            "add_top_level bottom",
            lambda a: a.add_top_level("def helper():\n    return 1"),
            "        return self.items.get(key)\n\n\ndef helper():\n    return 1\n",
        ),
        (
            "py",
            "add_top_level top",
            lambda a: a.add_top_level("SIZE = 1", position="top"),
            "SIZE = 1\n\n\nclass LRUCache:\n",
        ),
        (
            "py",
            "add_method",
            lambda a: a.add_method(
                "LRUCache", "    def clear(self):\n        self.items.clear()"
            ),
            "        return self.items.get(key)\n\n    def clear(self):\n        self.items.clear()\n",
        ),
        (
            "py",
            "insert_sibling before",
            lambda a: a.insert_sibling("LRUCache", "SIZE = 1", "before"),
            "SIZE = 1\n\n\nclass LRUCache:\n",
        ),
        (
            "py",
            "insert_sibling after",
            lambda a: a.insert_sibling("LRUCache", "def after():\n    pass", "after"),
            "        return self.items.get(key)\n\n\ndef after():\n    pass\n",
        ),
        (
            "py",
            "insert_in_body at=top",
            lambda a: a.insert_in_body(
                "LRUCache.get", "        print(key)\n        key = str(key)", at="top"
            ),
            "    def get(self, key):\n        print(key)\n        key = str(key)\n        return",
        ),
        (
            "py",
            "insert_in_body at=bottom",
            lambda a: a.insert_in_body("LRUCache.get", "        # end", at="bottom"),
            "        return self.items.get(key)\n        # end\n",
        ),
        (
            "js",
            "add_method",
            lambda a: a.add_method(
                "LRUCache", "    clear() {\n        this.items.clear();\n    }"
            ),
            "clear() {\n",
        ),
        (
            "go",
            "add_method",
            lambda a: a.add_method(
                "Cache", "func (c *Cache) Len() int {\n\treturn len(c.items)\n}"
            ),
            "}\n\nfunc (c *Cache) Len() int {\n\treturn len(c.items)\n}\n",
        ),
        (
            "c",
            "add_top_level",
            lambda a: a.add_top_level("int sub(int a, int b) {\n    return a - b;\n}"),
            "\n\nint sub(int a, int b) {\n    return a - b;\n}\n",
        ),
        (
            "java",
            "add_field",
            lambda a: a.add_field("LRUCache", "    private int hits;"),
            "public class LRUCache {\n    private int hits;\n",
        ),
        (
            "yaml",
            "add_key",
            lambda a: a.add_key("project", "license", '"MIT"'),
            'version: "1.0.0"\n  license: "MIT"\n',
        ),
        (
            "toml",
            "add_key",
            lambda a: a.add_key("project", "license", '"MIT"'),
            'version = "1.0.0"\nlicense = "MIT"\n',
        ),
        # Byte-based tools
        (
            "py",
            "replace_in_body",
            lambda a: a.replace_in_body(
                "LRUCache.__init__",
                "self.capacity = 10\n        self.items = {}",
                "self.capacity = 20\n        self.items = dict()",
            ),
            "        self.capacity = 20\n        self.items = dict()\n",
        ),
        (
            "py",
            "replace_in_body with CRLF snippets",
            lambda a: a.replace_in_body(
                "LRUCache.__init__",
                "self.capacity = 10\r\n        self.items = {}",
                "self.capacity = 30\r\n        self.hits = 0\r\n        self.items = {}",
            ),
            "        self.capacity = 30\n        self.hits = 0\n        self.items = {}\n",
        ),
        (
            "py",
            "insert_in_body after",
            lambda a: a.insert_in_body(
                "LRUCache.__init__", "\n        self.hits = 0", after="self.items = {}"
            ),
            "        self.items = {}\n        self.hits = 0\n\n    def get",
        ),
        (
            "py",
            "replace_signature",
            lambda a: a.replace_signature(
                "LRUCache.get", "    def get(\n        self,\n        key,\n    ):"
            ),
            "    def get(\n        self,\n        key,\n    ):\n        return",
        ),
        (
            "py",
            "add_parameter",
            lambda a: a.add_parameter("LRUCache.get", "default=None"),
            "    def get(self, key, default=None):\n",
        ),
        (
            "py",
            "replace_docstring",
            lambda a: a.replace_docstring(
                "LRUCache.get", '"""Return the item.\n\n        Or None.\n        """'
            ),
            '        """Return the item.\n\n        Or None.\n        """\n        return',
        ),
        (
            "js",
            "insert_in_body at=top",
            lambda a: a.insert_in_body("LRUCache.get", "        console.log(key);", at="top"),
            "    get(key) {\n        console.log(key);\n        return",
        ),
        (
            "json",
            "add_key",
            lambda a: a.add_key("project", "license", '"MIT"'),
            '"version": "1.0.0",\n        "license": "MIT"\n    },',
        ),
        (
            "json",
            "replace_value",
            lambda a: a.replace_value("project.version", '"2.0.0"'),
            '        "version": "2.0.0"\n',
        ),
        (
            "yaml",
            "replace_value",
            lambda a: a.replace_value("project.version", '"2.0.0"'),
            '  version: "2.0.0"\n',
        ),
        (
            "toml",
            "replace_value",
            lambda a: a.replace_value("project.version", '"2.0.0"'),
            'version = "2.0.0"\n',
        ),
    ]
    for lang, label, action, expected in cases:
        ext = os.path.splitext(FIXTURES[lang]["file"])[1]
        path = _write_temp("test_crlf" + ext, FIXTURES[lang]["content"], "\r\n")
        try:
            action(Applier(path))
        except ApplierError as e:
            check(f"crlf {lang} {label}: edit applied", f"REFUSED: {e}", expected)
            os.remove(path)
            continue
        data = _read_bytes(path)
        endings = _line_endings(data)
        check(
            f"crlf {lang} {label}: CRLF on every line",
            "PASS" if endings == "crlf" else f"FAIL: {endings}",
            "PASS",
        )
        check(
            f"crlf {lang} {label}: edit applied",
            data.decode("utf-8").replace("\r\n", "\n"),
            expected,
        )
        os.remove(path)

    # Lines the edit did not touch come back byte-identical.
    original = FIXTURES["go"]["content"].replace("\n", "\r\n").encode("utf-8")
    path = _write_temp("test_crlf.go", FIXTURES["go"]["content"], "\r\n")
    Applier(path).add_top_level("func ok() int {\r\n\treturn 1\r\n}")
    check(
        "crlf go: original bytes untouched",
        "PASS" if _read_bytes(path).startswith(original) else "FAIL",
        "PASS",
    )
    os.remove(path)

    # LF files stay LF, even when caller content arrives with CRLF.
    path = reset_fixture("py")
    Applier(path).add_method("LRUCache", "    def clear(self):\r\n        self.items.clear()")
    endings = _line_endings(_read_bytes(path))
    check("lf py add_method with CRLF content: LF only", "PASS" if endings == "lf" else f"FAIL: {endings}", "PASS")
    check("lf py add_method with CRLF content: applied", read_file(path), "    def clear(self):\n        self.items.clear()\n")

    path = reset_fixture("js")
    Applier(path).replace_in_body(
        "LRUCache.get",
        "return this.items.get(key);",
        "const v = this.items.get(key);\r\n        return v;",
    )
    endings = _line_endings(_read_bytes(path))
    check("lf js replace_in_body with CRLF content: LF only", "PASS" if endings == "lf" else f"FAIL: {endings}", "PASS")

    # A mixed file keeps each line's own break; new lines take that of the
    # line beside them (see test_content_layout).
    path = _write_temp("test_mixed.py", "a = 1\r\nb = 2\r\nc = 3\n")
    Applier(path).add_top_level("d = 4")
    check("mixed endings: each line keeps its own", _read_bytes(path).decode("utf-8"), "a = 1\r\nb = 2\r\nc = 3\nd = 4\n")
    os.remove(path)

    # str.splitlines() also splits on form feeds; the file must keep them and
    # line-based edits must still land on the right line.
    path = _write_temp("test_formfeed.py", "import os\n\x0c\ndef f():\n    return 1\n")
    Applier(path).insert_in_body("f", "    x = 2", at="top")
    check(
        "form feed: kept, and insert lands inside f",
        _read_bytes(path).decode("utf-8"),
        "import os\n\x0c\ndef f():\n    x = 2\n    return 1\n",
    )
    os.remove(path)

    # Blank lines at the end of the file survive line-based edits elsewhere,
    # in either style; an edit never leaves more of them than there were.
    trailing = "import os\n\n\ndef f():\n    return 1\n\n\n"
    for label, newline in (("lf", "\n"), ("crlf", "\r\n")):
        result = _edit_result("test_trailing.py", trailing, lambda a: a.add_import("import sys"), newline)
        _exact(f"{label} trailing blank lines kept (add_import)", result,
               trailing.replace("import os\n", "import os\nimport sys\n").replace("\n", newline))
        result = _edit_result(
            "test_trailing.py", trailing, lambda a: a.insert_in_body("f", "    x = 2", at="top"), newline
        )
        _exact(f"{label} trailing blank lines kept (insert_in_body)", result,
               trailing.replace("    return 1", "    x = 2\n    return 1").replace("\n", newline))
    for label, content, action, expected in [
        ("delete the last function", "a = 1\n\n\ndef f():\n    pass\n",
         lambda a: a.delete_symbol("f"), "a = 1\n"),
        ("delete the last method", "class A:\n    def f(self):\n        pass\n\n    def g(self):\n        pass\n",
         lambda a: a.delete_symbol("A.g"), "class A:\n    def f(self):\n        pass\n"),
        ("delete the last function, one trailing blank line", "a = 1\n\n\ndef f():\n    pass\n\n",
         lambda a: a.delete_symbol("f"), "a = 1\n\n"),
        ("content ending in blank lines at the end", "a = 1\n",
         lambda a: a.add_top_level("def g():\n    pass\n\n"), "a = 1\n\n\ndef g():\n    pass\n"),
    ]:
        _exact(f"trailing blank lines not added ({label})", _edit_result("test_trailing.py", content, action), expected)


def test_replace_signature_indentation():
    print("\n═══ replace_signature: caller indentation ═══")

    # Signatures given with or without the method's own indentation must
    # land at the definition's column (indented input used to double it).
    # (fixture, label, target, new signature, text expected in the result)
    py_get = "\n\n    def get(self, key, default=None):\n        return self.items.get(key)\n"
    py_multiline = "\n\n    def get(\n        self,\n        key,\n    ):\n        return self.items.get(key)\n"
    js_get = "\n\n    get(key, fallback) {\n        return this.items.get(key);\n    }\n}\n"
    cases = [
        ("py", "indented", "LRUCache.get", "    def get(self, key, default=None):", py_get),
        ("py", "unindented", "LRUCache.get", "def get(self, key, default=None):", py_get),
        (
            "py",
            "over-indented with blank lines around it",
            "LRUCache.get",
            "\n        def get(self, key, default=None):\n",
            py_get,
        ),
        (
            "py",
            "indented multi-line",
            "LRUCache.get",
            "    def get(\n        self,\n        key,\n    ):",
            py_multiline,
        ),
        (
            "py",
            "multi-line as read_symbol returns it",
            "LRUCache.get",
            "def get(\n        self,\n        key,\n    ):",
            py_multiline,
        ),
        (
            "py_decorated",
            "indented, decorated",
            "MyApp.name",
            "    def name(self) -> str:",
            "    @property\n    def name(self) -> str:\n        return self._name\n",
        ),
        ("js", "indented", "LRUCache.get", "    get(key, fallback)", js_get),
        ("js", "unindented", "LRUCache.get", "get(key, fallback)", js_get),
        (
            "ts",
            "indented",
            "LRUCache.get",
            "    get(key: string, fallback?: number): number | undefined",
            "\n\n    get(key: string, fallback?: number): number | undefined {\n        return",
        ),
        (
            "java",
            "indented",
            "LRUCache.get",
            "    public String get(String key, String fallback)",
            "\n\n    public String get(String key, String fallback) {\n        return items.get(key);",
        ),
        (
            "java",
            "indented, with annotation",
            "LRUCache.toString",
            "    @Override\n    public synchronized String toString()",
            "\n\n    @Override\n    public synchronized String toString() {\n        return",
        ),
        (
            "cpp",
            "indented",
            "Calculator.add",
            "    int add(int a, int b, int c)",
            "public:\n    int add(int a, int b, int c) {\n        return a + b;",
        ),
        (
            "go",
            "indented",
            "Cache.Get",
            "\tfunc (c *Cache) Get(key string, fallback string) string",
            "\n\nfunc (c *Cache) Get(key string, fallback string) string {\n\treturn c.items[key]",
        ),
    ]
    for lang, label, target, signature, expected in cases:
        path = reset_fixture(lang)
        try:
            Applier(path).replace_signature(target, signature)
            result = read_file(path)
        except ApplierError as e:
            result = f"REFUSED: {e}"
        check(f"{lang} replace_signature ({label})", result, expected)

    # Unindented signatures whose later lines sit left of the definition
    # (a decorator line, or parameters written relative to the def) are
    # re-based onto the method's column as a whole.
    py_class = (
        "class C:\n    @cached\n    def a(self):\n        return 1\n\n"
        "    def b(self, x):\n        return x\n"
    )
    for label, name, content, target, signature, expected in [
        ("py new decorator", "s.py", py_class, "C.b", "@staticmethod\ndef b(x):",
         py_class.replace("    def b(self, x):", "    @staticmethod\n    def b(x):")),
        ("py replacing the decorator", "s.py", py_class, "C.a", "@memo\ndef a(self):",
         py_class.replace("@cached", "@memo")),
        ("py multi-line parameters", "s.py", py_class, "C.b", "def b(\n    self,\n    x,\n):",
         py_class.replace("    def b(self, x):", "    def b(\n        self,\n        x,\n    ):")),
        ("java new annotation", "s.java",
         "class A {\n    @Override\n    public String toString() {\n        return \"\";\n    }\n}\n",
         "A.toString", "@Nonnull\npublic String toString()",
         "class A {\n    @Nonnull\n    public String toString() {\n        return \"\";\n    }\n}\n"),
        ("ts new decorator", "s.ts",
         "class K {\n  @Old()\n  name(a: string): void {\n    return;\n  }\n}\n",
         "K.name", "@New()\nname(a: string): void",
         "class K {\n  @New()\n  name(a: string): void {\n    return;\n  }\n}\n"),
        ("ts multi-line parameters", "s.ts",
         "class K {\n  name(a: string): void {\n    return;\n  }\n}\n",
         "K.name", "name(\n  a: string,\n  b: number,\n): void",
         "class K {\n  name(\n    a: string,\n    b: number,\n  ): void {\n    return;\n  }\n}\n"),
    ]:
        result = _edit_result(name, content, lambda a: a.replace_signature(target, signature))
        _exact(f"replace_signature unindented ({label})", result, expected)

# ──────────────────────────────────────────────
# add_key on JS/TS objects, duplicate keys, entry layout; Java annotations;
# edit_leading_comment / add_parameter validation; tool names in the docs
# ──────────────────────────────────────────────


def _exact(label: str, result: str, expected: str):
    """check() that result equals expected exactly."""
    check(label, "PASS" if result == expected else f"FAIL, got:\n{result!r}", "PASS")


def _edit_result(name: str, content: str, action, newline: str = "\n") -> str:
    """Write tests/<name>, run action(Applier) on it and return the new file
    text (CRLF kept), or 'REFUSED: <error>' with the file left untouched;
    the file is removed afterwards."""
    path = _write_temp(name, content, newline)
    before = _read_bytes(path)
    try:
        action(Applier(path))
        result = _read_bytes(path).decode("utf-8")
    except ApplierError as e:
        result = f"REFUSED: {e}"
        if _read_bytes(path) != before:
            result += " [FILE CHANGED]"
    os.remove(path)
    return result


def test_add_key_jsts():
    print("\n═══ add_key (JS/TS object literals) ═══")

    # (label, file name, content, parent_target, key, value, expected file)
    cases = [
        (
            "ts multi-line, trailing comma",
            "t.ts",
            "const CONFIG = {\n  port: 3000,\n  debug: true,\n};\n",
            "CONFIG", "host", '"localhost"',
            'const CONFIG = {\n  port: 3000,\n  debug: true,\n  host: "localhost",\n};\n',
        ),
        (
            "js multi-line, no trailing comma",
            "t.js",
            "const CONFIG = {\n    port: 3000,\n    debug: true\n};\n",
            "CONFIG", "host", "'h'",
            "const CONFIG = {\n    port: 3000,\n    debug: true,\n    host: 'h'\n};\n",
        ),
        (
            "js single-line",
            "t.js",
            "const C = { a: 1, b: 2 };\n",
            "C", "c", "3",
            "const C = { a: 1, b: 2, c: 3 };\n",
        ),
        (
            "ts single-line, trailing comma",
            "t.ts",
            "const C = { a: 1, };\n",
            "C", "b", "2",
            "const C = { a: 1, b: 2, };\n",
        ),
        (
            "ts empty object in export const",
            "t.ts",
            "export const C = {};\n",
            "C", "a", "1",
            "export const C = { a: 1 };\n",
        ),
        (
            "js empty multi-line object",
            "t.js",
            "function f() {\n  return 1;\n}\nlet C = {\n};\n",
            "C", "a", "1",
            "function f() {\n  return 1;\n}\nlet C = {\n  a: 1,\n};\n",
        ),
        (
            "js empty multi-line object, tab-indented file",
            "t.js",
            "function f() {\n\treturn 1;\n}\nvar C = {\n};\n",
            "C", "a", "1",
            "function f() {\n\treturn 1;\n}\nvar C = {\n\ta: 1,\n};\n",
        ),
        (
            "ts key needing quotes, double-quote file",
            "t.ts",
            'import x from "x";\nconst C = {\n  a: 1,\n};\n',
            "C", "my-key", "2",
            'import x from "x";\nconst C = {\n  a: 1,\n  "my-key": 2,\n};\n',
        ),
        (
            "js key needing quotes, single-quote file",
            "t.js",
            "const C = { a: 'x', b: 'y' };\n",
            "C", "my key", "1",
            "const C = { a: 'x', b: 'y', 'my key': 1 };\n",
        ),
        (
            "js numeric key stays bare",
            "t.js",
            "const C = { a: 1 };\n",
            "C", "42", "'n'",
            "const C = { a: 1, 42: 'n' };\n",
        ),
        (
            "js $ identifier stays bare",
            "t.js",
            'const C = { a: "x" };\n',
            "C", "$el", "1",
            'const C = { a: "x", $el: 1 };\n',
        ),
        (
            "js leading-zero number is quoted",
            "t.js",
            'const C = { a: "x" };\n',
            "C", "007", "1",
            'const C = { a: "x", "007": 1 };\n',
        ),
        (
            "ts key given in quotes is kept",
            "t.ts",
            "const C = { a: 1 };\n",
            "C", "'x-y'", "2",
            "const C = { a: 1, 'x-y': 2 };\n",
        ),
        (
            "ts nested object",
            "t.ts",
            'export const CONFIG = {\n  port: 3000,\n  server: {\n    host: "h",\n  },\n};\n',
            "CONFIG.server", "port", "80",
            'export const CONFIG = {\n  port: 3000,\n  server: {\n    host: "h",\n    port: 80,\n  },\n};\n',
        ),
        (
            "js deeply nested, quoted segment",
            "t.js",
            "const C = {\n  'dev-server': {\n    tls: { cert: 'c' },\n  },\n};\n",
            "C.\"dev-server\".tls", "key", "'k'",
            "const C = {\n  'dev-server': {\n    tls: { cert: 'c', key: 'k' },\n  },\n};\n",
        ),
        (
            "js comment on the last entry's line stays there",
            "t.js",
            "const C = {\n  a: 1, // first\n  b: 2, // second\n};\n",
            "C", "c", "3",
            "const C = {\n  a: 1, // first\n  b: 2, // second\n  c: 3,\n};\n",
        ),
        (
            "ts `as const` object",
            "t.ts",
            "export const C = {\n  a: 1,\n} as const;\n",
            "C", "b", "2",
            "export const C = {\n  a: 1,\n  b: 2,\n} as const;\n",
        ),
        (
            "ts `satisfies` object",
            "t.ts",
            "const C = {\n  a: 1\n} satisfies Record<string, number>;\n",
            "C", "b", "2",
            "const C = {\n  a: 1,\n  b: 2\n} satisfies Record<string, number>;\n",
        ),
        (
            "js after a spread and a method",
            "t.js",
            "const C = {\n  ...base,\n  get(k) {\n    return k;\n  },\n};\n",
            "C", "a", "1",
            "const C = {\n  ...base,\n  get(k) {\n    return k;\n  },\n  a: 1,\n};\n",
        ),
        (
            ".mjs file",
            "t.mjs",
            "export const C = { a: 1 };\n",
            "C", "b", "2",
            "export const C = { a: 1, b: 2 };\n",
        ),
        (
            ".tsx file",
            "t.tsx",
            "const C = { a: 1 };\nexport const App = () => <div />;\n",
            "C", "b", "2",
            "const C = { a: 1, b: 2 };\nexport const App = () => <div />;\n",
        ),
    ]
    for label, name, content, parent, key, value, expected in cases:
        result = _edit_result(name, content, lambda a: a.add_key(parent, key, value))
        _exact(f"add_key {label}", result, expected)

    result = _edit_result(
        "t.ts",
        "const C = {\n  a: 1,\n};\n",
        lambda a: a.add_key("C", "b", "2"),
        newline="\r\n",
    )
    _exact("add_key ts: CRLF file stays CRLF", result, "const C = {\r\n  a: 1,\r\n  b: 2,\r\n};\r\n")

    # Targets that do not name an object literal are refused, file untouched.
    content = "const CONFIG = {\n  port: 3000,\n  server: { host: 'h' },\n};\n"
    refusals = [
        ("missing variable", "MISSING", "not found as a module-level const/let/var"),
        ("nested value is not an object", "CONFIG.port", "'CONFIG.port' is not an object literal"),
        ("missing nested key", "CONFIG.nope", "Key 'nope' not found in CONFIG"),
        ("empty parent_target", "", "parent_target must be the name of a module-level"),
    ]
    for label, parent, fragment in refusals:
        result = _edit_result("t.js", content, lambda a: a.add_key(parent, "x", "1"))
        check(f"add_key js refused ({label})", result, "REFUSED: ")
        check(f"add_key js refused ({label}): message", result, fragment)
        check(
            f"add_key js refused ({label}): file untouched",
            "PASS" if "[FILE CHANGED]" not in result else "FAIL",
            "PASS",
        )

    # Through the MCP tool.
    from ast_editor import server

    path = _write_temp("t.ts", "export const CONFIG = {\n  port: 3000,\n};\n")
    check("server add_key ts: reply", server.add_key(path, "CONFIG", "host", '"h"'), "Added")
    check("server add_key ts: key written", read_file(path), '  port: 3000,\n  host: "h",\n};')
    os.remove(path)


def test_add_key_duplicates():
    print("\n═══ add_key: refuses keys that already exist ═══")

    # (label, file name, content, parent_target, key, fragments of the error)
    cases = [
        ("json nested", "d.json", '{\n  "deps": {\n    "mcp": "1"\n  }\n}\n',
         "deps", "mcp", ("Key 'mcp' already exists in 'deps'", "target 'deps.mcp'")),
        ("json root", "d.json", '{"a": 1}\n',
         "", "a", ("already exists in the root", "target 'a'")),
        ("json key given quoted", "d.json", '{"a": 1}\n',
         "", '"a"', ("already exists",)),
        ("yaml", "d.yaml", "project:\n  name: x\n  version: '1'\n",
         "project", "version", ("Key 'version' already exists in 'project'", "target 'project.version'")),
        ("yaml quoted key in file", "d.yaml", 'project:\n  "name": x\n',
         "project", "name", ("already exists",)),
        ("toml table", "d.toml", '[project]\nname = "x"\n',
         "project", "name", ("Key 'name' already exists in 'project'", "target 'project.name'")),
        ("toml root", "d.toml", 'title = "t"\n\n[project]\nname = "x"\n',
         "", "title", ("already exists in the root", "target 'title'")),
        ("toml dotted key", "d.toml", '[project]\nurls.home = "h"\n',
         "project", "urls", ("already exists",)),
        ("toml sub-table", "d.toml", '[project]\nname = "x"\n\n[project.urls]\nhome = "h"\n',
         "project", "urls", ("already exists",)),
        # A dotted key may not reopen a table that has its own [header].
        ("toml dotted key into a [table]'s key", "d.toml", "x = 1\n\n[a]\nc = 2\n",
         "", "a.c", ("Key 'a.c' already exists in the root",)),
        ("toml dotted key into a [table]", "d.toml", "x = 1\n\n[a]\nc = 2\n",
         "", "a.b", ("already exists",)),
        ("toml dotted key into a [sub.table]", "d.toml", "[p]\nx = 1\n\n[p.q]\ns = 1\n",
         "p", "q.r", ("Key 'q.r' already exists in 'p'", "target 'p.q.r'")),
        ("python same quotes", "d.py", 'CONFIG = {"a": 1}\n',
         "CONFIG", '"a"', ("Key '\"a\"' already exists in 'CONFIG'", "target 'CONFIG.\"a\"'")),
        ("python other quotes", "d.py", 'CONFIG = {"a": 1}\n',
         "CONFIG", "'a'", ("already exists",)),
        ("python nested dict", "d.py", 'CONFIG = {"db": {"host": "h"}}\n',
         'CONFIG."db"', '"host"', ("already exists in 'CONFIG.\"db\"'",)),
        ("js identifier vs quoted", "d.js", "const C = { port: 1 };\n",
         "C", '"port"', ("already exists in 'C'", "target 'C.\"port\"'")),
        ("js quoted vs bare", "d.js", "const C = { 'my-key': 1 };\n",
         "C", "my-key", ("already exists",)),
        ("js shorthand", "d.js", "const C = { name };\n",
         "C", "name", ("already exists",)),
        ("js method", "d.js", "const C = { run() { return 1; } };\n",
         "C", "run", ("already exists",)),
        ("ts nested", "d.ts", "export const C = {\n  server: { port: 1 },\n};\n",
         "C.server", "port", ("already exists in 'C.server'", "target 'C.server.port'")),
    ]
    for label, name, content, parent, key, fragments in cases:
        result = _edit_result(name, content, lambda a: a.add_key(parent, key, "2"))
        check(f"add_key duplicate ({label}): refused", result, "REFUSED: ")
        check(f"add_key duplicate ({label}): suggests replace_value", result, "use replace_value")
        for fragment in fragments:
            check(f"add_key duplicate ({label}): {fragment}", result, fragment)
        check(
            f"add_key duplicate ({label}): file untouched",
            "PASS" if "[FILE CHANGED]" not in result else "FAIL",
            "PASS",
        )

    # Dotted keys that only share a prefix with a table, or that sit beside
    # an unrelated one, are still allowed, and the result is valid TOML.
    import tomllib

    for label, content, parent, key, expected in [
        ("beside [a.y]", "x = 1\n\n[a.y]\nz = 1\n", "", "a.x", "x = 1\na.x = 1\n\n[a.y]\n"),
        ("beside [p.q.t]", "[p]\nx = 1\n\n[p.q.t]\nz = 1\n", "p", "q.r", "[p]\nx = 1\nq.r = 1\n\n[p.q.t]\n"),
        ("beside a.b", "a.b = 1\n", "", "a.c", "a.b = 1\na.c = 1\n"),
        ("beside [pp.a]", "x = 1\n\n[pp.a]\nz = 1\n", "", "a", "x = 1\na = 1\n\n[pp.a]\n"),
    ]:
        result = _edit_result("d.toml", content, lambda a: a.add_key(parent, key, "1"))
        check(f"add_key toml {key} {label}: allowed", result, expected)
        try:
            tomllib.loads(result)
            valid = "PASS"
        except tomllib.TOMLDecodeError as e:
            valid = f"FAIL: {e}"
        check(f"add_key toml {key} {label}: valid TOML", valid, "PASS")

    # The suggested replace_value target works, including for dict and
    # object literals.
    for name, content, target, expected in [
        ("r.py", 'CONFIG = {"db": {"host": "h"}}\n', 'CONFIG."db"."host"',
         'CONFIG = {"db": {"host": "new"}}\n'),
        ("r.js", "const C = {\n  server: { port: 1 },\n};\n", "C.server.port",
         "const C = {\n  server: { port: \"new\" },\n};\n"),
        ("r.ts", "const C = { name };\n", "C.name", 'const C = { name: "new" };\n'),
        ("r.toml", '[project]\nname = "x"\n', "project.name", '[project]\nname = "new"\n'),
    ]:
        result = _edit_result(name, content, lambda a: a.replace_value(target, '"new"'))
        _exact(f"replace_value {name} {target}", result, expected)

    for name, content, target, fragment in [
        ("r.js", "const C = { a: 1 };\n", "C.nope", "Target 'C.nope' not found (Key 'nope' not found in C)"),
        ("r.ts", "class K {\n  a() {}\n}\n", "K.b", "Target 'K.b' not found ('K' not found as a module-level"),
        ("r.py", 'C = {"a": 1}\n', 'C."b"', "Target 'C.\"b\"' not found (Key \"b\" not found in dict 'C')"),
    ]:
        result = _edit_result(name, content, lambda a: a.replace_value(target, "2"))
        check(f"replace_value {name} {target}: refused", result, fragment)

    from ast_editor import server

    path = _write_temp("d.json", '{"a": 1}\n')
    reply = server.add_key(path, "", "a", "2")
    check("server add_key duplicate: reply", reply, "Cannot perform edit: Key 'a' already exists")
    check("server add_key duplicate: file untouched", read_file(path), '{"a": 1}\n')
    os.remove(path)


def test_add_key_layout():
    print("\n═══ add_key / delete_key: layout of JSON objects and Python dicts ═══")

    # add_key follows the container's layout in JSON and Python too.
    cases = [
        ("json single-line object", "l.json", '{"a": 1}\n', "", "b", "2", '{"a": 1, "b": 2}\n'),
        ("json key is escaped", "l.json", '{\n  "a": 1\n}\n', "", 'say "hi"', "2",
         '{\n  "a": 1,\n  "say \\"hi\\"": 2\n}\n'),
        ("json empty object, 4-space file", "l.json", '{\n    "deps": {}\n}\n', "deps", "x", '"1"',
         '{\n    "deps": {\n        "x": "1"\n    }\n}\n'),
        ("json empty object on two lines", "l.json", '{\n  "deps": {\n  }\n}\n', "deps", "x", "1",
         '{\n  "deps": {\n    "x": 1\n  }\n}\n'),
        ("python single-line dict", "l.py", 'CONFIG = {"a": 1, "b": 2}\n', "CONFIG", '"c"', "3",
         'CONFIG = {"a": 1, "b": 2, "c": 3}\n'),
        ("python multi-line, trailing comma", "l.py", 'CONFIG = {\n    "a": 1,\n}\n', "CONFIG", '"b"', "2",
         'CONFIG = {\n    "a": 1,\n    "b": 2,\n}\n'),
        ("python comment after the last entry", "l.py", 'CONFIG = {\n    "a": 1,  # one\n}\n',
         "CONFIG", '"b"', "2", 'CONFIG = {\n    "a": 1,  # one\n    "b": 2,\n}\n'),
        ("python after a ** spread", "l.py", 'CONFIG = {"a": 1, **BASE}\n', "CONFIG", '"b"', "2",
         'CONFIG = {"a": 1, **BASE, "b": 2}\n'),
        ("python empty dict", "l.py", "CONFIG = {}\n", "CONFIG", '"a"', "1", 'CONFIG = {\n    "a": 1,\n}\n'),
        ("python nested dict", "l.py", 'CONFIG = {\n    "db": {\n        "host": "h"\n    },\n}\n',
         'CONFIG."db"', '"port"', "5432",
         'CONFIG = {\n    "db": {\n        "host": "h",\n        "port": 5432\n    },\n}\n'),
        ("python class attribute dict", "l.py", 'class S:\n    D = {"a": 1}\n', "S.D", '"b"', "2",
         'class S:\n    D = {"a": 1, "b": 2}\n'),
    ]
    for label, name, content, parent, key, value, expected in cases:
        result = _edit_result(name, content, lambda a: a.add_key(parent, key, value))
        _exact(f"add_key {label}", result, expected)

    # delete_key resolves the same nested paths, and deleting the only entry
    # leaves `{}` instead of a stray trailing comma (invalid JS that the
    # grammar accepts).
    deletes = [
        ("js nested", "x.js", "const C = {\n  server: { host: 'h', port: 1 },\n};\n", "C.server.host",
         "const C = {\n  server: { port: 1 },\n};\n"),
        ("ts only entry, trailing comma", "x.ts", "const C = {\n  a: 1,\n};\n", "C.a", "const C = {};\n"),
        ("ts only entry of a nested object", "x.ts", "const C = { s: { a: 1 } };\n", "C.s.a",
         "const C = { s: {} };\n"),
        ("js quoted key containing a dot", "x.js", "const C = { 'a.b': 1, c: 2 };\n", "C.\"a.b\"",
         "const C = { c: 2 };\n"),
        ("python only entry, trailing comma", "x.py", 'C = {\n    "a": 1,\n}\n', 'C."a"', "C = {}\n"),
        ("python nested", "x.py", 'C = {"db": {"host": "h", "port": 1}}\n', 'C."db"."port"',
         'C = {"db": {"host": "h"}}\n'),
        ("json only entry", "x.json", '{\n  "d": {\n    "a": 1\n  }\n}\n', "d.a", '{\n  "d": {}\n}\n'),
    ]
    for label, name, content, target, expected in deletes:
        result = _edit_result(name, content, lambda a: a.delete_key(target))
        _exact(f"delete_key {label}", result, expected)

    # An entry on its own line goes with that whole line, its same-line
    # comment included, so the neighbours keep their own comments; a last
    # entry without a trailing comma also takes the comma before it.
    deletes = [
        ("js last entry, same-line comments", "x.js", "const C = {\n  a: 1, // one\n  b: 2, // two\n};\n",
         "C.b", "const C = {\n  a: 1, // one\n};\n"),
        ("js first entry, same-line comments", "x.js", "const C = {\n  a: 1, // one\n  b: 2, // two\n};\n",
         "C.a", "const C = {\n  b: 2, // two\n};\n"),
        ("js last entry, no trailing comma", "x.js", "const C = {\n  a: 1, // one\n  b: 2 // two\n};\n",
         "C.b", "const C = {\n  a: 1 // one\n};\n"),
        ("js only entry below a comment", "x.js", "const C = {\n  // c\n  a: 1,\n};\n", "C.a",
         "const C = {\n  // c\n};\n"),
        ("js multi-line value", "x.js", "const C = {\n  a: 1,\n  b: {\n    x: 1,\n  }, // obj\n  c: 3,\n};\n",
         "C.b", "const C = {\n  a: 1,\n  c: 3,\n};\n"),
        ("js entry sharing its line", "x.js", "const C = {\n  a: 1,\n  b: 2, c: 3\n};\n", "C.b",
         "const C = {\n  a: 1,\n  c: 3\n};\n"),
        ("python same-line comments", "x.py", 'C = {\n    "a": 1,  # one\n    "b": 2,  # two\n}\n',
         'C."b"', 'C = {\n    "a": 1,  # one\n}\n'),
        ("python no trailing comma", "x.py", 'C = {\n    "a": 1,  # one\n    "b": 2  # two\n}\n',
         'C."b"', 'C = {\n    "a": 1  # one\n}\n'),
        ("json last entry", "x.json", '{\n  "a": 1,\n  "b": 2\n}\n', "b", '{\n  "a": 1\n}\n'),
        ("jsonc same-line comments", "x.json", '{\n  "a": 1, // one\n  "b": 2 // two\n}\n', "b",
         '{\n  "a": 1 // one\n}\n'),
    ]
    for label, name, content, target, expected in deletes:
        result = _edit_result(name, content, lambda a: a.delete_key(target))
        _exact(f"delete_key {label}", result, expected)


def test_java_signature_annotations():
    print("\n═══ replace_signature: decorators and annotations ═══")

    def java(body: str) -> str:
        return "class B {\n" + body + "}\n"

    # (label, file, content, target, new signature, expected file)
    cases = [
        (
            "java annotation on its own line kept",
            "s.java",
            java("    @Override\n    public String toString() {\n        return \"\";\n    }\n"),
            "B.toString",
            "public synchronized String toString()",
            java("    @Override\n    public synchronized String toString() {\n        return \"\";\n    }\n"),
        ),
        (
            "java several annotations on their own lines kept",
            "s.java",
            java("    @Override\n    @Deprecated\n    public String a() {\n        return \"\";\n    }\n"),
            "B.a",
            "    public String a(int x)",
            java("    @Override\n    @Deprecated\n    public String a(int x) {\n        return \"\";\n    }\n"),
        ),
        (
            "java annotations on the same line kept",
            "s.java",
            java("    @Override @Deprecated public String a() { return \"\"; }\n"),
            "B.a",
            "public String a(int x)",
            java("    @Override @Deprecated public String a(int x) { return \"\"; }\n"),
        ),
        (
            "java annotation with arguments and a comment kept",
            "s.java",
            java("    @SuppressWarnings(\"unchecked\") // legacy\n    B(int x) { }\n"),
            "B.B",
            "public B(int x, int y)",
            java("    @SuppressWarnings(\"unchecked\") // legacy\n    public B(int x, int y) { }\n"),
        ),
        (
            "java annotation after a modifier moved in front",
            "s.java",
            java("    public @Deprecated String a() { return \"\"; }\n"),
            "B.a",
            "public String a(int x)",
            java("    @Deprecated public String a(int x) { return \"\"; }\n"),
        ),
        (
            "java new annotation replaces the old one",
            "s.java",
            java("    @Override\n    public String a() { return \"\"; }\n"),
            "B.a",
            "@Deprecated\n    public String a(int x)",
            java("    @Deprecated\n    public String a(int x) { return \"\"; }\n"),
        ),
        (
            "java new annotations on the same line replace the old ones",
            "s.java",
            java("    @Override\n    @Deprecated\n    public String a() { return \"\"; }\n"),
            "B.a",
            "@Override public String a(int x)",
            java("    @Override public String a(int x) { return \"\"; }\n"),
        ),
        (
            "java parameter annotations do not count as the method's",
            "s.java",
            java("    @Override\n    public String a() { return \"\"; }\n"),
            "B.a",
            "public String a(@Deprecated String x)",
            java("    @Override\n    public String a(@Deprecated String x) { return \"\"; }\n"),
        ),
        (
            "js decorator kept",
            "s.js",
            "class A {\n  @dec()\n  foo(x) {\n    return x;\n  }\n}\n",
            "A.foo",
            "foo(x, y)",
            "class A {\n  @dec()\n  foo(x, y) {\n    return x;\n  }\n}\n",
        ),
        (
            "js new decorator replaces the old one",
            "s.js",
            "class A {\n  @dec()\n  foo(x) {\n    return x;\n  }\n}\n",
            "A.foo",
            "@other\n  foo(x, y)",
            "class A {\n  @other\n  foo(x, y) {\n    return x;\n  }\n}\n",
        ),
        (
            "ts decorator kept",
            "s.ts",
            "class A {\n  @dec()\n  foo(x: number): void {\n    return;\n  }\n}\n",
            "A.foo",
            "foo(x: number, y: number): void",
            "class A {\n  @dec()\n  foo(x: number, y: number): void {\n    return;\n  }\n}\n",
        ),
        (
            "ts new decorator replaces the old ones",
            "s.ts",
            "class A {\n  @a()\n  @b\n  foo(x: number): void {\n    return;\n  }\n}\n",
            "A.foo",
            "  @c\n  foo(x: number): void",
            "class A {\n  @c\n  foo(x: number): void {\n    return;\n  }\n}\n",
        ),
        (
            "ts parameter decorators do not count as the method's",
            "s.ts",
            "class A {\n  @dec()\n  foo(x: number): void {\n    return;\n  }\n}\n",
            "A.foo",
            "foo(@Inject() x: number): void",
            "class A {\n  @dec()\n  foo(@Inject() x: number): void {\n    return;\n  }\n}\n",
        ),
        (
            "python new decorator replaces the old one",
            "s.py",
            "class A:\n    @property\n    def n(self):\n        return 1\n",
            "A.n",
            "    @cached_property\n    def n(self):",
            "class A:\n    @cached_property\n    def n(self):\n        return 1\n",
        ),
        (
            "python decorator kept without one in the signature",
            "s.py",
            "class A:\n    @property\n    def n(self):\n        return 1\n",
            "A.n",
            "def n(self) -> int:",
            "class A:\n    @property\n    def n(self) -> int:\n        return 1\n",
        ),
    ]
    for label, name, content, target, signature, expected in cases:
        result = _edit_result(name, content, lambda a: a.replace_signature(target, signature))
        _exact(f"replace_signature {label}", result, expected)

    # The shared fixture: @Override on toString survives a plain signature.
    path = reset_fixture("java")
    Applier(path).replace_signature("LRUCache.toString", "public synchronized String toString()")
    check(
        "java fixture: @Override kept",
        read_file(path),
        "    @Override\n    public synchronized String toString() {\n",
    )


def test_comment_and_parameter_validation():
    print("\n═══ edit_leading_comment op='add' / add_parameter position checks ═══")

    # op="add" is refused when the symbol already has a leading comment.
    refusals = [
        ("python # comment", "c.py", "# Existing\ndef f():\n    pass\n", "f", "# New",
         "'f' already has a leading comment (line 1)"),
        ("js block comment", "c.js", "/**\n * Doc\n */\nfunction f() {}\n", "f", "// New",
         "(lines 1-3)"),
        ("java javadoc on a method", "c.java",
         "class B {\n    /** Doc */\n    @Override\n    public String toString() { return \"\"; }\n}\n",
         "B.toString", "// New", "already has a leading comment (line 2)"),
        ("yaml", "c.yaml", "# Section\nproject:\n  name: x\n", "project", "# New",
         "already has a leading comment"),
    ]
    for label, name, content, target, comment, fragment in refusals:
        result = _edit_result(name, content, lambda a: a.edit_leading_comment(target, "add", comment))
        check(f"edit_leading_comment add refused ({label})", result, "REFUSED: ")
        check(f"edit_leading_comment add refused ({label}): message", result, fragment)
        check(f"edit_leading_comment add refused ({label}): suggests replace", result, "Use op='replace'")
        check(
            f"edit_leading_comment add refused ({label}): file untouched",
            "PASS" if "[FILE CHANGED]" not in result else "FAIL",
            "PASS",
        )

    # The refusal quotes the existing lines, so a directive such as
    # eslint-disable-next-line can be carried over into op="replace".
    for label, name, content, target, quoted in [
        ("eslint directive", "c.js", "// eslint-disable-next-line no-unused-vars\nfunction f() {}\n",
         "f", "(line 1):\n// eslint-disable-next-line no-unused-vars\nUse op='replace'"),
        ("go directive", "c.go", "package main\n\n//go:noinline\nfunc f() {}\n",
         "f", "(line 3):\n//go:noinline\nUse op='replace'"),
        ("indented javadoc", "c.java", "class B {\n    /**\n     * Doc\n     */\n    void f() {}\n}\n",
         "B.f", "(lines 2-4):\n/**\n* Doc\n*/\nUse op='replace'"),
    ]:
        result = _edit_result(name, content, lambda a: a.edit_leading_comment(target, "add", "// New"))
        check(f"edit_leading_comment add refused ({label}): quotes the lines", result, quoted)
        check(f"edit_leading_comment add refused ({label}): mentions directives", result,
              "includes any of these lines you want to keep (e.g. lint or compiler directives)")

    # A /* ... */ after code on the line above is that code's comment, not
    # the symbol's leading comment: add goes ahead and the code is kept.
    for label, name, content, target, expected in [
        ("c", "c.c", "int x = 1; /* trailing */\nint f(void) { return 0; }\n", "f",
         "int x = 1; /* trailing */\n// New\nint f(void) { return 0; }\n"),
        ("js", "c.js", "const x = 1; /* note */\nfunction f() {}\n", "f",
         "const x = 1; /* note */\n// New\nfunction f() {}\n"),
        ("java field", "c.java", "class A {\n    int x = 1; /* n */\n    void f() {}\n}\n", "A.f",
         "class A {\n    int x = 1; /* n */\n    // New\n    void f() {}\n}\n"),
        ("c block opened after code", "c.c",
         "int x = 1; /* starts here\n   ends here */\nint f(void) { return 0; }\n", "f",
         "int x = 1; /* starts here\n   ends here */\n// New\nint f(void) { return 0; }\n"),
        ("block comments around code", "c.c", "/* a */ int x = 1; /* b */\nint f(void) { return 0; }\n", "f",
         "/* a */ int x = 1; /* b */\n// New\nint f(void) { return 0; }\n"),
        ("js regex ending in */", "c.js", "import x from \"y\";\nconst r = /a*/\nfunction f() {}\n", "f",
         "import x from \"y\";\nconst r = /a*/\n// New\nfunction f() {}\n"),
    ]:
        result = _edit_result(name, content, lambda a: a.edit_leading_comment(target, "add", "// New"))
        _exact(f"edit_leading_comment add after trailing block comment ({label})", result, expected)
    for op, comment in (("replace", "// New"), ("remove", "")):
        result = _edit_result(
            "c.c",
            "int x = 1; /* trailing */\nint f(void) { return 0; }\n",
            lambda a: a.edit_leading_comment("f", op, comment),
        )
        expected = (
            "int x = 1; /* trailing */\n// New\nint f(void) { return 0; }\n"
            if op == "replace"
            else "REFUSED: No leading comment found above 'f'"
        )
        _exact(f"edit_leading_comment {op} after trailing block comment: code kept", result, expected)

    # A comment separated by a blank line is not the symbol's own.
    result = _edit_result(
        "c.py",
        "# Section header\n\ndef f():\n    pass\n",
        lambda a: a.edit_leading_comment("f", "add", "# Does f"),
    )
    _exact("edit_leading_comment add: blank line separates", result,
           "# Section header\n\n# Does f\ndef f():\n    pass\n")

    # A YAML key whose value is a mapping gets its comment above the key,
    # not inside the mapping (the value node starts on the next line).
    result = _edit_result(
        "c.yaml",
        "project:\n  name: x\n  urls:\n    home: h\n",
        lambda a: a.edit_leading_comment("project", "add", "# Project"),
    )
    _exact("edit_leading_comment add yaml: above a mapping key", result,
           "# Project\nproject:\n  name: x\n  urls:\n    home: h\n")
    result = _edit_result(
        "c.yaml",
        "project:\n  name: x\n  urls:\n    home: h\n",
        lambda a: a.edit_leading_comment("project.urls", "add", "# Links"),
    )
    _exact("edit_leading_comment add yaml: above a nested mapping key", result,
           "project:\n  name: x\n  # Links\n  urls:\n    home: h\n")
    result = _edit_result(
        "c.yaml",
        "# Old\nproject:\n  name: x\n",
        lambda a: a.edit_leading_comment("project", "replace", "# New"),
    )
    _exact("edit_leading_comment replace yaml: mapping key", result, "# New\nproject:\n  name: x\n")

    # The unsupported-format message names the real tool.
    result = _edit_result("c.json", '{"a": 1}\n', lambda a: a.edit_leading_comment("a", "add", "# x"))
    check("edit_leading_comment json: names the tool", result,
          "edit_leading_comment is not supported for .json files")

    from ast_editor import server

    path = _write_temp("c.py", "# Existing\ndef f():\n    pass\n")
    reply = server.edit_leading_comment(path, "f", "add", "# New")
    check("server edit_leading_comment add: refusal reply", reply,
          "Cannot perform edit: 'f' already has a leading comment")
    os.remove(path)

    # add_parameter accepts only "start" and "end".
    for position in ("middle", "Start", ""):
        result = _edit_result("p.py", "def f(a):\n    pass\n",
                              lambda a: a.add_parameter("f", "b", position))
        check(f"add_parameter position {position!r}: refused", result,
              f"add_parameter: position must be 'start' or 'end', got '{position}'")
        check(
            f"add_parameter position {position!r}: file untouched",
            "PASS" if "[FILE CHANGED]" not in result else "FAIL",
            "PASS",
        )
    for position, expected in (("start", "def f(b, a):"), ("end", "def f(a, b):")):
        result = _edit_result("p.py", "def f(a):\n    pass\n",
                              lambda a: a.add_parameter("f", "b", position))
        check(f"add_parameter position {position!r}: applied", result, expected)

    path = _write_temp("p.py", "def f(a):\n    pass\n")
    reply = server.add_parameter(path, "f", "b", "middle")
    check("server add_parameter bad position: reply", reply, "Cannot perform edit: add_parameter: position")
    os.remove(path)


def test_body_insert_placement():
    print("\n═══ insert_in_body at=top/bottom: placement ═══")
    import tempfile

    # New lines must land at body level whatever the last statement is (a
    # nested block used to pull bottom inserts into its innermost level), and
    # a body sharing a line with its signature or braces is refused.
    # (file, source, target, at, snippet, expected file text or None = refused)
    cases = [
        ("nested.py", "def f(x):\n    if x:\n        for i in range(3):\n            print(i)\n",
         "f", "bottom", "done = 1",
         "def f(x):\n    if x:\n        for i in range(3):\n            print(i)\n    done = 1\n"),
        ("doc.py", 'def f():\n    """Doc."""\n    return 1\n', "f", "top", "x = 1",
         'def f():\n    """Doc."""\n    x = 1\n    return 1\n'),
        ("oneline.py", "def f(): return 1\n", "f", "bottom", "x = 2", None),
        ("nested.js", "function f(x) {\n  if (x) {\n    for (const i of x) {\n      log(i);\n    }\n  }\n}\n",
         "f", "bottom", "done();",
         "function f(x) {\n  if (x) {\n    for (const i of x) {\n      log(i);\n    }\n  }\n  done();\n}\n"),
        ("oneline.js", "function f() { return 1; }\n", "f", "top", "done();", None),
        ("inline_empty.js", "function f() {}\n", "f", "bottom", "done();", None),
        ("empty.js", "function f() {\n}\n", "f", "bottom", "x();", "function f() {\n  x();\n}\n"),
        ("method.ts", "class A {\n  m(): void {\n    if (a) {\n      b();\n    }\n  }\n}\n",
         "A.m", "bottom", "c();",
         "class A {\n  m(): void {\n    if (a) {\n      b();\n    }\n    c();\n  }\n}\n"),
        ("nested.go", "package main\n\nfunc f(x int) {\n\tif x > 0 {\n\t\tprintln(x)\n\t}\n}\n",
         "f", "bottom", 'println("done")',
         'package main\n\nfunc f(x int) {\n\tif x > 0 {\n\t\tprintln(x)\n\t}\n\tprintln("done")\n}\n'),
        ("empty.go", "package main\n\nfunc f() {\n}\n", "f", "top", "x()",
         "package main\n\nfunc f() {\n\tx()\n}\n"),
        ("Nested.java", "class A {\n    void f(int x) {\n        if (x > 0) {\n            g(x);\n        }\n    }\n}\n",
         "A.f", "bottom", "done();",
         "class A {\n    void f(int x) {\n        if (x > 0) {\n            g(x);\n        }\n        done();\n    }\n}\n"),
        ("nested.c", "void f(int x) {\n    if (x) {\n        g(x);\n    }\n}\n", "f", "bottom", "done();",
         "void f(int x) {\n    if (x) {\n        g(x);\n    }\n    done();\n}\n"),
        ("nested_top.rb", "def f(x)\n  if x\n    puts x\n  end\nend\n", "f", "top", "puts 'start'",
         "def f(x)\n  puts 'start'\n  if x\n    puts x\n  end\nend\n"),
        ("nested_bottom.rb", "def f(x)\n  if x\n    puts x\n  end\nend\n", "f", "bottom", "puts 'done'",
         "def f(x)\n  if x\n    puts x\n  end\n  puts 'done'\nend\n"),
        ("flat.rb", "def f(x)\n  a = 1\n  b = 2\nend\n", "f", "top", "puts 'start'",
         "def f(x)\n  puts 'start'\n  a = 1\n  b = 2\nend\n"),
        ("rescue.rb", "def f\n  work\nrescue => e\n  log e\nend\n", "f", "bottom", "more",
         "def f\n  work\n  more\nrescue => e\n  log e\nend\n"),
    ]
    work = tempfile.mkdtemp(prefix="ast-editor-body-")
    try:
        for name, source, target, at, snippet, expected in cases:
            path = os.path.join(work, name)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(source)
            try:
                Applier(path).insert_in_body(target, snippet, at=at)
                outcome = "inserted"
            except ApplierError as e:
                outcome = str(e)
            with open(path, encoding="utf-8", newline="") as f:
                after = f.read()
            if expected is None:
                check(f"body insert {name} at={at}: refused", outcome, "shares a line with its signature or braces")
                check(f"body insert {name} at={at}: file unchanged",
                      "<exact match>" if after == source else after, "<exact match>")
            else:
                check(f"body insert {name} at={at}: placed at body level",
                      "<exact match>" if after == expected else after, "<exact match>")
    finally:
        shutil.rmtree(work, ignore_errors=True)

# ──────────────────────────────────────────────
# JS/TS exports; add_method / add_field layout; decorators and leading comments
# ──────────────────────────────────────────────


def _read_result(name: str, content: str, action) -> str:
    """Write tests/<name>, return what action(Applier) returns (or
    'REFUSED: <error>'), and remove the file."""
    path = _write_temp(name, content)
    try:
        result = action(Applier(path))
    except ApplierError as e:
        result = f"REFUSED: {e}"
    os.remove(path)
    return result


def test_exported_symbols():
    print("\n═══ JS/TS exported symbols: list_symbols and targeting ═══")

    # The reported case, in every JS/TS extension: exported, default-exported
    # and plain declarations are all listed, classes with their methods.
    repro = (
        "export function a() {}\n"
        "function b() {}\n"
        "export default function c() {}\n"
        "export class K { m() {} }\n"
    )
    expected = (
        "function a (line 1)\nfunction b (line 2)\nfunction c (line 3)\n"
        "class K (line 4)\n  method K.m (line 4)"
    )
    for ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
        _exact(
            f"list_symbols {ext}: exported declarations listed",
            _read_result("exports" + ext, repro, lambda a: a.list_symbols()),
            expected,
        )

    # An exported declaration is listed exactly as its plain form is (const
    # arrow functions, generators, abstract classes, type aliases and enums
    # included).
    for ext, plain in [
        (".js", "function f() {}\n"),
        (".js", "class C {\n  m() {}\n}\n"),
        (".js", "const f = () => 1;\n"),
        (".js", "function* g() {}\n"),
        (".ts", "interface I {\n  x: number;\n}\n"),
        (".ts", "abstract class A {\n  m() {}\n}\n"),
        (".ts", "type T = string;\n"),
        (".ts", "enum E {\n  A,\n}\n"),
    ]:
        label = plain.split("\n")[0]
        _exact(
            f"list_symbols {ext}: 'export {label}' listed like the plain form",
            _read_result("forms" + ext, "export " + plain, lambda a: a.list_symbols()),
            _read_result("forms" + ext, plain, lambda a: a.list_symbols()),
        )

    module = (
        "/** Adds. */\n"
        "export function add(x, y) {\n"
        "  return x + y;\n"
        "}\n"
        "\n"
        "export default class {\n"
        "  run() {\n"
        "    return 1;\n"
        "  }\n"
        "}\n"
        "\n"
        "export class Store {\n"
        "  get(k) {\n"
        "    return k;\n"
        "  }\n"
        "}\n"
    )
    default_end = "    return 1;\n  }\n}\n"
    for ext in (".js", ".ts"):
        name = "exported" + ext

        def edit(action):
            return _edit_result(name, module, action)

        listed = _read_result(name, module, lambda a: a.list_symbols())
        _exact(
            f"{ext} list_symbols: anonymous default export listed as 'default'",
            listed,
            "function add (line 2)\nclass default (line 6)\n  method default.run (line 7)\n"
            "class Store (line 12)\n  method Store.get (line 13)",
        )
        # Every listed name is a valid target.
        for target in [line.split()[1] for line in listed.splitlines()]:
            result = _read_result(name, module, lambda a: a.read_symbol(target))
            check(
                f"{ext} read_symbol('{target}'): listed name resolves",
                "FAIL: " + result if result.startswith("REFUSED") else "PASS",
                "PASS",
            )
        _exact(
            f"{ext} read_symbol: includes `export`",
            _read_result(name, module, lambda a: a.read_symbol("add")),
            "export function add(x, y) {\n  return x + y;\n}",
        )
        _exact(
            f"{ext} read_symbol('default'): the default export",
            _read_result(name, module, lambda a: a.read_symbol("default")),
            "export default class {\n  run() {\n    return 1;\n  }\n}",
        )
        _exact(
            f"{ext} read_symbol depth=signature: the declaration's own signature",
            _read_result(name, module, lambda a: a.read_symbol("add", depth="signature")),
            "function add(x, y)",
        )
        _exact(
            f"{ext} read_symbol depth=interface: header includes `export`",
            _read_result(name, module, lambda a: a.read_symbol("Store", depth="interface")),
            "export class Store {\n  get(k) ...\n}",
        )
        _exact(
            f"{ext} replace_function: round trip keeps `export`",
            edit(lambda a: a.replace_function(
                "add", "export function add(x, y, z) {\n  return x + y + z;\n}"
            )),
            module.replace(
                "export function add(x, y) {\n  return x + y;\n",
                "export function add(x, y, z) {\n  return x + y + z;\n",
            ),
        )
        _exact(
            f"{ext} replace_signature: `export` kept",
            edit(lambda a: a.replace_signature("add", "function add(x, y, z)")),
            module.replace("add(x, y)", "add(x, y, z)"),
        )
        _exact(
            f"{ext} delete_symbol: export statement and its doc comment removed",
            edit(lambda a: a.delete_symbol("Store")),
            module[: module.index("\nexport class Store")],
        )
        result = edit(lambda a: a.delete_symbol("default"))
        check(
            f"{ext} delete_symbol('default'): default export removed",
            "PASS" if "export default" not in result and "export class Store" in result else result,
            "PASS",
        )
        _exact(
            f"{ext} edit_leading_comment replace: above the export",
            edit(lambda a: a.edit_leading_comment("add", "replace", "// Sums.")),
            module.replace("/** Adds. */", "// Sums."),
        )
        _exact(
            f"{ext} edit_leading_comment add: above the export",
            edit(lambda a: a.edit_leading_comment("Store", "add", "/** Store. */")),
            module.replace("\nexport class Store", "\n/** Store. */\nexport class Store"),
        )
        _exact(
            f"{ext} insert_sibling after the default export",
            edit(lambda a: a.insert_sibling("default", "const q = 1;", "after")),
            module.replace(default_end, default_end + "\nconst q = 1;\n"),
        )
        _exact(
            f"{ext} add_method on the default export",
            edit(lambda a: a.add_method("default", "stop() {}")),
            module.replace(default_end, "    return 1;\n  }\n\n  stop() {}\n}\n"),
        )
        _exact(
            f"{ext} replace_function_body on default.run",
            edit(lambda a: a.replace_function_body("default.run", "return 2;")),
            module.replace("    return 1;", "    return 2;"),
        )
        check(
            f"{ext} find_references: exported class found",
            _read_result(name, module, lambda a: a.find_references("Store")),
            "line 12: export class Store {",
        )

    # TS decorators written before `export` belong to the exported class.
    svc = (
        "const x = 1;\n"
        "\n"
        "/** Svc. */\n"
        "@Injectable()\n"
        "export class Svc {\n"
        "  run() {}\n"
        "}\n"
    )
    _exact(
        "ts decorated export: listed at its decorator",
        _read_result("svc.ts", svc, lambda a: a.list_symbols()),
        "constant x (line 1)\nclass Svc (line 4)\n  method Svc.run (line 6)",
    )
    _exact(
        "ts decorated export: read_symbol includes the decorator",
        _read_result("svc.ts", svc, lambda a: a.read_symbol("Svc")),
        "@Injectable()\nexport class Svc {\n  run() {}\n}",
    )
    _exact(
        "ts decorated export: leading comment replaced above the decorator",
        _edit_result("svc.ts", svc, lambda a: a.edit_leading_comment("Svc", "replace", "// Service.")),
        svc.replace("/** Svc. */", "// Service."),
    )
    _exact(
        "ts decorated export: delete_symbol removes decorator and doc comment",
        _edit_result("svc.ts", svc, lambda a: a.delete_symbol("Svc")),
        "const x = 1;\n",
    )
    _exact(
        "ts decorated export: insert_sibling before goes above the decorator",
        _edit_result("svc.ts", svc.replace("/** Svc. */\n", ""),
                     lambda a: a.insert_sibling("Svc", "const y = 2;", "before")),
        svc.replace("/** Svc. */\n", "const y = 2;\n\n"),
    )


def test_class_member_layout():
    print("\n═══ add_method / add_field: indentation and spacing ═══")

    ts4 = "class K {\n    x = 1;\n\n    a() {\n        return 0;\n    }\n}\n"
    ts4_added = (
        "class K {\n    x = 1;\n\n    a() {\n        return 0;\n    }\n\n"
        "    m() {\n        return 1;\n    }\n}\n"
    )
    py_tabs = "class K:\n\t\"\"\"Doc.\"\"\"\n\tdef a(self):\n\t\treturn 1\n"
    rb4 = "class R\n    def a\n    end\nend\n"
    # (label, file name, source, action, expected file text)
    cases = [
        # The reported case: a 4-space TS class used to get a 2-space method
        # and a blank line before its closing brace.
        ("ts: method indented like the class's members", "k.ts", ts4,
         lambda a: a.add_method("K", "m() {\n    return 1;\n}"), ts4_added),
        ("ts: indented snippet re-based, relative indentation kept", "k.ts", ts4,
         lambda a: a.add_method("K", "        m() {\n            return 1;\n        }"), ts4_added),
        ("ts: blank lines around the snippet dropped", "k.ts", ts4,
         lambda a: a.add_method("K", "\n\nm() {\n    return 1;\n}\n\n"), ts4_added),
        ("ts: methods without blank lines between them stay that way", "k.ts",
         "class K {\n  a() {}\n  b() {}\n}\n",
         lambda a: a.add_method("K", "c() {}"),
         "class K {\n  a() {}\n  b() {}\n  c() {}\n}\n"),
        ("ts: empty class gets the file's indent unit", "k.ts",
         "function f() {\n    return 1;\n}\n\nexport class K {}\n",
         lambda a: a.add_method("K", "m() {}"),
         "function f() {\n    return 1;\n}\n\nexport class K {\n    m() {}\n}\n"),
        ("ts: empty class in an unindented file gets the TS default", "k.ts",
         "class K {}\n", lambda a: a.add_method("K", "m() {}"), "class K {\n  m() {}\n}\n"),
        ("ts: a blank line already before } stays", "k.ts",
         "class K {\n    a() {}\n\n}\n", lambda a: a.add_method("K", "m() {}"),
         "class K {\n    a() {}\n\n    m() {}\n\n}\n"),
        ("ts: interface members stay one per line", "i.ts",
         "interface I {\n    a: number;\n}\n", lambda a: a.add_method("I", "m(): void;"),
         "interface I {\n    a: number;\n    m(): void;\n}\n"),
        ("ts add_field: above a decorated first method, blank line between", "k.ts",
         "class K {\n    @dec()\n    a() {}\n}\n", lambda a: a.add_field("K", "x = 1;"),
         "class K {\n    x = 1;\n\n    @dec()\n    a() {}\n}\n"),
        ("ts add_field: among fields, no blank line", "k.ts",
         "class K {\n    a = 1;\n\n    m() {}\n}\n", lambda a: a.add_field("K", "b = 2;"),
         "class K {\n    b = 2;\n    a = 1;\n\n    m() {}\n}\n"),
        ("js: one-line class body opened up", "k.js",
         "class K { a() {} }\n", lambda a: a.add_method("K", "b() {}"),
         "class K {\n  a() {}\n\n  b() {}\n}\n"),
        ("js add_field: empty one-line class", "k.js",
         "class K {}\n", lambda a: a.add_field("K", "x = 1;"), "class K {\n  x = 1;\n}\n"),
        ("java: 2-space class", "J.java",
         "class J {\n  int x;\n\n  void a() {}\n}\n",
         lambda a: a.add_method("J", "void m() {\n  return;\n}"),
         "class J {\n  int x;\n\n  void a() {}\n\n  void m() {\n    return;\n  }\n}\n"),
        ("java add_field: above the first method", "J.java",
         "class J {\n  void a() {}\n}\n", lambda a: a.add_field("J", "private int x;"),
         "class J {\n  private int x;\n\n  void a() {}\n}\n"),
        ("java: empty class in an unindented file gets the Java default", "J.java",
         "class J {}\n", lambda a: a.add_method("J", "void m() {}"), "class J {\n    void m() {}\n}\n"),
        ("cpp: access label does not set the indentation", "c.cpp",
         "class C {\npublic:\n  int x;\n};\n", lambda a: a.add_method("C", "void m() {}"),
         "class C {\npublic:\n  int x;\n\n  void m() {}\n};\n"),
        ("cpp add_field: empty struct", "c.cpp",
         "struct E {};\n", lambda a: a.add_field("E", "int y;"), "struct E {\n  int y;\n};\n"),
        ("py: tab-indented class", "t.py",
         "class K:\n\tdef a(self):\n\t\treturn 1\n",
         lambda a: a.add_method("K", "def m(self):\n\treturn 2"),
         "class K:\n\tdef a(self):\n\t\treturn 1\n\n\tdef m(self):\n\t\treturn 2\n"),
        ("py add_field: tab-indented, after the docstring", "t.py", py_tabs,
         lambda a: a.add_field("K", "x = 1"),
         "class K:\n\t\"\"\"Doc.\"\"\"\n\tx = 1\n\n\tdef a(self):\n\t\treturn 1\n"),
        ("py add_field: after the docstring, existing blank line kept", "t.py",
         "class K:\n    \"\"\"Doc.\"\"\"\n\n    def a(self):\n        return 1\n",
         lambda a: a.add_field("K", "x = 1"),
         "class K:\n    \"\"\"Doc.\"\"\"\n    x = 1\n\n    def a(self):\n        return 1\n"),
        ("py: 2-space class", "t.py", "class K:\n  def a(self):\n    return 1\n",
         lambda a: a.add_method("K", "def m(self):\n  return 2"),
         "class K:\n  def a(self):\n    return 1\n\n  def m(self):\n    return 2\n"),
        ("rb: 4-space class", "r.rb", rb4, lambda a: a.add_method("R", "def m\n  1\nend"),
         "class R\n    def a\n    end\n\n    def m\n      1\n    end\nend\n"),
        ("rb add_field: above the first method", "r.rb", rb4,
         lambda a: a.add_field("R", "attr_reader :x"),
         "class R\n    attr_reader :x\n\n    def a\n    end\nend\n"),
        ("rb: empty class", "r.rb", "class R\nend\n", lambda a: a.add_method("R", "def m\nend"),
         "class R\n  def m\n  end\nend\n"),
        ("go add_field: empty one-line struct", "s.go", "package main\n\ntype T struct{}\n",
         lambda a: a.add_field("T", "A int"), "package main\n\ntype T struct{\n\tA int\n}\n"),
        ("go add_field: indented like the existing fields", "s.go",
         "package main\n\ntype T struct {\n    B int\n}\n", lambda a: a.add_field("T", "A int"),
         "package main\n\ntype T struct {\n    A int\n    B int\n}\n"),
    ]
    cases += [
        ("ts: after a comment on the last member's line", "k.ts",
         "class K {\n  a() {} // note\n}\n", lambda a: a.add_method("K", "b() {}"),
         "class K {\n  a() {} // note\n\n  b() {}\n}\n"),
        ("ts: multi-byte text before the class", "u.ts",
         "// ═══ é ═══\nclass K {}\n", lambda a: a.add_method("K", "m() { return '→'; }"),
         "// ═══ é ═══\nclass K {\n  m() { return '→'; }\n}\n"),
        ("cpp: class nested in a namespace", "n.cpp",
         "namespace n {\n  class C {};\n}\n", lambda a: a.add_method("C", "void m() {}"),
         "namespace n {\n  class C {\n    void m() {}\n  };\n}\n"),
        ("py: nested class", "n.py",
         "class O:\n    class I:\n        def a(self):\n            pass\n",
         lambda a: a.add_method("O.I", "def m(self):\n    pass"),
         "class O:\n    class I:\n        def a(self):\n            pass\n\n"
         "        def m(self):\n            pass\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"member layout {label}", _edit_result(name, source, action), expected)

    # Line endings are kept by both insertion paths.
    _exact("member layout ts: CRLF file stays CRLF",
           _edit_result("k.ts", "class K {\n    a() {}\n}\n",
                        lambda a: a.add_method("K", "m() {}"), "\r\n"),
           "class K {\r\n    a() {}\r\n\r\n    m() {}\r\n}\r\n")
    _exact("member layout py: CRLF file stays CRLF",
           _edit_result("k.py", "class K:\n    def a(self):\n        pass\n",
                        lambda a: a.add_field("K", "x = 1"), "\r\n"),
           "class K:\r\n    x = 1\r\n\r\n    def a(self):\r\n        pass\r\n")

    # A Python or Ruby class body on its header's line has no line to insert
    # on: refused, file untouched (Python's used to land before the class).
    for label, name, source, action in [
        ("py add_method", "t.py", "class K: pass\n", lambda a: a.add_method("K", "def m(self):\n    pass")),
        ("py add_field", "t.py", "class K: pass\n", lambda a: a.add_field("K", "x = 1")),
        ("rb add_method", "r.rb", "class R; end\n", lambda a: a.add_method("R", "def m\nend")),
    ]:
        result = _edit_result(name, source, action)
        check(f"member layout {label} on a one-line class: refused", result,
              "REFUSED: The body of ")
        check(f"member layout {label} on a one-line class: points to replace_function",
              result, "with replace_function")
        check(f"member layout {label} on a one-line class: file untouched",
              "PASS" if "[FILE CHANGED]" not in result else "FAIL", "PASS")
    check("member layout: empty content refused",
          _edit_result("k.ts", ts4, lambda a: a.add_method("K", "\n  \n")),
          "REFUSED: content is empty")


def test_decorator_leading_comments():
    print("\n═══ decorators and leading comments (TS, JS, Python, Java) ═══")

    # Each method has a doc comment above two decorators/annotations. TS puts
    # the decorators beside the method in the class body; JS and Java keep
    # them inside the method node and Python in its decorated_definition, and
    # all four must behave alike.
    # (label, file name, source, target, doc line, new comment line,
    #  replace_function content, its expected source fragment, sibling)
    ts = (
        "class S {\n    x = 1;\n\n    /** Finds. */\n    @Get()\n    @Auth\n"
        "    find() {\n        return 1;\n    }\n}\n"
    )
    langs = [
        ("ts", "s.ts", ts, "S.find", "    /** Finds. */\n", "    // New.\n",
         "@Post()\nfind() {\n    return 2;\n}", "    @Post()\n    find() {\n        return 2;\n    }\n",
         "y = 2;"),
        ("js", "s.js", ts, "S.find", "    /** Finds. */\n", "    // New.\n",
         "@Post()\nfind() {\n    return 2;\n}", "    @Post()\n    find() {\n        return 2;\n    }\n",
         "y = 2;"),
        ("python", "s.py",
         "class S:\n    x = 1\n\n    # Finds.\n    @property\n    @cached\n"
         "    def find(self):\n        return 1\n",
         "S.find", "    # Finds.\n", "    # New.\n",
         "@staticmethod\ndef find():\n    return 2", "    @staticmethod\n    def find():\n        return 2\n",
         "y = 2"),
        ("java", "S.java",
         "class S {\n    int x;\n\n    /** Finds. */\n    @Override\n    @Deprecated\n"
         "    public String find() {\n        return \"\";\n    }\n}\n",
         "S.find", "    /** Finds. */\n", "    // New.\n",
         "@Override\npublic String find() {\n    return \"b\";\n}",
         "    @Override\n    public String find() {\n        return \"b\";\n    }\n",
         "int y;"),
    ]
    for label, name, source, target, doc, new, new_def, new_def_text, sibling in langs:
        decorated = source[source.index(doc) + len(doc):]
        definition_end = decorated.index("\n    }\n") + 7 if "{" in decorated else len(decorated)
        definition = decorated[:definition_end]
        bare = source.replace(doc, "")
        _exact(f"{label} add: comment goes above the first decorator",
               _edit_result(name, bare, lambda a: a.edit_leading_comment(target, "add", new.strip())),
               source.replace(doc, new))
        check(f"{label} add: comment above the decorators is detected",
              _edit_result(name, source, lambda a: a.edit_leading_comment(target, "add", new.strip())),
              f"already has a leading comment (line 4):\n{doc.strip()}")
        _exact(f"{label} replace: comment above the decorators replaced",
               _edit_result(name, source, lambda a: a.edit_leading_comment(target, "replace", new.strip())),
               source.replace(doc, new))
        _exact(f"{label} remove: comment above the decorators removed",
               _edit_result(name, source, lambda a: a.edit_leading_comment(target, "remove")),
               bare)
        head = source[: source.index(doc)].rstrip("\n")
        result = _edit_result(name, source, lambda a: a.delete_symbol(target))
        check(f"{label} delete_symbol: decorators and doc comment go too",
              "PASS" if result.startswith(head) and "@" not in result
              and "find" not in result and doc.strip() not in result else result,
              "PASS")
        result = _edit_result(name, source, lambda a: a.delete_symbol(target, include_leading_comments=False))
        check(f"{label} delete_symbol include_leading_comments=False: doc kept, decorators gone",
              "PASS" if result.startswith(head + "\n\n" + doc) and "@" not in result
              and "find" not in result else result,
              "PASS")
        _exact(f"{label} read_symbol: starts at the first decorator",
               _read_result(name, source, lambda a: a.read_symbol(target)),
               definition.strip())
        check(f"{label} list_symbols: method listed at its first decorator",
              _read_result(name, source, lambda a: a.list_symbols()),
              f"method {target} (line 5)")
        _exact(f"{label} replace_function: decorators replaced with the definition",
               _edit_result(name, source, lambda a: a.replace_function(target, new_def)),
               source.replace(definition, new_def_text))
        _exact(f"{label} insert_sibling before: above the decorators",
               _edit_result(name, bare, lambda a: a.insert_sibling(target, sibling, "before")),
               bare.replace(definition, f"    {sibling}\n\n" + definition))

    # A comment between two TS decorators is part of the decorated member.
    between = "class S {\n    x = 1;\n\n    @A()\n    // why\n    @B()\n    m() {}\n}\n"
    result = _edit_result("b.ts", between, lambda a: a.delete_symbol("S.m"))
    check("ts comment between decorators: delete_symbol removes all of it",
          "PASS" if "@" not in result and "why" not in result and "m()" not in result else result,
          "PASS")
    _exact("ts comment between decorators: add goes above the first decorator",
           _edit_result("b.ts", between, lambda a: a.edit_leading_comment("S.m", "add", "// Doc.")),
           between.replace("    @A()", "    // Doc.\n    @A()"))

    # A decorated Python class is listed as a class, and its decorators go
    # with it (they used to be listed as 'function <anonymous>' and left
    # behind by delete_symbol).
    dc = "x = 1\n\n\n# Data.\n@dataclass\nclass D:\n    a: int = 1\n"
    _exact("py decorated class: listed as a class",
           _read_result("d.py", dc, lambda a: a.list_symbols()), "variable x (line 1)\nclass D (line 5)\n  field D.a (line 7)")
    _exact("py decorated class: read_symbol includes the decorator",
           _read_result("d.py", dc, lambda a: a.read_symbol("D")),
           "@dataclass\nclass D:\n    a: int = 1")
    _exact("py decorated class: delete_symbol removes decorator and comment",
           _edit_result("d.py", dc, lambda a: a.delete_symbol("D")), "x = 1\n")
    _exact("py decorated class: comment replaced above the decorator",
           _edit_result("d.py", dc, lambda a: a.edit_leading_comment("D", "replace", "# Record.")),
           dc.replace("# Data.", "# Record."))
    _exact("py decorated class: replace_function replaces the decorators too",
           _edit_result("d.py", dc, lambda a: a.replace_function(
               "D", "@dataclass(frozen=True)\nclass D:\n    a: int = 2")),
           dc.replace("@dataclass\nclass D:\n    a: int = 1", "@dataclass(frozen=True)\nclass D:\n    a: int = 2"))
    check("py decorated class: interface header includes the decorator",
          _read_result("d.py", dc, lambda a: a.read_symbol("D", depth="interface")),
          "@dataclass\nclass D:")
    _exact("py decorated class: add_method still targets the class",
           _edit_result("d.py", dc, lambda a: a.add_method("D", "def m(self):\n    return 1")),
           dc + "\n    def m(self):\n        return 1\n")

def test_docs_name_real_tools():
    print("\n═══ docs and tool metadata only name tools that exist ═══")

    import asyncio
    import re

    from ast_editor.server import mcp

    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    texts = {"_INSTRUCTIONS": mcp.instructions or ""}
    for t in tools:
        texts[f"{t.name} docstring"] = t.description or ""
        for prop, spec in t.input_schema.get("properties", {}).items():
            texts[f"{t.name}.{prop} description"] = str(spec.get("description", ""))
    root = os.path.join(TESTS_DIR, "..")
    for doc in ("README.md", "AST-EDITOR.md"):
        with open(os.path.join(root, doc), encoding="utf-8") as f:
            texts[doc] = f.read()

    # Tool-shaped words; `delete_group` is named in AST-EDITOR.md only to say
    # it does not exist.
    pattern = re.compile(
        r"\b(?:add|append|delete|edit|find|get|insert|list|prepend|read|remove|replace)_[a-z_]+\b"
    )
    allowed = {"delete_group"}
    unknown = sorted(
        f"{where}: {word}"
        for where, text in texts.items()
        for word in set(pattern.findall(text))
        if word not in names and word not in allowed
    )
    check(
        "docs: every tool-like name is a registered tool",
        "PASS" if not unknown else "FAIL: " + "; ".join(unknown),
        "PASS",
    )

    # Error messages reach the caller too, so they must not name removed
    # tools either: check the text of every ApplierError raised in applier.py.
    import ast as _ast

    with open(os.path.join(root, "ast_editor", "applier.py"), encoding="utf-8") as f:
        tree = _ast.parse(f.read())
    unknown = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call) and getattr(node.func, "id", None) == "ApplierError":
            for part in _ast.walk(node):
                if isinstance(part, _ast.Constant) and isinstance(part.value, str):
                    unknown.update(
                        f"line {node.lineno}: {word}"
                        for word in pattern.findall(part.value)
                        if word not in names and word not in allowed
                    )
    check(
        "error messages: every tool-like name is a registered tool",
        "PASS" if not unknown else "FAIL: " + "; ".join(sorted(unknown)),
        "PASS",
    )
    result = _edit_result("r.json", '{"a": 1}\n', lambda a: a.read_symbol("a", depth="interface"))
    check("read_symbol(depth='interface') on json: names the real tool", result,
          "REFUSED: read_symbol(depth='interface') is not supported for .json")

def test_config_path_lookup():
    print("\n═══ Config files: dotted paths are followed from the root ═══")

    json_deeper = '{"x": {"a": {"b": 1}}}\n'
    json_both = '{"x": {"a": {"b": 1}}, "a": {"b": 3}}\n'
    yaml_deeper = "x:\n  a:\n    b: 1\n"
    yaml_both = "x:\n  a:\n    b: 1\na:\n  b: 3\n"
    # (label, file name, content, edit, expected file, or None if the
    # target must not be found)
    cases = [
        # a.b exists only deeper (x.a.b), or b only below another key.
        ("json a.b only deeper: replace_value", "p.json", json_deeper,
         lambda a: a.replace_value("a.b", "2"), None),
        ("json a.b only deeper: delete_key", "p.json", json_deeper,
         lambda a: a.delete_key("a.b"), None),
        ("json a only deeper: add_key", "p.json", '{"x": {"a": {"m": 0}}}\n',
         lambda a: a.add_key("a", "k", "1"), None),
        ("json a.b only deeper: append_to_array", "p.json", '{"x": {"a": {"b": [1]}}}\n',
         lambda a: a.append_to_array("a.b", "2"), None),
        ("json a.b only deeper: remove_from_array", "p.json", '{"x": {"a": {"b": [1, 2]}}}\n',
         lambda a: a.remove_from_array("a.b", "1"), None),
        ("json b only under a", "p.json", '{"a": {"b": 1}}\n',
         lambda a: a.replace_value("b", "2"), None),
        ("json a.b only under a.x", "p.json", '{"a": {"x": {"b": 1}}}\n',
         lambda a: a.replace_value("a.b", "2"), None),
        ("json a.b missing", "p.json", '{"a": {"c": 1}}\n',
         lambda a: a.replace_value("a.b", "2"), None),
        # a.b both deeper and at the root: the root one is edited.
        ("json a.b deeper and at root: replace_value", "p.json", json_both,
         lambda a: a.replace_value("a.b", "2"), '{"x": {"a": {"b": 1}}, "a": {"b": 2}}\n'),
        ("json a.b deeper and at root: delete_key", "p.json", json_both,
         lambda a: a.delete_key("a.b"), '{"x": {"a": {"b": 1}}, "a": {}}\n'),
        ("json a deeper and at root: add_key", "p.json", '{"x": {"a": {"m": 0}}, "a": {"m": 0}}\n',
         lambda a: a.add_key("a", "k", "1"), '{"x": {"a": {"m": 0}}, "a": {"m": 0, "k": 1}}\n'),
        ("json a.b deeper and at root: remove_from_array", "p.json",
         '{"x": {"a": {"b": [1, 2]}}, "a": {"b": [1, 2]}}\n',
         lambda a: a.remove_from_array("a.b", "1"), '{"x": {"a": {"b": [1, 2]}}, "a": {"b": [2]}}\n'),
        ("yaml a.b only deeper: replace_value", "p.yaml", yaml_deeper,
         lambda a: a.replace_value("a.b", "2"), None),
        ("yaml a.b only deeper: delete_key", "p.yaml", yaml_deeper,
         lambda a: a.delete_key("a.b"), None),
        ("yaml a only deeper: add_key", "p.yaml", "x:\n  a:\n    m: 0\n",
         lambda a: a.add_key("a", "k", "1"), None),
        ("yaml a.b only deeper: append_to_array", "p.yaml", "x:\n  a:\n    b:\n      - 1\n",
         lambda a: a.append_to_array("a.b", "2"), None),
        ("yaml b only under a", "p.yaml", "a:\n  b: 1\n",
         lambda a: a.replace_value("b", "2"), None),
        ("yaml a.b only under a.x", "p.yaml", "a:\n  x:\n    b: 1\n",
         lambda a: a.replace_value("a.b", "2"), None),
        ("yaml a.b missing", "p.yaml", "a:\n  c: 1\n",
         lambda a: a.replace_value("a.b", "2"), None),
        ("yaml a.b deeper and at root: replace_value", "p.yaml", yaml_both,
         lambda a: a.replace_value("a.b", "2"), "x:\n  a:\n    b: 1\na:\n  b: 2\n"),
        ("yaml a.b deeper and at root: delete_key", "p.yaml", "x:\n  a:\n    b: 1\na:\n  b: 3\n  c: 4\n",
         lambda a: a.delete_key("a.b"), "x:\n  a:\n    b: 1\na:\n  c: 4\n"),
        ("yaml a deeper and at root: add_key", "p.yaml", "x:\n  a:\n    m: 0\na:\n  m: 0\n",
         lambda a: a.add_key("a", "k", "1"), "x:\n  a:\n    m: 0\na:\n  m: 0\n  k: 1\n"),
        ("yaml key of a later document", "p.yaml", "a: 1\n---\nb: 2\n",
         lambda a: a.replace_value("b", "3"), "a: 1\n---\nb: 3\n"),
        ("yaml delete_key on a key with no value", "p.yaml", "a:\nb: 1\n",
         lambda a: a.delete_key("a"), "b: 1\n"),
        ("yaml document after a directive", "p.yaml", "%YAML 1.2\n---\na:\n  b: 1\n",
         lambda a: a.replace_value("a.b", "2"), "%YAML 1.2\n---\na:\n  b: 2\n"),
        ("yaml document with a tag", "p.yaml", "--- !!map\na:\n  b: 1\n",
         lambda a: a.replace_value("a.b", "2"), "--- !!map\na:\n  b: 2\n"),
        ("yaml document after comments", "p.yaml", "# c\n---\n# d\na:\n  b: 1\n",
         lambda a: a.replace_value("a.b", "2"), "# c\n---\n# d\na:\n  b: 2\n"),
        ("yaml mapping with an anchor", "p.yaml", "a: &x\n  b: 1\n",
         lambda a: a.replace_value("a.b", "2"), "a: &x\n  b: 2\n"),
        ("yaml add_key at the root after a directive", "p.yaml", "%YAML 1.2\n---\na: 1\n",
         lambda a: a.add_key("", "k", "2"), "%YAML 1.2\n---\na: 1\nk: 2\n"),
        ("toml x only in a [table]: replace_value", "p.toml", "[t]\nx = 1\n",
         lambda a: a.replace_value("x", "2"), None),
        ("toml x only in a [table]: delete_key", "p.toml", "[t]\nx = 1\n",
         lambda a: a.delete_key("x"), None),
        ("toml x missing", "p.toml", "y = 1\n",
         lambda a: a.replace_value("x", "2"), None),
        ("toml x at root and in a [table]", "p.toml", "x = 0\n\n[t]\nx = 1\n",
         lambda a: a.replace_value("x", "2"), "x = 2\n\n[t]\nx = 1\n"),
        ("toml t.x", "p.toml", "x = 0\n\n[t]\nx = 1\n",
         lambda a: a.replace_value("t.x", "2"), "x = 0\n\n[t]\nx = 2\n"),
        # Dotted [a.b] table names stay addressable, and JSON keys compare
        # by their decoded text.
        ("toml key of an [a.b] table", "p.toml", "[a]\nc = 0\n\n[a.b]\nc = 1\n",
         lambda a: a.replace_value("a.b.c", "2"), "[a]\nc = 0\n\n[a.b]\nc = 2\n"),
        ("json key written with an escape", "p.json", '{"caf\\u00e9": {"b": 1}}\n',
         lambda a: a.replace_value("café.b", "2"), '{"caf\\u00e9": {"b": 2}}\n'),
    ]
    for label, name, content, action, expected in cases:
        result = _edit_result(name, content, action)
        if expected is None:
            check(f"{label}: not found", result, "REFUSED: ")
            check(f"{label}: says not found", result, "not found")
            check(f"{label}: file untouched", "PASS" if "[FILE CHANGED]" not in result else "FAIL", "PASS")
        else:
            _exact(label, result, expected)

    for label, name, content, target, expected in [
        ("json a.b deeper and at root", "p.json", json_both, "a.b", "3"),
        ("json a.b only deeper", "p.json", json_deeper, "a.b", "REFUSED: Target 'a.b' not found"),
        ("yaml a.b deeper and at root", "p.yaml", yaml_both, "a.b", "3"),
        ("yaml a.b only deeper", "p.yaml", yaml_deeper, "a.b", "REFUSED: Target 'a.b' not found"),
        ("toml x at root and in a [table]", "p.toml", "x = 0\n\n[t]\nx = 1\n", "x", "0"),
        ("toml x only in a [table]", "p.toml", "[t]\nx = 1\n", "x", "REFUSED: Target 'x' not found"),
    ]:
        result = _read_result(name, content, lambda a: a.read_symbol(target))
        check(f"read_symbol {label}", result, expected)
        if not expected.startswith("REFUSED"):
            _exact(f"read_symbol {label}: just the root value", result, expected)

def test_add_key_config_shapes():
    print("\n═══ add_key: empty, flow and inline YAML/TOML mappings, key quoting ═══")
    import tomllib

    try:
        import yaml  # not a dependency of this server: checked when installed
    except ImportError:
        yaml = None

    def lookup(data, path):
        for part in path:
            data = data[part]
        return data

    # (label, content, parent_target, key, value, expected file, path to
    # the new key in the loaded data)
    yaml_cases = [
        ("empty flow mapping", "a: {}\nb: 1\n", "a", "k", "1", "a: { k: 1 }\nb: 1\n", ("a", "k")),
        ("key with no value", "a:\nb: 1\n", "a", "k", "v", "a:\n  k: v\nb: 1\n", ("a", "k")),
        ("key with no value, 4-space file", "top:\n    a:\n    b: 1\n", "top.a", "k", "1",
         "top:\n    a:\n        k: 1\n    b: 1\n", ("top", "a", "k")),
        ("key with no value but a comment", "a: # later\nb: 1\n", "a", "k", "1",
         "a: # later\n  k: 1\nb: 1\n", ("a", "k")),
        ("last key, with no value", "b: 1\na:\n", "a", "k", "1", "b: 1\na:\n  k: 1\n", ("a", "k")),
        ("flow mapping", "a: {x: 1}\n", "a", "k", "2", "a: {x: 1, k: 2}\n", ("a", "k")),
        ("padded flow mapping", "a: { x: 1, y: 2 }\n", "a", "k", "3",
         "a: { x: 1, y: 2, k: 3 }\n", ("a", "k")),
        ("flow mapping over several lines", "a: {\n  x: 1,\n  y: 2\n}\n", "a", "k", "3",
         "a: {\n  x: 1,\n  y: 2,\n  k: 3\n}\n", ("a", "k")),
        ("flow mapping with an anchor", "a: &base {x: 1}\n", "a", "k", "2",
         "a: &base {x: 1, k: 2}\n", ("a", "k")),
        ("root flow mapping", "{a: 1}\n", "", "k", "2", "{a: 1, k: 2}\n", ("k",)),
        ("root empty flow mapping", "{}\n", "", "k", "1", "{ k: 1 }\n", ("k",)),
        ("empty file", "", "", "k", "1", "k: 1\n", ("k",)),
        ("comments only", "# settings\n", "", "k", "1", "# settings\nk: 1\n", ("k",)),
        ("block mapping", "a:\n  x: 1\n", "a", "k", "2", "a:\n  x: 1\n  k: 2\n", ("a", "k")),
        # Keys stay plain unless they have to be quoted.
        ("plain key with spaces", "a: 1\n", "", "my key", "2", "a: 1\nmy key: 2\n", ("my key",)),
        ("plain key with dots", "a: 1\n", "", "a.b", "2", "a: 1\na.b: 2\n", ("a.b",)),
        ("plain key, non-ASCII", "a: 1\n", "", "café", "2", "a: 1\ncafé: 2\n", ("café",)),
        ("plain key, spaces around", "a: 1\n", "", " k ", "2", "a: 1\nk: 2\n", ("k",)),
        ("key with a colon", "a: 1\n", "", "a:b", "2", 'a: 1\n"a:b": 2\n', ("a:b",)),
        ("key with colon and space", "a: 1\n", "", "a: b", "2", 'a: 1\n"a: b": 2\n', ("a: b",)),
        ("key with ' #'", "a: 1\n", "", "a #b", "2", 'a: 1\n"a #b": 2\n', ("a #b",)),
        ("key starting with a digit", "a: 1\n", "", "123", "2", 'a: 1\n"123": 2\n', ("123",)),
        ("key that reads as a float", "a: 1\n", "", "1.5", "2", 'a: 1\n"1.5": 2\n', ("1.5",)),
        ("key that reads as a boolean", "a: 1\n", "", "yes", "2", 'a: 1\n"yes": 2\n', ("yes",)),
        ("key that reads as null", "a: 1\n", "", "null", "2", 'a: 1\n"null": 2\n', ("null",)),
        ("key with a tab", "a: 1\n", "", "a\tb", "2", 'a: 1\n"a\\tb": 2\n', ("a\tb",)),
        ("key with a double quote", "a: 1\n", "", 'say "hi"', "2",
         'a: 1\n"say \\"hi\\"": 2\n', ('say "hi"',)),
        ("key with a line separator", "a: 1\n", "", "a\N{LINE SEPARATOR}b", "2",
         'a: 1\n"a\\u2028b": 2\n', ("a\N{LINE SEPARATOR}b",)),
        ("key with DEL", "a: 1\n", "", "a\x7fb", "2", 'a: 1\n"a\\u007fb": 2\n', ("a\x7fb",)),
        ("key given quoted", "a: 1\n", "", '"x y"', "2", 'a: 1\n"x y": 2\n', ("x y",)),
        ("comma key into a flow mapping", "m: {x: 1}\n", "m", "a, b", "2",
         'm: {x: 1, "a, b": 2}\n', ("m", "a, b")),
        ("file that single-quotes", "a: 'x'\nb: 'y'\n", "", "#c", "2",
         "a: 'x'\nb: 'y'\n'#c': 2\n", ("#c",)),
        ("file that single-quotes, apostrophe", "a: 'x'\n", "", "it's #1", "2",
         "a: 'x'\n'it''s #1': 2\n", ("it's #1",)),
    ]
    yaml_cases += [
        (f"key starting with {ch}", "a: 1\n", "", ch + "x", "2", f'a: 1\n"{ch}x": 2\n', (ch + "x",))
        for ch in "-?&*!|>%@`[{"
    ]
    for label, content, parent, key, value, expected, path in yaml_cases:
        result = _edit_result("k.yaml", content, lambda a: a.add_key(parent, key, value))
        _exact(f"yaml add_key {label}", result, expected)
        if yaml is not None:
            try:
                loaded = yaml.safe_load(result)
                got = "PASS" if lookup(loaded, path) == yaml.safe_load(value) else f"FAIL: {loaded!r}"
            except Exception as e:
                got = f"FAIL: {type(e).__name__}: {e}"
            check(f"yaml add_key {label}: loads with the new key", got, "PASS")
    if yaml is None:
        print("  [NOTE] PyYAML is not installed here: yaml.safe_load checks skipped")

    toml_cases = [
        ("inline table", "t = { a = 1 }\n", "t", "k", "2", "t = { a = 1, k = 2 }\n", ("t", "k")),
        ("empty inline table", "t = {}\n", "t", "k", "2", "t = { k = 2 }\n", ("t", "k")),
        ("inline table in a [table]", "[s]\nt = { a = 1 }\n", "s.t", "k", "2",
         "[s]\nt = { a = 1, k = 2 }\n", ("s", "t", "k")),
        ("compact inline table", "t = {a=1}\n", "t", "k", "2", "t = {a=1, k = 2}\n", ("t", "k")),
        ("inline table, key quoted", "t = { a = 1 }\n", "t", "x y", "2",
         't = { a = 1, "x y" = 2 }\n', ("t", "x y")),
        ("[table]", "[t]\na = 1\n", "t", "k", "2", "[t]\na = 1\nk = 2\n", ("t", "k")),
        ("[table], key quoted", "[t]\na = 1\n", "t", "x y", "2", '[t]\na = 1\n"x y" = 2\n', ("t", "x y")),
        ("key with a space", "a = 1\n", "", "x y", "2", 'a = 1\n"x y" = 2\n', ("x y",)),
        ("key with a colon", "a = 1\n", "", "x:y", "2", 'a = 1\n"x:y" = 2\n', ("x:y",)),
        ("key starting with #", "a = 1\n", "", "#c", "2", 'a = 1\n"#c" = 2\n', ("#c",)),
        ("non-ASCII key", "a = 1\n", "", "café", "2", 'a = 1\n"café" = 2\n', ("café",)),
        ("bare key with a leading digit", "a = 1\n", "", "1st", "2", "a = 1\n1st = 2\n", ("1st",)),
        ("bare key with - and _", "a = 1\n", "", "my-key_2", "2", "a = 1\nmy-key_2 = 2\n", ("my-key_2",)),
        ("dotted key", "a = 1\n", "", "b.c", "2", "a = 1\nb.c = 2\n", ("b", "c")),
        ("dotted key, one part quoted", "a = 1\n", "", "b.x y", "2", 'a = 1\nb."x y" = 2\n', ("b", "x y")),
        ("key with a dot, given quoted", "a = 1\n", "", '"b.c"', "2", 'a = 1\n"b.c" = 2\n', ("b.c",)),
        ("literal-string key", "a = 1\n", "", "'x y'", "2", "a = 1\n'x y' = 2\n", ("x y",)),
        ("key with a double quote", "a = 1\n", "", 'say "hi"', "2",
         'a = 1\n"say \\"hi\\"" = 2\n', ('say "hi"',)),
        ("empty key", "a = 1\n", "", "", "2", 'a = 1\n"" = 2\n', ("",)),
        ("key with a tab", "a = 1\n", "", "a\tb", "2", 'a = 1\n"a\\tb" = 2\n', ("a\tb",)),
        ("key with DEL", "a = 1\n", "", "a\x7fb", "2", 'a = 1\n"a\\u007fb" = 2\n', ("a\x7fb",)),
    ]
    for label, content, parent, key, value, expected, path in toml_cases:
        result = _edit_result("k.toml", content, lambda a: a.add_key(parent, key, value))
        _exact(f"toml add_key {label}", result, expected)
        try:
            loaded = tomllib.loads(result)
            want = tomllib.loads(f"v = {value}")["v"]
            got = "PASS" if lookup(loaded, path) == want else f"FAIL: {loaded!r}"
        except Exception as e:
            got = f"FAIL: {type(e).__name__}: {e}"
        check(f"toml add_key {label}: loads with the new key", got, "PASS")

    # (label, file name, content, parent_target, key, expected error)
    for label, name, content, parent, key, error in [
        ("yaml key in a flow mapping", "k.yaml", "a: {x: 1}\n", "a", "x",
         "Key 'x' already exists in 'a'; use replace_value with target 'a.x'"),
        ("yaml key quoted in a flow mapping", "k.yaml", 'a: {"x": 1}\n', "a", "x", "already exists"),
        ("yaml key in the root flow mapping", "k.yaml", "{x: 1}\n", "", "x",
         "already exists in the root; use replace_value with target 'x'"),
        ("yaml escaped key", "k.yaml", 'a:\n  "q\\"k": 1\n', "a", 'q"k', "already exists in 'a'"),
        ("yaml single-quoted key", "k.yaml", "a:\n  'it''s': 1\n", "a", "it's", "already exists in 'a'"),
        ("yaml scalar parent", "k.yaml", "a: 1\n", "a", "k", "YAML value at 'a' is not a mapping"),
        ("yaml null parent", "k.yaml", "a: null\n", "a", "k", "YAML value at 'a' is not a mapping"),
        ("yaml sequence root", "k.yaml", "- 1\n", "", "k", "YAML document root is not a mapping"),
        ("yaml missing parent", "k.yaml", "a: 1\n", "b", "k", "YAML key 'b' not found"),
        ("toml key in an inline table", "k.toml", "t = { a = 1 }\n", "t", "a",
         "Key 'a' already exists in 't'; use replace_value with target 't.a' to change its value."),
        ("toml quoted key, given bare", "k.toml", '"x y" = 1\n', "", "x y", "already exists in the root"),
        ("toml bare key, given quoted", "k.toml", "xy = 1\n", "", '"xy"', "already exists in the root"),
        ("toml scalar parent", "k.toml", "t = 1\n", "t", "k", "TOML value at 't' is not a table"),
        ("toml missing parent", "k.toml", "a = 1\n", "t", "k", "TOML table '[t]' not found"),
    ]:
        result = _edit_result(name, content, lambda a: a.add_key(parent, key, "2"))
        check(f"add_key refused ({label})", result, "REFUSED: ")
        check(f"add_key refused ({label}): {error}", result, error)
        check(f"add_key refused ({label}): file untouched", "PASS" if "[FILE CHANGED]" not in result else "FAIL", "PASS")

def test_content_line_breaks():
    print("\n═══ Caller content is split into lines on \\n only ═══")

    # Characters str.splitlines() breaks lines on, besides \n and \r. Inside
    # a string literal (or a comment) they are ordinary characters.
    seps = "\x0b\x0c\x1c\x1d\x1e\x85\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}"
    py = "class K:\n    def f(self):\n        return 1\n\n\ndef g():\n    return 2\n"
    js = "class K {\n  f() {\n    return 1;\n  }\n}\n\nfunction g() {\n  return 2;\n}\n"
    # (file name, content, tool label, edit taking the text to put inside
    # the literal or comment). Every edit must come out exactly as it does
    # with an ordinary character (`~`) in place of the separator.
    edits = [
        ("c.py", py, "insert_in_body top", lambda a, s: a.insert_in_body("g", f'    s = "{s}"\n', at="top")),
        ("c.py", py, "insert_in_body bottom", lambda a, s: a.insert_in_body("g", f'    s = "{s}"\n', at="bottom")),
        ("c.py", py, "replace_function_body", lambda a, s: a.replace_function_body("g", f'    return "{s}"')),
        ("c.py", py, "replace_function", lambda a, s: a.replace_function("g", f'def g():\n    return "{s}"')),
        ("c.py", py, "add_top_level", lambda a, s: a.add_top_level(f'S = "{s}"')),
        ("c.py", py, "add_top_level top", lambda a, s: a.add_top_level(f'S = "{s}"', position="top")),
        ("c.py", py, "insert_sibling before", lambda a, s: a.insert_sibling("g", f'S = "{s}"', "before")),
        ("c.py", py, "insert_sibling after", lambda a, s: a.insert_sibling("g", f'S = "{s}"', "after")),
        ("c.py", py, "add_method", lambda a, s: a.add_method("K", f'    def h(self):\n        return "{s}"')),
        ("c.py", py, "add_field", lambda a, s: a.add_field("K", f'    s = "{s}"')),
        ("c.py", py, "edit_leading_comment add", lambda a, s: a.edit_leading_comment("g", "add", f"# {s}")),
        ("c.py", py, "edit_leading_comment replace", lambda a, s: a.edit_leading_comment("g", "replace", f"# {s}")),
        ("c.js", js, "insert_in_body top", lambda a, s: a.insert_in_body("g", f'  const s = "{s}";\n', at="top")),
        ("c.js", js, "insert_in_body bottom", lambda a, s: a.insert_in_body("g", f'  const s = "{s}";\n', at="bottom")),
        ("c.js", js, "replace_function_body", lambda a, s: a.replace_function_body("g", f'  return "{s}";')),
        ("c.js", js, "replace_function", lambda a, s: a.replace_function("g", f'function g() {{\n  return "{s}";\n}}')),
        ("c.js", js, "add_top_level", lambda a, s: a.add_top_level(f'const S = "{s}";')),
        ("c.js", js, "insert_sibling before", lambda a, s: a.insert_sibling("g", f'const S = "{s}";', "before")),
        ("c.js", js, "insert_sibling after", lambda a, s: a.insert_sibling("g", f'const S = "{s}";', "after")),
        ("c.js", js, "add_method", lambda a, s: a.add_method("K", f'  h() {{\n    return "{s}";\n  }}')),
        ("c.js", js, "add_field", lambda a, s: a.add_field("K", f'  s = "{s}";')),
        ("c.js", js, "edit_leading_comment add", lambda a, s: a.edit_leading_comment("g", "add", f"// {s}")),
    ]
    for name, content, tool, edit in edits:
        lang = name.rsplit(".", 1)[1]
        plain = _edit_result(name, content, lambda a: edit(a, "a~b"))
        check(f"{lang} {tool}: edit with `~` written", "PASS" if not plain.startswith("REFUSED") else plain, "PASS")
        chars = seps
        if lang == "js" and tool.startswith("edit_leading_comment"):
            # U+2028 and U+2029 end a JS line comment.
            chars = seps.replace("\N{LINE SEPARATOR}", "").replace("\N{PARAGRAPH SEPARATOR}", "")
        # All of them together for every tool, and one at a time for the
        # most common ones.
        groups = [chars] + (list(chars) if tool in ("insert_in_body top", "add_top_level") else [])
        for sep in groups:
            what = "all separators" if len(sep) > 1 else f"U+{ord(sep):04X}"
            result = _edit_result(name, content, lambda a: edit(a, f"a{sep}b"))
            _exact(f"{lang} {tool}, {what}: kept inside its line", result, plain.replace("~", sep))

    # The same in a CRLF file, with CRLF content.
    result = _edit_result(
        "c.py",
        "def g():\n    return 2\n",
        lambda a: a.insert_in_body("g", f'    s = "a{seps}b"\r\n    t = 1\r\n', at="top"),
        "\r\n",
    )
    _exact("py CRLF insert_in_body, all separators", result,
           f'def g():\r\n    s = "a{seps}b"\r\n    t = 1\r\n    return 2\r\n')

    # So do append_to_array and replace_value on a YAML block sequence. (YAML
    # forbids most of the separators; U+0085 is an ordinary character in
    # YAML 1.2, which tree-sitter-yaml follows.)
    result = _edit_result("c.yaml", "l:\n  - a\n", lambda a: a.append_to_array("l", '"x\x85y"'))
    _exact("yaml append_to_array, U+0085", result, 'l:\n  - a\n  - "x\x85y"\n')
    result = _edit_result("c.yaml", "l:\n  - a\n", lambda a: a.replace_value("l", '- "x\x85y"\n- b'))
    _exact("yaml replace_value sequence, U+0085", result, 'l:\n  - "x\x85y"\n  - b\n')


def test_json_plus_exponents():
    print("\n═══ JSON numbers with a + exponent (6.02E+23) ═══")

    # tree-sitter-json cannot parse an exponent written with `+`; the parser
    # masks the sign, so the number node covers the whole token.
    from ast_editor.parser import TreeSitterParser

    path = _write_temp("e.json", '{"a": 6.02E+23, "s": "1e+5", "t": [1e+5, -2E+0]}\n')
    parser = TreeSitterParser(path)
    check("parser: file with + exponents parses cleanly",
          "PASS" if not parser.tree.root_node.has_error else "FAIL", "PASS")
    numbers = []
    stack = [parser.tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "number":
            numbers.append(parser.node_text(node))
        stack.extend(node.children)
    _exact("parser: number nodes are whole tokens", sorted(numbers), sorted(["6.02E+23", "1e+5", "-2E+0"]))
    os.remove(path)

    one_line = '{"a": 1, "b": 6.02E+23}\n'
    multi = '{\n  "a": 1,\n  "b": 6.02E+23\n}\n'
    # (label, content, edit, expected file)
    cases = [
        ("replace_value", one_line, lambda a: a.replace_value("b", "1"), '{"a": 1, "b": 1}\n'),
        ("replace_value, lowercase e, nested", '{"x": {"b": 1e+5}}\n',
         lambda a: a.replace_value("x.b", "2"), '{"x": {"b": 2}}\n'),
        ("replace_value with a + exponent", one_line,
         lambda a: a.replace_value("b", "1.5E+3"), '{"a": 1, "b": 1.5E+3}\n'),
        ("replace_value beside one", '{"b": 6.02E+23, "a": 1}\n',
         lambda a: a.replace_value("a", "2"), '{"b": 6.02E+23, "a": 2}\n'),
        ("delete_key, last entry", multi, lambda a: a.delete_key("b"), '{\n  "a": 1\n}\n'),
        ("delete_key, last entry inline", one_line, lambda a: a.delete_key("b"), '{"a": 1}\n'),
        ("delete_key, first entry", '{"b": 6.02E+23, "a": 1}\n', lambda a: a.delete_key("b"), '{"a": 1}\n'),
        ("delete_key after one", '{"b": 6.02E+23, "a": 1}\n', lambda a: a.delete_key("a"), '{"b": 6.02E+23}\n'),
        ("add_key after one", multi, lambda a: a.add_key("", "c", "2"),
         '{\n  "a": 1,\n  "b": 6.02E+23,\n  "c": 2\n}\n'),
        ("add_key after one, inline", '{"b": -1.5e+10}\n', lambda a: a.add_key("", "c", "2"),
         '{"b": -1.5e+10, "c": 2}\n'),
        ("append_to_array after one", '{\n  "v": [\n    1e+5\n  ]\n}\n',
         lambda a: a.append_to_array("v", "2"), '{\n  "v": [\n    1e+5,\n    2\n  ]\n}\n'),
        ("remove_from_array", '{"v": [1e+5, 2]}\n', lambda a: a.remove_from_array("v", "1e+5"), '{"v": [2]}\n'),
        ("strings are not numbers", '{"s": "1e+5", "q": "say \\"2E+3\\"", "n": 2E+3}\n',
         lambda a: a.replace_value("n", "3"), '{"s": "1e+5", "q": "say \\"2E+3\\"", "n": 3}\n'),
    ]
    for label, content, action, expected in cases:
        _exact(f"json + exponent: {label}", _edit_result("e.json", content, action), expected)

    for label, content, target, expected in [
        ("number", one_line, "b", "6.02E+23"),
        ("string", '{"s": "1e+5"}\n', "s", '"1e+5"'),
        ("key that looks like one", '{"1e+5": 7}\n', "1e+5", "7"),
    ]:
        result = _read_result("e.json", content, lambda a: a.read_symbol(target))
        _exact(f"json + exponent: read_symbol {label}", result, expected)


def test_member_layout_followups():
    print("\n═══ add_method / add_field: brace-line comments, tabs, one-line bodies, enums ═══")

    def field_then_comment(a):
        a.add_field("K", "x = 1;")
        a.edit_leading_comment("K.a", "add", "// doc")

    # (label, file name, source, action, expected file text)
    cases = [
        # A comment after the `{` on its line stays there: line-scoped
        # directives (NOSONAR, NOLINT) keep applying to the class line, and
        # the comment does not become the first member's leading comment.
        ("ts add_field: comment on the brace line stays", "k.ts",
         "class K { // note\n  a() {}\n}\n", lambda a: a.add_field("K", "x = 1;"),
         "class K { // note\n  x = 1;\n\n  a() {}\n}\n"),
        ("java add_field: NOSONAR on the brace line stays", "K.java",
         "class K { // NOSONAR\n    void a() {}\n}\n", lambda a: a.add_field("K", "int x;"),
         "class K { // NOSONAR\n    int x;\n\n    void a() {}\n}\n"),
        ("cpp add_field: NOLINT on the brace line stays", "k.cpp",
         "class K { // NOLINT\n    void a() {}\n};\n", lambda a: a.add_field("K", "int x;"),
         "class K { // NOLINT\n    int x;\n\n    void a() {}\n};\n"),
        ("ts: the method's leading comment can still be added", "k.ts",
         "class K { // note\n  a() {}\n}\n", field_then_comment,
         "class K { // note\n  x = 1;\n\n  // doc\n  a() {}\n}\n"),
        ("java add_field: block comment on the brace line, blank line kept", "K.java",
         "class K { /* c */\n\n    void a() {}\n}\n", lambda a: a.add_field("K", "int x;"),
         "class K { /* c */\n    int x;\n\n    void a() {}\n}\n"),
        ("java add_field: brace-line comment and no member", "K.java",
         "class K { // c\n}\n", lambda a: a.add_field("K", "int x;"),
         "class K { // c\n    int x;\n}\n"),
        ("java add_field: code after the brace still moves down", "K.java",
         "class K { int y; // c\n    void a() {}\n}\n", lambda a: a.add_field("K", "int x;"),
         "class K {\n    int x;\n    int y; // c\n    void a() {}\n}\n"),
        # Content indented with spaces gets tabs in a tab-indented class.
        ("py add_method: 4-space snippet in a tab-indented class", "t.py",
         "class K:\n\tdef a(self):\n\t\treturn 1\n",
         lambda a: a.add_method("K", "def b(self):\n    if self:\n        return 2"),
         "class K:\n\tdef a(self):\n\t\treturn 1\n\n\tdef b(self):\n\t\tif self:\n\t\t\treturn 2\n"),
        ("py add_field: 4-space snippet in a tab-indented class", "t.py",
         "class K:\n\tdef a(self):\n\t\treturn 1\n",
         lambda a: a.add_field("K", "x = (\n    1\n)"),
         "class K:\n\tx = (\n\t\t1\n\t)\n\n\tdef a(self):\n\t\treturn 1\n"),
        ("js add_method: 2-space snippet in a tab-indented class", "k.js",
         "class K {\n\ta() {}\n}\n", lambda a: a.add_method("K", "m() {\n  return 1;\n}"),
         "class K {\n\ta() {}\n\n\tm() {\n\t\treturn 1;\n\t}\n}\n"),
        ("java add_method: indented snippet in a tab-indented class", "K.java",
         "class K {\n\tvoid a() {}\n}\n",
         lambda a: a.add_method("K", "    void b() {\n        int x;\n    }"),
         "class K {\n\tvoid a() {}\n\n\tvoid b() {\n\t\tint x;\n\t}\n}\n"),
        ("rb add_method: 2-space snippet in a tab-indented class", "r.rb",
         "class R\n\tdef a\n\tend\nend\n", lambda a: a.add_method("R", "def m\n  1\nend"),
         "class R\n\tdef a\n\tend\n\n\tdef m\n\t\t1\n\tend\nend\n"),
        # A non-empty body on one line is opened up completely.
        ("js add_field: one-line class body", "k.js",
         "class K { a() {} }\n", lambda a: a.add_field("K", "x = 1;"),
         "class K {\n  x = 1;\n\n  a() {}\n}\n"),
        ("ts add_method: one-line exported class", "k.ts",
         "export class K { a() {} }\n", lambda a: a.add_method("K", "b() {}"),
         "export class K {\n  a() {}\n\n  b() {}\n}\n"),
        ("go add_field: one-line struct", "s.go",
         "package main\n\ntype S struct{ A int }\n", lambda a: a.add_field("S", "B string"),
         "package main\n\ntype S struct{\n\tB string\n\tA int\n}\n"),
        ("cpp add_method: one-line struct", "c.cpp",
         "struct E { int a; };\n", lambda a: a.add_method("E", "void m() {}"),
         "struct E {\n  int a;\n\n  void m() {}\n};\n"),
        ("cpp add_method: one-line class in a namespace", "n.cpp",
         "namespace n {\n  class C { int a; };\n}\n", lambda a: a.add_method("C", "void m() {}"),
         "namespace n {\n  class C {\n    int a;\n\n    void m() {}\n  };\n}\n"),
        # A method added after a C++ access label goes right under it.
        ("cpp add_method: class with only an access label", "c.cpp",
         "class K {\npublic:\n};\n", lambda a: a.add_method("K", "void b() {}"),
         "class K {\npublic:\n  void b() {}\n};\n"),
        # One after a method that a label follows goes after that method, in
        # its section.
        ("cpp add_method: after a trailing access label", "c.cpp",
         "class K {\n  void a() {}\npublic:\n};\n", lambda a: a.add_method("K", "void b() {}"),
         "class K {\n  void a() {}\n\n  void b() {}\npublic:\n};\n"),
        # Java enums: new members go after the constants, which get the `;`
        # Java needs before other members when they have none.
        ("java add_field: enum with methods", "E.java",
         "enum E {\n    A, B;\n\n    void m() {}\n}\n", lambda a: a.add_field("E", "int x;"),
         "enum E {\n    A, B;\n\n    int x;\n\n    void m() {}\n}\n"),
        ("java add_method: enum with methods", "E.java",
         "enum E {\n    A, B;\n\n    void m() {}\n}\n", lambda a: a.add_method("E", "void n() {}"),
         "enum E {\n    A, B;\n\n    void m() {}\n\n    void n() {}\n}\n"),
        ("java add_method: enum with no ;", "E.java",
         "enum E {\n    A, B\n}\n", lambda a: a.add_method("E", "void n() {}"),
         "enum E {\n    A, B;\n\n    void n() {}\n}\n"),
        ("java add_field: enum with only constants and a ;", "E.java",
         "enum E {\n    A, B;\n}\n", lambda a: a.add_field("E", "int x;"),
         "enum E {\n    A, B;\n\n    int x;\n}\n"),
        ("java add_method: enum constants with a comment", "E.java",
         "enum E {\n    A, B // last\n}\n", lambda a: a.add_method("E", "void n() {}"),
         "enum E {\n    A, B; // last\n\n    void n() {}\n}\n"),
        ("java add_method: enum constant with a body", "E.java",
         "enum E {\n    A {\n        void f() {}\n    },\n    B\n}\n",
         lambda a: a.add_method("E", "void n() {}"),
         "enum E {\n    A {\n        void f() {}\n    },\n    B;\n\n    void n() {}\n}\n"),
        ("java add_field: enum with a constructor", "E.java",
         "enum E {\n    A(1), B(2);\n\n    private final int v;\n\n    E(int v) { this.v = v; }\n}\n",
         lambda a: a.add_field("E", "int x;"),
         "enum E {\n    A(1), B(2);\n\n    int x;\n    private final int v;\n\n"
         "    E(int v) { this.v = v; }\n}\n"),
        ("java add_field: one-line enum", "E.java",
         "enum E { A, B }\n", lambda a: a.add_field("E", "int x;"),
         "enum E {\n    A, B;\n\n    int x;\n}\n"),
        ("java add_field: one-line enum with a method", "E.java",
         "enum E { A; void m() {} }\n", lambda a: a.add_field("E", "int x;"),
         "enum E {\n    A;\n\n    int x;\n\n    void m() {}\n}\n"),
        ("java add_method: empty enum", "E.java",
         "enum E {}\n", lambda a: a.add_method("E", "void n() {}"),
         "enum E {\n    ;\n\n    void n() {}\n}\n"),
        ("java add_method: enum nested in a class", "E.java",
         "class O {\n    enum E {\n        A, B\n    }\n}\n", lambda a: a.add_method("O.E", "void n() {}"),
         "class O {\n    enum E {\n        A, B;\n\n        void n() {}\n    }\n}\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"member layout {label}", _edit_result(name, source, action), expected)

    # A decorated class nested in a class is listed as a class, at its
    # decorator, as an undecorated one is; it used to show up as 'method
    # O.<anonymous>'.
    outline = _read_result(
        "n.py",
        "class O:\n    @dataclass\n    class I:\n        x: int\n\n    def m(self):\n        pass\n",
        lambda a: a.list_symbols(),
    )
    _exact("list_symbols: decorated nested Python class listed as a class", outline,
           "class O (line 1)\n  class O.I (line 2)\n    field O.I.x (line 4)\n  method O.m (line 6)")


def test_config_key_followups():
    print("\n═══ YAML/TOML keys: first document with content, quoted names, inline tables ═══")

    # (label, file name, content, edit, expected file text)
    cases = [
        # add_key at the root goes to the first document that has content.
        ("yaml add_key at the root after an empty document", "k.yaml",
         "---\n---\nb: 2\n", lambda a: a.add_key("", "k", "1"), "---\n---\nb: 2\nk: 1\n"),
        ("yaml add_key at the root after a document with only a comment", "k.yaml",
         "---\n# c\n---\nb: 2\n", lambda a: a.add_key("", "k", "1"), "---\n# c\n---\nb: 2\nk: 1\n"),
        # YAML keys are matched by the name they spell, as add_key does.
        ("yaml replace_value on a single-quoted key with ''", "k.yaml",
         "a:\n  'it''s': 1\n", lambda a: a.replace_value("a.it's", "2"), "a:\n  'it''s': 2\n"),
        ("yaml replace_value on a key with an escape", "k.yaml",
         'a:\n  "caf\\u00e9": 1\n', lambda a: a.replace_value("a.café", "2"), 'a:\n  "caf\\u00e9": 2\n'),
        ("yaml delete_key on a key with an escape", "k.yaml",
         'a:\n  "caf\\u00e9": 1\n  b: 2\n', lambda a: a.delete_key("a.café"), "a:\n  b: 2\n"),
        ("yaml add_key under a parent with an escape", "k.yaml",
         '"caf\\u00e9":\n  b: 1\n', lambda a: a.add_key("café", "k", "2"), '"caf\\u00e9":\n  b: 1\n  k: 2\n'),
        ("yaml quoted key, bare name", "k.yaml",
         'a:\n  "x y": 1\n', lambda a: a.replace_value("a.x y", "2"), 'a:\n  "x y": 2\n'),
        ("yaml quoted key, name written with its quotes", "k.yaml",
         'a:\n  "x y": 1\n', lambda a: a.replace_value('a."x y"', "2"), 'a:\n  "x y": 2\n'),
    ]
    for label, name, content, action, expected in cases:
        _exact(label, _edit_result(name, content, action), expected)

    for label, content, target in [
        ("single-quoted key with ''", "a:\n  'it''s': 1\n", "a.it's"),
        ("key with an escape", 'a:\n  "caf\\u00e9": 1\n', "a.café"),
    ]:
        _exact(f"yaml read_symbol {label}",
               _read_result("k.yaml", content, lambda a: a.read_symbol(target)), "1")

    # The duplicate check runs on the document add_key would write to.
    result = _edit_result("k.yaml", "---\n---\nk: 2\n", lambda a: a.add_key("", "k", "1"))
    check("yaml add_key after an empty document: duplicate refused", result,
          "REFUSED: Key 'k' already exists in the root")
    check("yaml add_key after an empty document: file untouched",
          "PASS" if "[FILE CHANGED]" not in result else "FAIL", "PASS")

    # The target a YAML duplicate refusal points to can be used.
    path = _write_temp("k.yaml", "a:\n  'it''s': 1\n")
    message = _refusal(lambda: Applier(path).add_key("a", "it's", "2"))
    check("yaml duplicate refusal names the target", message, "target \"a.it's\"")
    try:
        Applier(path).replace_value("a.it's", "3")
        result = read_file(path)
    except ApplierError as e:
        result = f"REFUSED: {e}"
    _exact("yaml duplicate refusal: its target works with replace_value", result, "a:\n  'it''s': 3\n")
    os.remove(path)

    # Keys inside TOML inline tables and YAML flow mappings are addressable,
    # so the refusal names the key's own target, and that target works.
    for label, name, content, parent, key, target, expected in [
        ("toml inline table", "k.toml", "t = { a = 1 }\n", "t", "a", "t.a", "t = { a = 3 }\n"),
        ("yaml flow mapping", "k.yaml", "a: {x: 1}\n", "a", "x", "a.x", "a: {x: 3}\n"),
    ]:
        path = _write_temp(name, content)
        message = _refusal(lambda: Applier(path).add_key(parent, key, "2"))
        check(f"{label} duplicate: names the key's target", message, f"target '{target}'")
        try:
            Applier(path).replace_value(target, "3")
            result = read_file(path)
        except ApplierError as e:
            result = f"REFUSED: {e}"
        _exact(f"{label} duplicate: its target works with replace_value", result, expected)
        os.remove(path)


def test_insert_before_leading_comments():
    print("\n═══ insert_sibling before: above the target's leading comment ═══")

    # (label, file name, source, target, content, expected file text). The
    # comment documents the target, so new code goes above it, and above
    # the decorators, annotations and `export` below it.
    cases = [
        ("py function (reported)", "s.py",
         "x = 1\n\n# Doc for f\ndef f():\n    pass\n", "f", "def g():\n    pass",
         "x = 1\n\n\ndef g():\n    pass\n\n\n# Doc for f\ndef f():\n    pass\n"),
        ("py decorated function", "s.py",
         "x = 1\n\n\n# Doc\n@dec\ndef f():\n    pass\n", "f", "def g():\n    pass",
         "x = 1\n\n\ndef g():\n    pass\n\n\n# Doc\n@dec\ndef f():\n    pass\n"),
        ("py method", "s.py",
         "class A:\n    x = 1\n\n    # Doc\n    def f(self):\n        pass\n", "A.f",
         "def g(self):\n    pass",
         "class A:\n    x = 1\n\n    def g(self):\n        pass\n\n    # Doc\n    def f(self):\n        pass\n"),
        ("js multi-line JSDoc", "s.js",
         "const x = 1;\n\n/**\n * Doc.\n */\nfunction f() {}\n", "f", "function g() {}",
         "const x = 1;\n\nfunction g() {}\n\n/**\n * Doc.\n */\nfunction f() {}\n"),
        ("ts decorated export", "s.ts",
         "const x = 1;\n\n// Doc\n@Dec()\nexport class K {}\n", "K", "const y = 2;",
         "const x = 1;\n\nconst y = 2;\n\n// Doc\n@Dec()\nexport class K {}\n"),
        ("ts decorated method", "s.ts",
         "class S {\n  x = 1;\n\n  /** Finds. */\n  @Get()\n  find() {}\n}\n", "S.find", "y = 2;",
         "class S {\n  x = 1;\n\n  y = 2;\n\n  /** Finds. */\n  @Get()\n  find() {}\n}\n"),
        ("go Godoc", "s.go",
         "package main\n\n// F does.\nfunc F() {}\n", "F", "func G() {}",
         "package main\n\nfunc G() {}\n\n// F does.\nfunc F() {}\n"),
        ("java Javadoc and annotation", "S.java",
         "class A {\n    int x;\n\n    /** Doc. */\n    @Override\n    public String toString() { return \"\"; }\n}\n",
         "A.toString", "int y;",
         "class A {\n    int x;\n\n    int y;\n\n    /** Doc. */\n    @Override\n"
         "    public String toString() { return \"\"; }\n}\n"),
        ("ruby comment", "s.rb",
         "class A\n  # Doc\n  def m\n  end\nend\n", "A.m", "def n\nend",
         "class A\n  def n\n  end\n\n  # Doc\n  def m\n  end\nend\n"),
        ("c block comment", "s.c",
         "int x;\n\n/* Doc */\nint f(void) { return 0; }\n", "f", "int g(void) { return 1; }",
         "int x;\n\nint g(void) { return 1; }\n\n/* Doc */\nint f(void) { return 0; }\n"),
        ("cpp line comment", "s.cpp",
         "int x;\n\n// Doc\nclass A {};\n", "A", "class B {};",
         "int x;\n\nclass B {};\n\n// Doc\nclass A {};\n"),
        # A comment separated from the target by a blank line is not its
        # leading comment and stays above the new code.
        ("py detached comment stays above", "s.py",
         "# Section\n\ndef f():\n    pass\n", "f", "X = 1",
         "# Section\n\nX = 1\n\n\ndef f():\n    pass\n"),
        # A `#!` line and encoding or magic comments only work at the top of
        # the file, so they are never taken for the target's comment.
        ("py shebang and coding line stay first", "s.py",
         "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\ndef main():\n    pass\n", "main", "X = 1",
         "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\nX = 1\n\n\ndef main():\n    pass\n"),
        ("ruby magic comment stays first", "s.rb",
         "# frozen_string_literal: true\n# Doc\nclass A\nend\n", "A", "X = 1",
         "# frozen_string_literal: true\nX = 1\n\n# Doc\nclass A\nend\n"),
        # Further down, a comment that mentions a coding is just a comment.
        ("py comment naming a coding below the top lines", "s.py",
         "x = 1\n\n# Decoding: from bytes\ndef f():\n    pass\n", "f", "Y = 2",
         "x = 1\n\nY = 2\n\n\n# Decoding: from bytes\ndef f():\n    pass\n"),
    ]
    for label, name, source, target, content, expected in cases:
        _exact(f"insert_sibling before ({label})",
               _edit_result(name, source, lambda a: a.insert_sibling(target, content, "before")),
               expected)

    # The other comment tools leave the file's directives alone too.
    _exact("delete_symbol keeps the #! line",
           _edit_result("s.py", "#!/usr/bin/env python\n# Doc\ndef main():\n    pass\n",
                        lambda a: a.delete_symbol("main")),
           "#!/usr/bin/env python\n")
    _exact("delete_symbol keeps the #! and coding lines, not the comment below them",
           _edit_result("s.py", "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n# Main.\ndef main():\n    pass\n",
                        lambda a: a.delete_symbol("main")),
           "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n")
    _exact("edit_leading_comment add goes below the #! line",
           _edit_result("s.py", "#!/usr/bin/env python\ndef main():\n    pass\n",
                        lambda a: a.edit_leading_comment("main", "add", "# Main.")),
           "#!/usr/bin/env python\n# Main.\ndef main():\n    pass\n")
    check("edit_leading_comment remove: a #! line is no leading comment",
          _edit_result("s.py", "#!/usr/bin/env python\ndef main():\n    pass\n",
                       lambda a: a.edit_leading_comment("main", "remove")),
          "REFUSED: No leading comment found above 'main'")


def test_ts_abstract_classes():
    print("\n═══ TS abstract classes and abstract methods ═══")

    # The reported case: listed, and a valid add_method target.
    repro = "export abstract class A {\n  m(): void {}\n}\n"
    for ext in (".ts", ".tsx"):
        _exact(f"{ext} list_symbols: exported abstract class listed",
               _read_result("abs" + ext, repro, lambda a: a.list_symbols()),
               "class A (line 1)\n  method A.m (line 2)")
        _exact(f"{ext} add_method on an exported abstract class",
               _edit_result("abs" + ext, repro, lambda a: a.add_method("A", "n(): void {}")),
               "export abstract class A {\n  m(): void {}\n\n  n(): void {}\n}\n")

    ts = (
        "export abstract class A {\n"
        "  x = 1;\n"
        "\n"
        "  /** M. */\n"
        "  abstract m(): void;\n"
        "\n"
        "  n(): void {\n"
        "    return;\n"
        "  }\n"
        "}\n"
        "\n"
        "abstract class B {\n"
        "  f() {}\n"
        "}\n"
    )

    def edit(action):
        return _edit_result("abs.ts", ts, action)

    def read(action):
        return _read_result("abs.ts", ts, action)

    _exact("list_symbols: abstract classes with their abstract and regular methods",
           read(lambda a: a.list_symbols()),
           "class A (line 1)\n  field A.x (line 2)\n  method A.m (line 5)\n  method A.n (line 7)\n"
           "class B (line 12)\n  method B.f (line 13)")
    _exact("read_symbol: exported abstract class includes `export`",
           read(lambda a: a.read_symbol("A")), ts[: ts.index("\n\nabstract class B")])
    _exact("read_symbol: abstract method, with its `;`", read(lambda a: a.read_symbol("A.m")), "abstract m(): void;")
    _exact("read_symbol depth=signature: abstract method",
           read(lambda a: a.read_symbol("A.m", depth="signature")), "abstract m(): void")
    _exact("read_symbol depth=signature: abstract class header",
           read(lambda a: a.read_symbol("A", depth="signature")), "abstract class A")
    _exact("read_symbol depth=interface: abstract class",
           read(lambda a: a.read_symbol("A", depth="interface")),
           "export abstract class A {\n  x = 1;\n  /** M. */\n  abstract m(): void;\n  n(): void ...\n}")
    _exact("add_method on an abstract class",
           edit(lambda a: a.add_method("B", "g() {}")),
           ts.replace("  f() {}\n}", "  f() {}\n\n  g() {}\n}"))
    _exact("add_field on an exported abstract class",
           edit(lambda a: a.add_field("A", "y = 2;")),
           ts.replace("  x = 1;\n", "  y = 2;\n  x = 1;\n"))
    _exact("replace_function_body on an abstract class's method",
           edit(lambda a: a.replace_function_body("A.n", "console.log(1);")),
           ts.replace("    return;", "    console.log(1);"))
    _exact("replace_function on an abstract method",
           edit(lambda a: a.replace_function("A.m", "abstract m(x: number): void;")),
           ts.replace("abstract m(): void;", "abstract m(x: number): void;"))
    _exact("edit_leading_comment replace on an abstract method",
           edit(lambda a: a.edit_leading_comment("A.m", "replace", "// New.")),
           ts.replace("/** M. */", "// New."))
    _exact("edit_leading_comment add on an abstract class",
           edit(lambda a: a.edit_leading_comment("B", "add", "// B.")),
           ts.replace("\nabstract class B", "\n// B.\nabstract class B"))
    _exact("delete_symbol: abstract method with its doc comment",
           edit(lambda a: a.delete_symbol("A.m")),
           ts.replace("  /** M. */\n  abstract m(): void;\n\n", ""))
    _exact("delete_symbol: exported abstract class",
           edit(lambda a: a.delete_symbol("A")), "abstract class B {\n  f() {}\n}\n")
    _exact("delete_symbol: abstract class",
           edit(lambda a: a.delete_symbol("B")), ts[: ts.index("\nabstract class B")])
    _exact("insert_sibling before an abstract class",
           edit(lambda a: a.insert_sibling("B", "const q = 1;", "before")),
           ts.replace("\nabstract class B", "\nconst q = 1;\n\nabstract class B"))
    _exact("insert_sibling after an exported abstract class",
           edit(lambda a: a.insert_sibling("A", "const q = 1;", "after")),
           ts.replace("}\n\nabstract class B", "}\n\nconst q = 1;\n\nabstract class B"))

    # A Java interface method has no body either: its signature is its text.
    _exact("java read_symbol depth=signature: interface method",
           _read_result("S.java", "interface S {\n    String get(String k);\n}\n",
                        lambda a: a.read_symbol("S.get", depth="signature")),
           "String get(String k)")


def test_delete_symbol_separators():
    print("\n═══ delete_symbol: the blank lines that separated the symbol go too ═══")

    # (label, file name, source, target, expected file text)
    cases = [
        ("py last method before a top-level statement (reported)", "d.py",
         "class A:\n    def f(self):\n        pass\n\n    def g(self):\n        pass\n\n\nx = 1\n",
         "A.g", "class A:\n    def f(self):\n        pass\n\n\nx = 1\n"),
        ("py first function of the file (reported)", "d.py",
         "def f():\n    pass\n\n\ndef g():\n    pass\n", "f", "def g():\n    pass\n"),
        ("py first function with its comment", "d.py",
         "# Doc\ndef f():\n    pass\n\n\ndef g():\n    pass\n", "f", "def g():\n    pass\n"),
        ("py function between two others", "d.py",
         "import os\n\n\ndef f():\n    pass\n\n\ndef g():\n    pass\n\n\ndef h():\n    pass\n", "g",
         "import os\n\n\ndef f():\n    pass\n\n\ndef h():\n    pass\n"),
        ("py first function after the module docstring", "d.py",
         '"""Mod."""\n\n\ndef f():\n    pass\n\n\ndef g():\n    pass\n', "f",
         '"""Mod."""\n\n\ndef g():\n    pass\n'),
        ("py constant before a function: the wider gap stays", "d.py",
         "A = 1\nB = 2\n\n\ndef f():\n    pass\n", "B", "A = 1\n\n\ndef f():\n    pass\n"),
        ("py first method", "d.py",
         "class A:\n    def f(self):\n        pass\n\n    def g(self):\n        pass\n", "A.f",
         "class A:\n    def g(self):\n        pass\n"),
        ("py first method after the class docstring", "d.py",
         'class A:\n    """Doc."""\n\n    def f(self):\n        pass\n\n    def g(self):\n        pass\n', "A.f",
         'class A:\n    """Doc."""\n\n    def g(self):\n        pass\n'),
        ("js first method", "d.js",
         "class A {\n  f() {}\n\n  g() {}\n}\n", "A.f", "class A {\n  g() {}\n}\n"),
        ("js last method: no blank line before the }", "d.js",
         "class A {\n  f() {}\n\n  g() {}\n}\n\nfunction h() {}\n", "A.g",
         "class A {\n  f() {}\n}\n\nfunction h() {}\n"),
        ("ts first export", "d.ts",
         "export function f() {}\n\nexport function g() {}\n", "f", "export function g() {}\n"),
        ("ts only member", "d.ts", "class A {\n\n  f() {}\n\n}\n", "A.f", "class A {\n}\n"),
        ("go struct", "d.go",
         "package main\n\ntype Foo struct{}\n\nfunc main() {}\n", "Foo", "package main\n\nfunc main() {}\n"),
        ("go first function with its Godoc", "d.go",
         "package main\n\n// F.\nfunc F() {}\n\nfunc G() {}\n", "F", "package main\n\nfunc G() {}\n"),
        ("java first method", "D.java",
         "class A {\n    void f() {}\n\n    void g() {}\n}\n", "A.f", "class A {\n    void g() {}\n}\n"),
        ("java last method with its Javadoc", "D.java",
         "class A {\n    void f() {}\n\n    /** Doc. */\n    void g() {}\n}\n", "A.g",
         "class A {\n    void f() {}\n}\n"),
        ("ruby first method", "d.rb",
         "class A\n  def a\n  end\n\n  def b\n  end\nend\n", "A.a", "class A\n  def b\n  end\nend\n"),
        ("ruby last method", "d.rb",
         "class A\n  def a\n  end\n\n  def b\n  end\nend\n\nX = 1\n", "A.b",
         "class A\n  def a\n  end\nend\n\nX = 1\n"),
        ("cpp first method after an access label", "d.cpp",
         "class A {\npublic:\n  void f() {}\n\n  void g() {}\n};\n", "A.f",
         "class A {\npublic:\n  void g() {}\n};\n"),
        ("c first struct", "d.c",
         "struct S {\n  int a;\n};\n\nint f(void) { return 0; }\n", "S", "int f(void) { return 0; }\n"),
        ("c function right after an #include", "d.c",
         "#include <stdio.h>\nint f(void) { return 0; }\n\nint g(void) { return 0; }\n", "f",
         "#include <stdio.h>\n\nint g(void) { return 0; }\n"),
        ("py form feed line below the symbol stays (page break)", "d.py",
         "def f():\n    pass\n\n\x0c\ndef g():\n    pass\n", "f", "\x0c\ndef g():\n    pass\n"),
        ("py form feed line above the symbol stays (page break)", "d.py",
         "def f():\n    pass\n\x0c\n\ndef g():\n    pass\n", "g", "def f():\n    pass\n\x0c\n"),
    ]
    for label, name, source, target, expected in cases:
        _exact(f"delete_symbol ({label})",
               _edit_result(name, source, lambda a: a.delete_symbol(target)), expected)
    crlf = "def f():\n    pass\n\n\ndef g():\n    pass\n"
    _exact("delete_symbol (crlf first function)",
           _edit_result("d.py", crlf, lambda a: a.delete_symbol("f"), "\r\n"),
           "def g():\r\n    pass\r\n")

    # A kept comment stays where it was, the wider gap below it.
    _exact("delete_symbol include_leading_comments=False: comment and gap kept",
           _edit_result("d.py", "x = 1\n\n# keep\ndef f():\n    pass\n\n\ndef g():\n    pass\n",
                        lambda a: a.delete_symbol("f", include_leading_comments=False)),
           "x = 1\n\n# keep\n\n\ndef g():\n    pass\n")


def test_interface_indentation():
    print("\n═══ read_symbol depth=interface: members keep their indentation ═══")

    # (label, file name, source, target, expected interface)
    cases = [
        ("py (reported)", "i.py",
         "class A:\n    x = 1\n\n    def f(self, a):\n        return a\n", "A",
         "class A:\n    x = 1\n    def f(self, a): ..."),
        ("py nested class: its own indentation comes off", "i.py",
         'class O:\n    class A:\n        """Doc.\n\n        More.\n        """\n        x = 1\n\n'
         "        @property\n        def f(self):\n            return 1\n", "O.A",
         'class A:\n    """Doc.\n\n    More.\n    """\n    x = 1\n    @property\n    def f(self): ...'),
        ("ts decorated member, multi-line signature", "i.ts",
         "export class S {\n  private x: number;\n\n  @Get()\n  find(a: string,\n       b: number): void {\n"
         "    return;\n  }\n}\n", "S",
         "export class S {\n  private x: number;\n  @Get()\n  find(a: string,\n       b: number): void ...\n}"),
        ("ts class on one line", "i.ts",
         "class K { a = 1; b() {} }\n", "K", "class K {\n  a = 1;\n  b() ...\n}"),
        ("js tab-indented class", "i.js",
         "class K {\n\tconstructor() {\n\t\tthis.a = 1;\n\t}\n\n\tget() {}\n}\n", "K",
         "class K {\n\tconstructor() ...\n\tget() ...\n}"),
        ("java nested class", "I.java",
         "class Outer {\n    static class A {\n        int x;\n\n        /** Doc. */\n        void f() {}\n    }\n}\n",
         "Outer.A", "static class A {\n    int x;\n    /** Doc. */\n    void f() ...\n}"),
        ("cpp access labels keep their colons", "i.cpp",
         "class A {\npublic:\n  void f() {}\nprivate:\n  int x;\n};\n", "A",
         "class A {\npublic:\n  void f() ...\nprivate:\n  int x;\n};"),
        ("ruby", "i.rb",
         "class A\n  attr_reader :x\n\n  def f(a)\n    a\n  end\nend\n", "A",
         "class A\n  attr_reader :x\n  def f(a) ...\nend"),
        ("ruby nested class", "i.rb",
         "module M\n  class A\n    def f\n      1\n    end\n  end\nend\n", "M.A", "class A\n  def f ...\nend"),
        ("c struct", "i.c", "struct S {\n  int a;\n  char b;\n};\n", "S", "struct S {\n  int a;\n  char b;\n};"),
    ]
    for label, name, source, target, expected in cases:
        _exact(f"read_symbol depth=interface ({label})",
               _read_result(name, source, lambda a: a.read_symbol(target, depth="interface")),
               expected)


def test_js_ts_symbol_kinds():
    print("\n═══ JS/TS: generators, functions bound to names, enums, type aliases ═══")

    repro = (
        "enum E { A }\n"
        "type T = number;\n"
        "function* gen() {\n"
        "  yield 1;\n"
        "}\n"
        "const arrow = () => 1;\n"
        "export const ex = (x: number) => x;\n"
        "interface I {\n"
        "  a: number;\n"
        "}\n"
    )
    for ext in (".ts", ".tsx"):
        _exact(f"{ext} list_symbols: enum, type alias, generator, arrow functions (reported)",
               _read_result("kinds" + ext, repro, lambda a: a.list_symbols()),
               "enum E (line 1)\ntype T (line 2)\nfunction gen (line 3)\nfunction arrow (line 6)\n"
               "function ex (line 7)\ninterface I (line 8)")

    # Functions bound to names by const/let/var, exported or not, each name
    # of a declaration of several by its own value; other values are
    # constants and variables.
    js_kinds = (
        "const add = (a, b) => {\n"
        "  return a + b;\n"
        "};\n"
        "let fe = function (a) {\n"
        "  return a;\n"
        "};\n"
        "var g2 = function* () {};\n"
        "export function* gen() {}\n"
        "const n = 1;\n"
        "const two = () => 1, b = 2;\n"
        "export const ex = async (x) => x;\n"
    )
    listed_js = (
        "function add (line 1)\nfunction fe (line 4)\nfunction g2 (line 7)\nfunction gen (line 8)\n"
        "constant n (line 9)\nfunction two (line 10)\nconstant b (line 10)\nfunction ex (line 11)"
    )
    for ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
        listed = _read_result("kinds" + ext, js_kinds, lambda a: a.list_symbols())
        _exact(f"{ext} list_symbols: functions bound to names and generators", listed, listed_js)
        for target in [line.split()[1] for line in listed.splitlines()]:
            result = _read_result("kinds" + ext, js_kinds, lambda a: a.read_symbol(target))
            check(f"{ext} read_symbol('{target}'): listed name resolves",
                  "FAIL: " + result if result.startswith("REFUSED") else "PASS", "PASS")

    js = (
        "const x = 1;\n"
        "\n"
        "// Adds.\n"
        "const add = (a, b) => {\n"
        "  return a + b;\n"
        "};\n"
        "\n"
        "export const sq = (n) => n * n;\n"
        "\n"
        "let fe = function (a) {\n"
        "  return a;\n"
        "};\n"
        "\n"
        "function* gen() {\n"
        "  yield 1;\n"
        "}\n"
    )
    for ext in (".js", ".ts"):
        name = "bound" + ext

        def edit(action):
            return _edit_result(name, js, action)

        def read(action):
            return _read_result(name, js, action)

        _exact(f"{ext} read_symbol: arrow function", read(lambda a: a.read_symbol("add")),
               "const add = (a, b) => {\n  return a + b;\n};")
        _exact(f"{ext} read_symbol: exported arrow function", read(lambda a: a.read_symbol("sq")),
               "export const sq = (n) => n * n;")
        _exact(f"{ext} read_symbol depth=signature: arrow function",
               read(lambda a: a.read_symbol("add", depth="signature")), "const add = (a, b) =>")
        _exact(f"{ext} read_symbol depth=signature: arrow function with an expression body",
               read(lambda a: a.read_symbol("sq", depth="signature")), "const sq = (n) =>")
        _exact(f"{ext} read_symbol depth=interface: function expression",
               read(lambda a: a.read_symbol("fe", depth="interface")), "let fe = function (a)")
        _exact(f"{ext} read_symbol depth=signature: generator",
               read(lambda a: a.read_symbol("gen", depth="signature")), "function* gen()")
        _exact(f"{ext} replace_function_body: arrow function",
               edit(lambda a: a.replace_function_body("add", "return b + a;")),
               js.replace("  return a + b;", "  return b + a;"))
        _exact(f"{ext} insert_in_body at=top: arrow function",
               edit(lambda a: a.insert_in_body("add", "console.log(a);", at="top")),
               js.replace("  return a + b;", "  console.log(a);\n  return a + b;"))
        _exact(f"{ext} insert_in_body at=bottom: function expression",
               edit(lambda a: a.insert_in_body("fe", "a++;", at="bottom")),
               js.replace("  return a;\n", "  return a;\n  a++;\n"))
        _exact(f"{ext} replace_in_body: generator",
               edit(lambda a: a.replace_in_body("gen", "yield 1;", "yield 2;")),
               js.replace("yield 1;", "yield 2;"))
        _exact(f"{ext} delete_in_body: arrow function",
               edit(lambda a: a.delete_in_body("add", "  return a + b;\n")),
               js.replace("  return a + b;\n", ""))
        for tool, action in [
            ("replace_function_body", lambda a: a.replace_function_body("sq", "return n;")),
            ("insert_in_body", lambda a: a.insert_in_body("sq", "n++;", at="top")),
            ("replace_in_body", lambda a: a.replace_in_body("sq", "n * n", "n ** 2")),
        ]:
            result = edit(action)
            check(f"{ext} {tool}: expression body refused", result, "expression body")
            check(f"{ext} {tool}: refusal points to replace_function", result,
                  "rewrite it with replace_function")
            check(f"{ext} {tool}: file untouched", "PASS" if "[FILE CHANGED]" not in result else result, "PASS")
        _exact(f"{ext} replace_signature: with its const",
               edit(lambda a: a.replace_signature("add", "const add = (a, b, c) =>")),
               js.replace("(a, b) =>", "(a, b, c) =>"))
        _exact(f"{ext} replace_signature: the function's own part",
               edit(lambda a: a.replace_signature("add", "async (a, b, c) =>")),
               js.replace("(a, b) =>", "async (a, b, c) =>"))
        _exact(f"{ext} replace_signature: exported arrow function keeps `export`",
               edit(lambda a: a.replace_signature("sq", "const sq = (m) =>")),
               js.replace("(n) =>", "(m) =>"))
        _exact(f"{ext} replace_signature: depth=signature round trip",
               edit(lambda a: a.replace_signature("add", a.read_symbol("add", depth="signature"))), js)
        _exact(f"{ext} add_parameter: arrow function",
               edit(lambda a: a.add_parameter("add", "c")), js.replace("(a, b) =>", "(a, b, c) =>"))
        _exact(f"{ext} remove_parameter: arrow function",
               edit(lambda a: a.remove_parameter("add", "b")), js.replace("(a, b) =>", "(a) =>"))
        _exact(f"{ext} replace_function: exported arrow function",
               edit(lambda a: a.replace_function("sq", "export const sq = (n) => n ** 2;")),
               js.replace("n * n", "n ** 2"))
        _exact(f"{ext} delete_symbol: arrow function with its comment",
               edit(lambda a: a.delete_symbol("add")),
               js.replace("// Adds.\nconst add = (a, b) => {\n  return a + b;\n};\n\n", ""))
        _exact(f"{ext} edit_leading_comment replace: arrow function",
               edit(lambda a: a.edit_leading_comment("add", "replace", "// Sums.")),
               js.replace("// Adds.", "// Sums."))
        _exact(f"{ext} edit_leading_comment add: above the export",
               edit(lambda a: a.edit_leading_comment("sq", "add", "// Squares.")),
               js.replace("export const sq", "// Squares.\nexport const sq"))
        _exact(f"{ext} insert_sibling before: above the comment",
               edit(lambda a: a.insert_sibling("add", "const y = 2;", "before")),
               js.replace("// Adds.", "const y = 2;\n\n// Adds."))
        _exact(f"{ext} insert_sibling after a generator",
               edit(lambda a: a.insert_sibling("gen", "const y = 2;", "after")),
               js + "\nconst y = 2;\n")

    # One function among several names is a function.
    _exact("js insert_in_body: function in a declaration of several names",
           _edit_result("multi.js", "const a = () => {\n  return 1;\n}, b = 2;\n",
                        lambda a: a.insert_in_body("a", "x();", at="top")),
           "const a = () => {\n  x();\n  return 1;\n}, b = 2;\n")
    # An object-literal closure with an expression body points to replace_value.
    check("js closure with an expression body: refusal points to replace_value",
          _edit_result("obj.js", "const app = {\n  h: () => 1,\n};\n",
                       lambda a: a.replace_function_body("app.h", "return 2;")),
          "rewrite it with replace_value")

    tsd = (
        "enum E {\n"
        "  A,\n"
        "  B,\n"
        "}\n"
        "\n"
        "/** T. */\n"
        "type T = number;\n"
        "\n"
        "export interface I {\n"
        "  a: number;\n"
        "}\n"
    )
    _exact("ts list_symbols: enum, type alias and exported interface",
           _read_result("kinds.ts", tsd, lambda a: a.list_symbols()),
           "enum E (line 1)\ntype T (line 7)\ninterface I (line 9)")
    _exact("ts read_symbol: enum", _read_result("kinds.ts", tsd, lambda a: a.read_symbol("E")),
           "enum E {\n  A,\n  B,\n}")
    _exact("ts read_symbol: type alias", _read_result("kinds.ts", tsd, lambda a: a.read_symbol("T")),
           "type T = number;")
    _exact("ts read_symbol depth=interface: enum",
           _read_result("kinds.ts", tsd, lambda a: a.read_symbol("E", depth="interface")),
           "enum E {\n  A,\n  B,\n}")
    _exact("ts replace_function: type alias",
           _edit_result("kinds.ts", tsd, lambda a: a.replace_function("T", "type T = string;")),
           tsd.replace("type T = number;", "type T = string;"))
    _exact("ts delete_symbol: type alias with its doc comment",
           _edit_result("kinds.ts", tsd, lambda a: a.delete_symbol("T")),
           tsd.replace("/** T. */\ntype T = number;\n\n", ""))
    _exact("ts delete_symbol: enum",
           _edit_result("kinds.ts", tsd, lambda a: a.delete_symbol("E")),
           tsd[tsd.index("/** T. */"):])
    _exact("ts edit_leading_comment add: enum",
           _edit_result("kinds.ts", tsd, lambda a: a.edit_leading_comment("E", "add", "// E.")),
           "// E.\n" + tsd)
    _exact("ts insert_sibling before: type alias",
           _edit_result("kinds.ts", tsd, lambda a: a.insert_sibling("T", "const z = 1;", "before")),
           tsd.replace("/** T. */", "const z = 1;\n\n/** T. */"))

def _check_loads(label: str, name: str, text: str):
    """check() that an edited JSON or TOML file still loads."""
    import json as _json
    import tomllib

    if text.startswith("REFUSED"):
        return
    try:
        if name.endswith(".json"):
            _json.loads(text)
        elif name.endswith(".toml"):
            tomllib.loads(text)
        got = "PASS"
    except ValueError as e:
        got = f"FAIL: {type(e).__name__}: {e}"
    check(f"{label}: still loads", got, "PASS")


def test_config_quoted_paths():
    print("\n═══ Config paths: a quoted segment is one key, dots included ═══")

    # (label, file name, content, edit, expected file, or None if the
    # target must not be found)
    cases = [
        ("json replace_value", "q.json", '{\n  "editor.fontSize": 12\n}\n',
         lambda a: a.replace_value('"editor.fontSize"', "14"), '{\n  "editor.fontSize": 14\n}\n'),
        ("json nested", "q.json", '{"a": {"b.c": {"d": 1}}}\n',
         lambda a: a.replace_value('a."b.c".d', "2"), '{"a": {"b.c": {"d": 2}}}\n'),
        ("json quoted path is the dotted key", "q.json", '{"a.b": 1, "a": {"b": 2}}\n',
         lambda a: a.replace_value('"a.b"', "3"), '{"a.b": 3, "a": {"b": 2}}\n'),
        ("json bare path still nests", "q.json", '{"a.b": 1, "a": {"b": 2}}\n',
         lambda a: a.replace_value("a.b", "3"), '{"a.b": 1, "a": {"b": 3}}\n'),
        ("json escaped quote in a segment", "q.json", '{"say \\"hi\\".x": 1}\n',
         lambda a: a.replace_value('"say \\"hi\\".x"', "2"), '{"say \\"hi\\".x": 2}\n'),
        ("json spaces around a quoted segment", "q.json", '{"a": {"b.c": 1}}\n',
         lambda a: a.replace_value('a. "b.c" ', "2"), '{"a": {"b.c": 2}}\n'),
        ("json delete_key", "q.json", '{\n  "editor.fontSize": 12,\n  "x": 1\n}\n',
         lambda a: a.delete_key('"editor.fontSize"'), '{\n  "x": 1\n}\n'),
        ("json add_key parent", "q.json", '{"a.b": {"x": 1}}\n',
         lambda a: a.add_key('"a.b"', "k", "2"), '{"a.b": {"x": 1, "k": 2}}\n'),
        ("json add_key key is one name", "q.json", '{"a": 1}\n',
         lambda a: a.add_key("", "x.y", "2"), '{"a": 1, "x.y": 2}\n'),
        ("json add_key key given quoted", "q.json", '{"a": 1}\n',
         lambda a: a.add_key("", '"x.y"', "2"), '{"a": 1, "x.y": 2}\n'),
        ("json append_to_array", "q.json", '{"a.b": [1]}\n',
         lambda a: a.append_to_array('"a.b"', "2"), '{"a.b": [1, 2]}\n'),
        ("json remove_from_array", "q.json", '{"a.b": [1, 2]}\n',
         lambda a: a.remove_from_array('"a.b"', "2"), '{"a.b": [1]}\n'),
        ("json array element", "q.json", '{"a": [1, 2]}\n',
         lambda a: a.replace_value("a.0", "3"), None),
        ("yaml plain key", "q.yaml", "a.b: 1\n",
         lambda a: a.replace_value('"a.b"', "2"), "a.b: 2\n"),
        ("yaml double-quoted key", "q.yaml", '"a.b": 1\n',
         lambda a: a.replace_value('"a.b"', "2"), '"a.b": 2\n'),
        ("yaml single-quoted key", "q.yaml", "'a.b': 1\n",
         lambda a: a.replace_value('"a.b"', "2"), "'a.b': 2\n"),
        ("yaml bare path still nests", "q.yaml", "a.b: 1\na:\n  b: 2\n",
         lambda a: a.replace_value("a.b", "3"), "a.b: 1\na:\n  b: 3\n"),
        ("yaml nested", "q.yaml", 'x:\n  "y.z":\n    k: 1\n',
         lambda a: a.replace_value('x."y.z".k', "2"), 'x:\n  "y.z":\n    k: 2\n'),
        ("yaml delete_key", "q.yaml", "a.b: 1\nc: 2\n",
         lambda a: a.delete_key('"a.b"'), "c: 2\n"),
        ("yaml add_key parent", "q.yaml", "a.b:\n  x: 1\n",
         lambda a: a.add_key('"a.b"', "k", "2"), "a.b:\n  x: 1\n  k: 2\n"),
        ("yaml append_to_array", "q.yaml", "a.b:\n  - 1\n",
         lambda a: a.append_to_array('"a.b"', "2"), "a.b:\n  - 1\n  - 2\n"),
        ("yaml remove_from_array", "q.yaml", "a.b: [1, 2]\n",
         lambda a: a.remove_from_array('"a.b"', "2"), "a.b: [1]\n"),
        ("yaml edit_leading_comment", "q.yaml", "x: 1\na.b: 2\n",
         lambda a: a.edit_leading_comment('"a.b"', "add", "# note"), "x: 1\n# note\na.b: 2\n"),
        ("yaml sequence element", "q.yaml", "a:\n  - 1\n",
         lambda a: a.replace_value("a.0", "3"), None),
        ("toml basic-string key", "q.toml", '"a.b" = 1\n',
         lambda a: a.replace_value('"a.b"', "2"), '"a.b" = 2\n'),
        ("toml basic-string key, single-quoted path", "q.toml", '"a.b" = 1\n',
         lambda a: a.replace_value("'a.b'", "2"), '"a.b" = 2\n'),
        ("toml literal-string key", "q.toml", "'a.b' = 1\n",
         lambda a: a.replace_value('"a.b"', "2"), "'a.b' = 2\n"),
        ("toml key with an escape", "q.toml", '"caf\\u00e9" = 1\n',
         lambda a: a.replace_value("café", "2"), '"caf\\u00e9" = 2\n'),
        ("toml quoted header", "q.toml", '[x."y.z"]\nk = 1\n',
         lambda a: a.replace_value("x.'y.z'.k", "2"), '[x."y.z"]\nk = 2\n'),
        ("toml literal-string header", "q.toml", "[x.'y.z']\nk = 1\n",
         lambda a: a.replace_value('x."y.z".k', "2"), "[x.'y.z']\nk = 2\n"),
        ("toml header with spaces", "q.toml", '[ x . "y.z" ]\nk = 1\n',
         lambda a: a.replace_value('x."y.z".k', "2"), '[ x . "y.z" ]\nk = 2\n'),
        ("toml dotted key at the root", "q.toml", "x.y = 1\n",
         lambda a: a.replace_value("x.y", "2"), "x.y = 2\n"),
        ("toml dotted key in a [table]", "q.toml", "[t]\nx.y = 1\n",
         lambda a: a.replace_value("t.x.y", "2"), "[t]\nx.y = 2\n"),
        ("toml delete_key", "q.toml", '"a.b" = 1\nc = 2\n',
         lambda a: a.delete_key('"a.b"'), "c = 2\n"),
        ("toml add_key to a quoted [table]", "q.toml", '[x."y.z"]\nk = 1\n',
         lambda a: a.add_key("x.'y.z'", "n", "2"), '[x."y.z"]\nk = 1\nn = 2\n'),
        ("toml append_to_array", "q.toml", '"a.b" = [1]\n',
         lambda a: a.append_to_array('"a.b"', "2"), '"a.b" = [1, 2]\n'),
        ("toml remove_from_array", "q.toml", '"a.b" = [1, 2]\n',
         lambda a: a.remove_from_array('"a.b"', "2"), '"a.b" = [1]\n'),
        ("toml comment on a key", "q.toml", 'v = 1\n"a.b" = 2\n',
         lambda a: a.edit_leading_comment('"a.b"', "add", "# note"), 'v = 1\n# note\n"a.b" = 2\n'),
        ("toml comment on a quoted [table]", "q.toml", 'v = 1\n\n[x."y.z"]\nk = 1\n',
         lambda a: a.edit_leading_comment('x."y.z"', "add", "# note"),
         'v = 1\n\n# note\n[x."y.z"]\nk = 1\n'),
        ("toml comment on a dotted [table]", "q.toml", "[tool.uv]\nk = 1\n",
         lambda a: a.edit_leading_comment("tool.uv", "add", "# note"), "# note\n[tool.uv]\nk = 1\n"),
        ("toml array element", "q.toml", "a = [1, 2]\n",
         lambda a: a.replace_value("a.0", "3"), None),
    ]
    for label, name, content, action, expected in cases:
        result = _edit_result(name, content, action)
        if expected is None:
            check(f"{label}: not addressable", result, "not found")
            check(f"{label}: file untouched", "PASS" if "[FILE CHANGED]" not in result else "FAIL", "PASS")
        else:
            _exact(label, result, expected)
            _check_loads(label, name, result)

    for label, name, content, target, expected in [
        ("json", "q.json", '{"editor.fontSize": 12}\n', '"editor.fontSize"', "12"),
        ("yaml", "q.yaml", "'a.b': 1\n", '"a.b"', "1"),
        ("toml", "q.toml", "[x.'y.z']\nk = 1\n", 'x."y.z".k', "1"),
    ]:
        _exact(f"read_symbol {label} quoted segment",
               _read_result(name, content, lambda a: a.read_symbol(target)), expected)

    # A duplicate refusal names a target that works, quoted where needed.
    for label, name, content, parent, key, target, expected in [
        ("json", "q.json", '{"editor.fontSize": 12}\n', "", "editor.fontSize",
         '"editor.fontSize"', '{"editor.fontSize": 14}\n'),
        ("json nested", "q.json", '{"a": {"b.c": 1}}\n', "a", "b.c", 'a."b.c"', '{"a": {"b.c": 14}}\n'),
        ("yaml", "q.yaml", "a.b: 1\n", "", "a.b", '"a.b"', "a.b: 14\n"),
        ("toml", "q.toml", '"a.b" = 1\n', "", '"a.b"', '"a.b"', '"a.b" = 14\n'),
    ]:
        path = _write_temp(name, content)
        message = _refusal(lambda: Applier(path).add_key(parent, key, "2"))
        check(f"{label} duplicate refusal names a quoted target", message, f"target '{target}'")
        try:
            Applier(path).replace_value(target, "14")
            result = read_file(path)
        except ApplierError as e:
            result = f"REFUSED: {e}"
        _exact(f"{label} duplicate refusal: its target works with replace_value", result, expected)
        os.remove(path)


def test_config_inline_entries():
    print("\n═══ Config paths into YAML flow mappings and TOML inline tables ═══")

    # (label, file name, content, edit, expected file text)
    cases = [
        ("yaml replace_value", "f.yaml", "a: {x: 1, y: 2}\n",
         lambda a: a.replace_value("a.x", "5"), "a: {x: 5, y: 2}\n"),
        ("yaml replace_value, nested", "f.yaml", "a: {b: {c: 1}}\n",
         lambda a: a.replace_value("a.b.c", "5"), "a: {b: {c: 5}}\n"),
        ("yaml replace_value in a root flow mapping", "f.yaml", "{x: 1}\n",
         lambda a: a.replace_value("x", "5"), "{x: 5}\n"),
        ("yaml replace_value over several lines", "f.yaml", "a: {\n  x: 1,\n  y: 2\n}\n",
         lambda a: a.replace_value("a.y", "5"), "a: {\n  x: 1,\n  y: 5\n}\n"),
        ("yaml replace_value on a key without a value", "f.yaml", "a: {x, y: 1}\n",
         lambda a: a.replace_value("a.x", "5"), "a: {x: 5, y: 1}\n"),
        ("yaml replace_value on `x: ,`", "f.yaml", "a: {x: , y: 1}\n",
         lambda a: a.replace_value("a.x", "5"), "a: {x: 5, y: 1}\n"),
        ("yaml replace_value on `x:,`", "f.yaml", "a: {x:, y: 1}\n",
         lambda a: a.replace_value("a.x", "5"), "a: {x: 5, y: 1}\n"),
        ("yaml replace_value after add_key", "f.yaml", "a: {x: 1}\n",
         lambda a: (a.add_key("a", "k", "2"), Applier(a.filepath).replace_value("a.k", "3")),
         "a: {x: 1, k: 3}\n"),
        ("yaml delete_key, first", "f.yaml", "a: {x: 1, y: 2}\n",
         lambda a: a.delete_key("a.x"), "a: {y: 2}\n"),
        ("yaml delete_key, last", "f.yaml", "a: {x: 1, y: 2}\n",
         lambda a: a.delete_key("a.y"), "a: {x: 1}\n"),
        ("yaml delete_key, only", "f.yaml", "a: {b: {c: 1}}\n",
         lambda a: a.delete_key("a.b.c"), "a: {b: {}}\n"),
        ("yaml delete_key, key without a value", "f.yaml", "a: {x, y: 1}\n",
         lambda a: a.delete_key("a.x"), "a: {y: 1}\n"),
        ("yaml delete_key, own line", "f.yaml", "a: {\n  x: 1,\n  y: 2\n}\n",
         lambda a: a.delete_key("a.y"), "a: {\n  x: 1\n}\n"),
        ("yaml add_key, nested empty flow mapping", "f.yaml", "a: {b: {}}\n",
         lambda a: a.add_key("a.b", "k", "1"), "a: {b: { k: 1 }}\n"),
        ("yaml add_key, nested flow mapping", "f.yaml", "a: {b: {c: 1}}\n",
         lambda a: a.add_key("a.b", "k", "2"), "a: {b: {c: 1, k: 2}}\n"),
        ("yaml add_key under a flow key without a value", "f.yaml", "a: {x, y: 1}\n",
         lambda a: a.add_key("a.x", "k", "2"), "a: {x: { k: 2 }, y: 1}\n"),
        ("yaml add_key under `x:` in a flow mapping", "f.yaml", "a: {x: , y: 1}\n",
         lambda a: a.add_key("a.x", "k", "2"), "a: {x: { k: 2 }, y: 1}\n"),
        ("yaml append_to_array in a flow mapping", "f.yaml", "a: {b: [1]}\n",
         lambda a: a.append_to_array("a.b", "2"), "a: {b: [1, 2]}\n"),
        ("yaml comment on a flow key on its own line", "f.yaml", "a: {\n  x: 1,\n  y: 2\n}\n",
         lambda a: a.edit_leading_comment("a.y", "add", "# note"), "a: {\n  x: 1,\n  # note\n  y: 2\n}\n"),
        ("toml replace_value", "f.toml", "t = { a = 1, b = 2 }\n",
         lambda a: a.replace_value("t.a", "5"), "t = { a = 5, b = 2 }\n"),
        ("toml replace_value, nested", "f.toml", "t = { b = { c = 1 } }\n",
         lambda a: a.replace_value("t.b.c", "5"), "t = { b = { c = 5 } }\n"),
        ("toml replace_value in a [table]", "f.toml", "[s]\nt = { a = 1 }\n",
         lambda a: a.replace_value("s.t.a", "5"), "[s]\nt = { a = 5 }\n"),
        ("toml replace_value, quoted inner key", "f.toml", 't = { "a.b" = 1 }\n',
         lambda a: a.replace_value('t."a.b"', "5"), 't = { "a.b" = 5 }\n'),
        ("toml replace_value, dotted inner key", "f.toml", "t = { a.b = 1 }\n",
         lambda a: a.replace_value("t.a.b", "5"), "t = { a.b = 5 }\n"),
        ("toml replace_value after add_key", "f.toml", "t = { a = 1 }\n",
         lambda a: (a.add_key("t", "k", "2"), Applier(a.filepath).replace_value("t.k", "3")),
         "t = { a = 1, k = 3 }\n"),
        ("toml delete_key, first", "f.toml", "t = { a = 1, b = 2 }\n",
         lambda a: a.delete_key("t.a"), "t = { b = 2 }\n"),
        ("toml delete_key, last", "f.toml", "t = { a = 1, b = 2 }\n",
         lambda a: a.delete_key("t.b"), "t = { a = 1 }\n"),
        ("toml delete_key, only", "f.toml", "t = { b = { c = 1 } }\n",
         lambda a: a.delete_key("t.b.c"), "t = { b = {} }\n"),
        ("toml add_key, nested inline table", "f.toml", "t = { b = { c = 1 } }\n",
         lambda a: a.add_key("t.b", "d", "2"), "t = { b = { c = 1, d = 2 } }\n"),
        ("toml append_to_array in an inline table", "f.toml", "t = { d = [] }\n",
         lambda a: a.append_to_array("t.d", "1"), "t = { d = [1] }\n"),
    ]
    for label, name, content, action, expected in cases:
        result = _edit_result(name, content, action)
        _exact(label, result, expected)
        _check_loads(label, name, result)

    for label, name, content, target, expected in [
        ("yaml flow key", "f.yaml", "a: {x: 1, y: {z: 2}}\n", "a.y.z", "2"),
        ("yaml flow key without a value", "f.yaml", "a: {x, y: 1}\n", "a.x", ""),
        ("toml inline key", "f.toml", "t = { a = 1, b = { c = 2 } }\n", "t.b.c", "2"),
    ]:
        _exact(f"read_symbol {label}", _read_result(name, content, lambda a: a.read_symbol(target)), expected)

    # A comment line above an inline key would belong to the key its line
    # starts with.
    for label, name, content, target in [
        ("yaml", "f.yaml", "a: {x: 1}\n", "a.x"),
        ("toml", "f.toml", "t = { a = 1 }\n", "t.a"),
    ]:
        result = _edit_result(name, content, lambda a: a.edit_leading_comment(target, "add", "# note"))
        check(f"{label} comment on an inline key: refused", result, "REFUSED: ")
        check(f"{label} comment on an inline key: says why", result, "does not start its line")
        check(f"{label} comment on an inline key: file untouched",
              "PASS" if "[FILE CHANGED]" not in result else "FAIL", "PASS")

    for label, name, content, parent, key, target in [
        ("yaml nested flow mapping", "f.yaml", "a: {b: {c: 1}}\n", "a.b", "c", "a.b.c"),
        ("toml nested inline table", "f.toml", "t = { b = { c = 1 } }\n", "t.b", "c", "t.b.c"),
    ]:
        result = _edit_result(name, content, lambda a: a.add_key(parent, key, "2"))
        check(f"{label} duplicate names the key's target", result, f"target '{target}'")


def test_yaml_keys_without_value():
    print("\n═══ YAML keys with no value: read_symbol, replace_value, comments ═══")

    # (label, content, target, new value, expected file text)
    cases = [
        ("one line", "a:\nb: 1\n", "a", "3", "a: 3\nb: 1\n"),
        ("nested", "x:\n  a:\n  b: 1\n", "x.a", "3", "x:\n  a: 3\n  b: 1\n"),
        ("before a comment", "a: # later\nb: 1\n", "a", "3", "a: 3 # later\nb: 1\n"),
        ("trailing space", "a: \nb: 1\n", "a", "3", "a: 3\nb: 1\n"),
        ("last line", "b: 1\na:\n", "a", "3", "b: 1\na: 3\n"),
        ("flow mapping value", "a:\nb: 1\n", "a", "{k: v}", "a: {k: v}\nb: 1\n"),
        ("scalar with a colon", "a:\nb: 1\n", "a", "http://x.y", "a: http://x.y\nb: 1\n"),
        ("leading newline", "a:\nb: 1\n", "a", "\n3", "a: 3\nb: 1\n"),
        ("block mapping", "a:\nb: 1\n", "a", "k: 1\nm: 2", "a:\n  k: 1\n  m: 2\nb: 1\n"),
        ("one-line block mapping", "a:\nb: 1\n", "a", "k: v", "a:\n  k: v\nb: 1\n"),
        ("block sequence", "a:\nb: 1\n", "a", "- 1\n- 2", "a:\n  - 1\n  - 2\nb: 1\n"),
        ("one-item block sequence", "a:\nb: 1\n", "a", "- 1", "a:\n  - 1\nb: 1\n"),
        ("block in a 4-space file", "top:\n    a:\n    b: 1\n", "top.a", "k: 1",
         "top:\n    a:\n        k: 1\n    b: 1\n"),
        ("block keeps relative indentation", "a:\n", "a", "k:\n  m: 1", "a:\n  k:\n    m: 1\n"),
        ("quoted key with a dot", '"a.b":\nc: 1\n', '"a.b"', "3", '"a.b": 3\nc: 1\n'),
        ("block below a comment", "a: # c\nb: 1\n", "a", "k: 1\nm: 2", "a: # c\n  k: 1\n  m: 2\nb: 1\n"),
        ("block on a last line with no newline", "b: 1\na:", "a", "k: 1\nm: 2", "b: 1\na:\n  k: 1\n  m: 2"),
        # A block scalar header or node properties stay on the key's line.
        ("block scalar", "a:\nb: 1\n", "a", "|\n  line one\n  line two", "a: |\n  line one\n  line two\nb: 1\n"),
        ("block scalar before a comment", "a: # c\nb: 1\n", "a", "|\n  text", "a: | # c\n  text\nb: 1\n"),
        ("folded scalar", "a:\nb: 1\n", "a", ">-\n  text", "a: >-\n  text\nb: 1\n"),
        ("anchor", "a:\nb: 1\n", "a", "&x\n  k: 1", "a: &x\n  k: 1\nb: 1\n"),
        ("tag, nested", "x:\n  a:\n", "x.a", "!!map\n  k: 1", "x:\n  a: !!map\n    k: 1\n"),
    ]
    for label, content, target, value, expected in cases:
        result = _edit_result("n.yaml", content, lambda a: a.replace_value(target, value))
        _exact(f"yaml replace_value on a key with no value ({label})", result, expected)

    for label, value, expected in [
        ("one line", "3", "a: 3\r\nb: 1\r\n"),
        ("block", "k: 1\nm: 2", "a:\r\n  k: 1\r\n  m: 2\r\nb: 1\r\n"),
    ]:
        result = _edit_result("n.yaml", "a:\nb: 1\n", lambda a: a.replace_value("a", value), newline="\r\n")
        _exact(f"yaml replace_value on a key with no value, CRLF ({label})", result, expected)

    _exact("yaml read_symbol on a key with no value",
           _read_result("n.yaml", "x:\n  a:\n  b: 1\n", lambda a: a.read_symbol("x.a")), "")
    check("yaml read_symbol on a missing key: still refused",
          _read_result("n.yaml", "a:\n", lambda a: a.read_symbol("b")), "REFUSED: Target 'b' not found")

    # (label, content, target, op, comment, expected file text)
    for label, content, target, op, comment, expected in [
        ("add", "x: 1\na:\nb: 1\n", "a", "add", "# note", "x: 1\n# note\na:\nb: 1\n"),
        ("add, nested", "x:\n  a:\n  b: 1\n", "x.a", "add", "# note", "x:\n  # note\n  a:\n  b: 1\n"),
        ("replace", "# old\na:\nb: 1\n", "a", "replace", "# new", "# new\na:\nb: 1\n"),
        ("remove", "# old\na:\nb: 1\n", "a", "remove", "", "a:\nb: 1\n"),
    ]:
        result = _edit_result("n.yaml", content, lambda a: a.edit_leading_comment(target, op, comment))
        _exact(f"yaml edit_leading_comment on a key with no value ({label})", result, expected)


def test_append_to_array_layout():
    print("\n═══ append_to_array keeps the array's layout ═══")

    # (label, file name, content, target, value, expected file text)
    cases = [
        ("json inline", "r.json", '{"a": [1, 2]}\n', "a", "3", '{"a": [1, 2, 3]}\n'),
        ("json inline, padded", "r.json", '{"a": [ 1, 2 ]}\n', "a", "3", '{"a": [ 1, 2, 3 ]}\n'),
        ("json empty", "r.json", '{"a": []}\n', "a", "3", '{"a": [3]}\n'),
        ("json inline in a multi-line object", "r.json", '{\n  "a": [1, 2]\n}\n', "a", "3",
         '{\n  "a": [1, 2, 3]\n}\n'),
        ("json one per line", "r.json", '{\n  "a": [\n    1,\n    2\n  ]\n}\n', "a", "3",
         '{\n  "a": [\n    1,\n    2,\n    3\n  ]\n}\n'),
        ("json objects one per line", "r.json", '{\n  "a": [\n    {"x": 1}\n  ]\n}\n', "a", '{"x": 2}',
         '{\n  "a": [\n    {"x": 1},\n    {"x": 2}\n  ]\n}\n'),
        ("json empty, brackets on two lines", "r.json", '{\n  "a": [\n  ]\n}\n', "a", "3",
         '{\n  "a": [\n    3\n  ]\n}\n'),
        ("json tab-indented", "r.json", '{\n\t"a": [\n\t\t1\n\t]\n}\n', "a", "2",
         '{\n\t"a": [\n\t\t1,\n\t\t2\n\t]\n}\n'),
        ("toml inline", "r.toml", "a = [1, 2]\n", "a", "3", "a = [1, 2, 3]\n"),
        ("toml inline, trailing comma", "r.toml", "a = [1, 2,]\n", "a", "3", "a = [1, 2, 3,]\n"),
        ("toml empty", "r.toml", "a = []\n", "a", "3", "a = [3]\n"),
        ("toml one per line", "r.toml", "a = [\n    1,\n    2\n]\n", "a", "3",
         "a = [\n    1,\n    2,\n    3\n]\n"),
        ("toml one per line, trailing comma", "r.toml", "a = [\n  1,\n  2,\n]\n", "a", "3",
         "a = [\n  1,\n  2,\n  3,\n]\n"),
        ("toml comment on the last line", "r.toml", "a = [\n  1,\n  2, # two\n]\n", "a", "3",
         "a = [\n  1,\n  2, # two\n  3,\n]\n"),
        ("toml comment, no trailing comma", "r.toml", "a = [\n  1,\n  2 # two\n]\n", "a", "3",
         "a = [\n  1,\n  2, # two\n  3\n]\n"),
        ("toml empty, brackets on two lines", "r.toml", "a = [\n]\n", "a", "3", "a = [\n  3\n]\n"),
        ("toml in a [table]", "r.toml", '[p]\ndeps = [\n    "a",\n]\n', "p.deps", '"b"',
         '[p]\ndeps = [\n    "a",\n    "b",\n]\n'),
        ("yaml flow", "r.yaml", "a: [1, 2]\n", "a", "3", "a: [1, 2, 3]\n"),
        ("yaml flow, padded", "r.yaml", "a: [ 1 ]\n", "a", "3", "a: [ 1, 3 ]\n"),
        ("yaml flow, empty", "r.yaml", "a: []\n", "a", "3", "a: [3]\n"),
        ("yaml flow, one per line", "r.yaml", "a: [\n  1,\n  2\n]\n", "a", "3", "a: [\n  1,\n  2,\n  3\n]\n"),
        ("yaml flow, trailing comma", "r.yaml", "a: [\n  1,\n  2,\n]\n", "a", "3",
         "a: [\n  1,\n  2,\n  3,\n]\n"),
    ]
    for label, name, content, target, value, expected in cases:
        result = _edit_result(name, content, lambda a: a.append_to_array(target, value))
        _exact(f"append_to_array {label}", result, expected)
        _check_loads(f"append_to_array {label}", name, result)

    result = _edit_result("r.toml", "a = [\n  1,\n]\n", lambda a: a.append_to_array("a", "2"), newline="\r\n")
    _exact("append_to_array toml one per line, CRLF", result, "a = [\r\n  1,\r\n  2,\r\n]\r\n")


def test_indentation_whitespace():
    print("\n═══ Indentation is spaces and tabs only: form feeds and U+2028 stay ═══")

    # (label, content, edit, expected file text)
    cases = [
        ("insert_sibling: a form feed before the new def stays", "def f():\n    return 1\n",
         lambda a: a.insert_sibling("f", "\x0cdef g():\n    return 2\n", "after"),
         "def f():\n    return 1\n\n\n\x0cdef g():\n    return 2\n"),
        ("insert_sibling: the target's form feed is not copied", "\x0cdef f():\n    return 1\n",
         lambda a: a.insert_sibling("f", "def g():\n    return 2\n", "after"),
         "\x0cdef f():\n    return 1\n\n\ndef g():\n    return 2\n"),
        ("replace_function: no form feed added to the body", "x = 1\n\n\n\x0cdef f():\n    return 1\n",
         lambda a: a.replace_function("f", "def f():\n    return 2\n"),
         "x = 1\n\n\ndef f():\n    return 2\n"),
        ("add_method: U+2028 starting a docstring line stays", "class A:\n    def f(self):\n        return 1\n",
         lambda a: a.add_method("A", '        def g(self):\n            """Doc.\n\u2028more"""\n            return 1\n'),
         'class A:\n    def f(self):\n        return 1\n\n    def g(self):\n        """Doc.\n\u2028more"""\n        return 1\n'),
        ("add_method: a form feed starting a string line stays", "class A:\n    def f(self):\n        return 1\n",
         lambda a: a.add_method("A", '        def g(self):\n            s = """\n\x0cpage"""\n            return s\n'),
         'class A:\n    def f(self):\n        return 1\n\n    def g(self):\n        s = """\n\x0cpage"""\n        return s\n'),
    ]
    for label, content, action, expected in cases:
        _exact(label, _edit_result("w.py", content, action), expected)

    path = _write_temp("w.py", "x = 1\n")
    a = Applier(path)
    for label, line, indent in [
        ("a form feed is not indentation", "\x0c    x", ""),
        ("spaces and tabs before a form feed", " \t\x0cx", " \t"),
        ("U+2028 is not indentation", "  \u2028x", "  "),
        ("U+00A0 is not indentation", "\u00a0x", ""),
    ]:
        _exact(f"_get_indent: {label}", repr(a._get_indent(line)), repr(indent))
    _exact("_reindent keeps form feeds and U+2028",
           repr(a._reindent(["    a", "\u2028b", "  \x0cc"], "  ")),
           repr(["  a", "  \u2028b", "  \x0cc"]))
    os.remove(path)


def test_leading_comments_in_strings():
    print("\n═══ Leading comments: comment-like lines inside strings are text ═══")

    yaml_job = "job:\n  run: |\n    echo hi\n    # step two\n  env: 1\n"
    # (label, file name, source, edit, expected file text)
    cases = [
        ("insert_sibling before: py `#` line closing a string (reported)", "s.py",
         'X = """abc\n# fake comment"""\ndef f():\n    pass\n',
         lambda a: a.insert_sibling("f", "def g():\n    pass", "before"),
         'X = """abc\n# fake comment"""\n\n\ndef g():\n    pass\n\n\ndef f():\n    pass\n'),
        ("insert_sibling before: js `//` line closing a template literal (reported)", "s.js",
         "const s = `\n// not a comment`;\nfunction f() {}\n",
         lambda a: a.insert_sibling("f", "function g() {}", "before"),
         "const s = `\n// not a comment`;\n\nfunction g() {}\n\nfunction f() {}\n"),
        ("insert_sibling before: a real comment under the string still moves up", "s.py",
         'X = """abc\n# fake"""\n# Doc for f\ndef f():\n    pass\n',
         lambda a: a.insert_sibling("f", "def g():\n    pass", "before"),
         'X = """abc\n# fake"""\n\n\ndef g():\n    pass\n\n\n# Doc for f\ndef f():\n    pass\n'),
        ("insert_sibling before: `/*` opening a string is no comment start", "s.js",
         "const s = `\n/*`; /* real\ncomment */\nfunction f() {}\n",
         lambda a: a.insert_sibling("f", "function g() {}", "before"),
         "const s = `\n/*`; /* real\ncomment */\n\nfunction g() {}\n\nfunction f() {}\n"),
        ("delete_symbol: the string's last line is not deleted as a comment", "s.py",
         'X = """abc\n# fake comment"""\ndef f():\n    pass\n',
         lambda a: a.delete_symbol("f"),
         'X = """abc\n# fake comment"""\n'),
        ("edit_leading_comment remove: a YAML block scalar line is not a comment (reported)", "s.yaml",
         yaml_job, lambda a: a.edit_leading_comment("job.env", "remove"),
         "REFUSED: No leading comment found above 'job.env'"),
        ("edit_leading_comment add: lands under the block scalar", "s.yaml",
         yaml_job, lambda a: a.edit_leading_comment("job.env", "add", "# env doc"),
         "job:\n  run: |\n    echo hi\n    # step two\n  # env doc\n  env: 1\n"),
        ("edit_leading_comment replace: the block scalar keeps its line", "s.yaml",
         yaml_job, lambda a: a.edit_leading_comment("job.env", "replace", "# env doc"),
         "job:\n  run: |\n    echo hi\n    # step two\n  # env doc\n  env: 1\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(label, _edit_result(name, source, action), expected)


def test_ts_ambiguous_names():
    print("\n═══ TS: a name that is both a type and a value is the value's; `type User` is the type ═══")

    zod = (
        "import { z } from 'zod';\n\n"
        "export const User = z.object({ name: z.string() });\n\n"
        "/** The user type. */\n"
        "export type User = z.infer<typeof User>;\n"
    )
    _exact("zod pattern: list_symbols lists the type under its keyword",
           _read_result("amb.ts", zod, lambda a: a.list_symbols()), "constant User (line 3)\ntype type User (line 6)")
    _exact("zod pattern: read_symbol of the name is the value (reported)",
           _read_result("amb.ts", zod, lambda a: a.read_symbol("User")),
           "export const User = z.object({ name: z.string() });")
    _exact("zod pattern: delete_symbol of the name deletes the value (reported)",
           _edit_result("amb.ts", zod, lambda a: a.delete_symbol("User")),
           "import { z } from 'zod';\n\n/** The user type. */\nexport type User = z.infer<typeof User>;\n")
    _exact("zod pattern in .tsx: replace_function of `type User`",
           _edit_result("amb.tsx", zod, lambda a: a.replace_function("type User", "export type User = {};")),
           zod.replace("z.infer<typeof User>", "{}"))

    props = "export interface Props {\n  a: number;\n}\nexport const Props = (p: Props) => p.a;\n"
    _exact("interface and function: read_symbol of the name is the function",
           _read_result("amb.ts", props, lambda a: a.read_symbol("Props")), "export const Props = (p: Props) => p.a;")
    _exact("three declarations: the name is the value",
           _read_result("amb.ts", "const U = 1;\ntype U = number;\ninterface U {}\n", lambda a: a.read_symbol("U")),
           "const U = 1;")
    _exact("declare const and type: the name is the value",
           _read_result("amb.ts", "declare const X: number;\ntype X = string;\n", lambda a: a.read_symbol("X")),
           "declare const X: number;")

    # Overload signatures are part of their implementation; merged
    # interfaces and getter/setter pairs are the first; a same-named local
    # in another scope is no declaration of the scope.
    _exact("function overloads: the implementation with its signatures",
           _read_result("amb.ts", "export function f(a: string): string;\nexport function f(a: any) { return a; }\n",
                        lambda a: a.read_symbol("f")),
           "export function f(a: string): string;\nexport function f(a: any) { return a; }")
    _exact("merged interfaces: the first",
           _read_result("amb.ts", "interface A { x: number }\ninterface A { y: number }\n",
                        lambda a: a.read_symbol("A")),
           "interface A { x: number }")
    _exact("getter and setter: the first",
           _read_result("amb.ts", "class A {\n  get x() { return 1; }\n  set x(v) {}\n}\n",
                        lambda a: a.read_symbol("A.x")),
           "get x() { return 1; }")
    _exact("a local of the same name in a function body",
           _read_result("amb.ts", "type User = number;\nfunction g() {\n  const User = 1;\n}\n",
                        lambda a: a.read_symbol("User")),
           "type User = number;")


def test_ts_kind_tool_followups():
    print("\n═══ TS enums, type aliases, abstract methods and bare arrow parameters ═══")

    enum = "export enum E {\n  A,\n  B,\n}\n"
    enum_refusal = (
        "REFUSED: 'E' is an enum, not a class or interface, so add_method and add_field "
        "cannot add to it; rewrite it with replace_function"
    )
    _exact("add_field on a TS enum is refused (reported)",
           _edit_result("k.ts", enum, lambda a: a.add_field("E", "C,")), enum_refusal)
    _exact("add_method on a TS enum is refused (reported)",
           _edit_result("k.ts", enum, lambda a: a.add_method("E", "C,")), enum_refusal)
    _exact("add_method on a TS type alias is refused",
           _edit_result("k.ts", "type T = { a: number };\n", lambda a: a.add_method("T", "m(): void;")),
           "REFUSED: 'T' is a type alias, not a class or interface, so add_method and "
           "add_field cannot add to it; rewrite it with replace_function")
    _exact("read_symbol signature on a type alias is refused",
           _read_result("k.ts", "type T = number;\n", lambda a: a.read_symbol("T", "signature")),
           "REFUSED: 'T' is a type alias, which has no signature (depth='signature' is for "
           "functions and class headers); read it with depth='full'")

    abstract = "abstract class A {\n  abstract m(): void;\n}\n"
    for label, sig in [("without", "abstract m(x: number): void"),
                       ("with", "  abstract m(x: number): void;")]:
        _exact(f"replace_signature on an abstract method, new signature {label} `;`",
               _edit_result("k.ts", abstract, lambda a: a.replace_signature("A.m", sig)),
               "abstract class A {\n  abstract m(x: number): void;\n}\n")
    _exact("replace_signature on an abstract method written without `;`",
           _edit_result("k.ts", "abstract class A {\n  abstract m(): void\n  n() {}\n}\n",
                        lambda a: a.replace_signature("A.m", "abstract m(x: number): void")),
           "abstract class A {\n  abstract m(x: number): void\n  n() {}\n}\n")
    _exact("replace_signature on a Java interface method",
           _edit_result("K.java", "interface A {\n    void m();\n}\n",
                        lambda a: a.replace_signature("A.m", "void m(int x);")),
           "interface A {\n    void m(int x);\n}\n")
    _exact("list_symbols: an overloaded abstract method is listed once",
           _read_result("k.ts",
                        "export abstract class A {\n  abstract m(): void;\n  n() {}\n  abstract m(x: number): void;\n}\n",
                        lambda a: a.list_symbols()),
           "class A (line 1)\n  method A.m (line 2)\n  method A.n (line 3)")

    bare = "const f = x => {\n  return x;\n};\n"
    # (label, file name, source, edit, expected file text)
    cases = [
        ("add_parameter at the end (reported)", "k.js", bare,
         lambda a: a.add_parameter("f", "y"), "const f = (x, y) => {\n  return x;\n};\n"),
        ("add_parameter at the start of an async arrow", "k.js",
         "const f = async x => {\n  return x;\n};\n",
         lambda a: a.add_parameter("f", "y", "start"), "const f = async (y, x) => {\n  return x;\n};\n"),
        ("add_parameter to an expression-bodied TS arrow", "k.ts", "export const f = x => x * 2;\n",
         lambda a: a.add_parameter("f", "y: number"), "export const f = (x, y: number) => x * 2;\n"),
        ("add_parameter to an arrow in an object literal", "k.js",
         "const app = {\n  handler: req => {\n    return req;\n  },\n};\n",
         lambda a: a.add_parameter("app.handler", "res"),
         "const app = {\n  handler: (req, res) => {\n    return req;\n  },\n};\n"),
        ("remove_parameter leaves () (reported)", "k.js", bare,
         lambda a: a.remove_parameter("f", "x"), "const f = () => {\n  return x;\n};\n"),
        ("remove_parameter with another name is refused", "k.js", bare,
         lambda a: a.remove_parameter("f", "z"), "REFUSED: Parameter 'z' not found in 'f'"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"bare arrow parameter: {label}", _edit_result(name, source, action), expected)


def test_yaml_explicit_keys():
    print("\n═══ YAML: an explicit key with no value (`? a`) ═══")

    # (label, source, edit, expected file text)
    cases = [
        ("replace_value adds a `:` line (reported)", "? a\nb: 1\n",
         lambda a: a.replace_value("a", "3"), "? a\n: 3\nb: 1\n"),
        ("nested, in the `?`'s column", "top:\n  ? a\n  b: 1\n",
         lambda a: a.replace_value("top.a", "3"), "top:\n  ? a\n  : 3\n  b: 1\n"),
        ("a comment after the key stays on its line", "? a # c\nb: 1\n",
         lambda a: a.replace_value("a", "3"), "? a # c\n: 3\nb: 1\n"),
        ("a block sequence goes below the `:`", "? a\nb: 1\n",
         lambda a: a.replace_value("a", "- x\n- y"), "? a\n:\n  - x\n  - y\nb: 1\n"),
        ("a block scalar header stays after the `:`", "? a\nb: 1\n",
         lambda a: a.replace_value("a", "|\n  text\n  more"), "? a\n: |\n  text\n  more\nb: 1\n"),
        ("the last key of the file", "b: 1\n? a",
         lambda a: a.replace_value("a", "3"), "b: 1\n? a\n: 3"),
    ]
    for label, source, action, expected in cases:
        _exact(f"explicit key: {label}", _edit_result("x.yaml", source, action), expected)
    _exact("explicit key: crlf",
           _edit_result("x.yaml", "? a\nb: 1\n", lambda a: a.replace_value("a", "3"), "\r\n"),
           "? a\r\n: 3\r\nb: 1\r\n")

    # The key keeps its name: it can be read and replaced again.
    path = _write_temp("x.yaml", "? a\nb: 1\n")
    try:
        Applier(path).replace_value("a", "3")
        back = Applier(path).read_symbol("a")
        Applier(path).replace_value("a", "4")
        again = read_file(path)
    except ApplierError as e:
        back = again = f"REFUSED: {e}"
    os.remove(path)
    _exact("explicit key: read back after the edit", back, "3")
    _exact("explicit key: replaced again", again, "? a\n: 4\nb: 1\n")


# ──────────────────────────────────────────────
# Symbols that share a line with other code; C++ templates; sibling spacing
# ──────────────────────────────────────────────


def _refused(label: str, result: str, reason: str):
    """check() that an _edit_result was refused for `reason` and left the
    file as it was."""
    check(f"{label}: refused", result, reason)
    check(f"{label}: file unchanged",
          "[FILE CHANGED]" if result.endswith("[FILE CHANGED]") else "<unchanged>", "<unchanged>")


def test_symbols_sharing_a_line():
    print("\n═══ whole-symbol edits on a symbol that shares its line ═══")

    # An edit never changes code outside its target. A symbol that shares a
    # line with other code is cut by bytes, with one space left between its
    # neighbours; the `;` or `,` that ends it, and a comment after it at the
    # end of the line, go with it.
    # (label, file name, source, target, expected file text)
    deletes = [
        ("js method (reported)", "k.js", "class A { a() {} b() {} }\n", "A.a", "class A { b() {} }\n"),
        ("js last method", "k.js", "class A { a() {} b() {} }\n", "A.b", "class A { a() {} }\n"),
        ("js first of two functions", "k.js", "function a() {} function b() {}\n", "a", "function b() {}\n"),
        ("js second of two functions", "k.js", "function a() {} function b() {}\n", "b", "function a() {}\n"),
        ("js indented members", "k.js", "class A {\n  a() {} b() {}\n}\n", "A.a", "class A {\n  b() {}\n}\n"),
        ("js multi-line function before another", "k.js",
         "function a() {\n  return 1;\n} function b() {}\n", "a", "function b() {}\n"),
        ("js function after a multi-line one", "k.js",
         "function a() {\n  return 1;\n} function b() {}\n", "b", "function a() {\n  return 1;\n}\n"),
        ("js comment at the end of the line goes too", "k.js",
         "function a() {} function b() {} // b\n", "b", "function a() {}\n"),
        ("js comment before the next symbol stays", "k.js",
         "function a() {} /* x */ function b() {}\n", "a", "/* x */ function b() {}\n"),
        ("js closure in an object literal, with its key and comma", "k.js",
         "const app = { handler: () => {}, other: 1 };\n", "app.handler", "const app = { other: 1 };\n"),
        ("js leading comment goes with the line's first symbol", "k.js",
         "// A.\nfunction a() {} function b() {}\n", "a", "function b() {}\n"),
        ("js the comment above is not the second symbol's", "k.js",
         "// A.\nfunction a() {} function b() {}\n", "b", "// A.\nfunction a() {}\n"),
        ("ts method", "k.ts", "class A { a(): void {} b(): void {} }\n", "A.b", "class A { a(): void {} }\n"),
        ("java method", "K.java", "class A { void a() {} void b() {} }\n", "A.a", "class A { void b() {} }\n"),
        ("cpp method", "k.cpp", "class A { void a() {} void b() {} };\n", "A.b", "class A { void a() {} };\n"),
        ("cpp class, with its `;`", "k.cpp", "class A {}; class B {};\n", "A", "class B {};\n"),
        ("cpp second class", "k.cpp", "class A {}; class B {};\n", "B", "class A {};\n"),
        ("ruby method", "k.rb", "class A; def a; end; def b; end; end\n", "A.a", "class A; def b; end; end\n"),
        ("ruby last method", "k.rb", "class A; def a; end; def b; end; end\n", "A.b", "class A; def a; end; end\n"),
        ("go function", "k.go", "package main\n\nfunc a() {}; func b() {}\n", "a", "package main\n\nfunc b() {}\n"),
        ("go last function takes the `;` before it", "k.go",
         "package main\n\nfunc a() {}; func b() {}\n", "b", "package main\n\nfunc a() {}\n"),
        ("go type, with its keyword", "k.go",
         "package main\n\ntype A struct{}; type B struct{}\n", "A", "package main\n\ntype B struct{}\n"),
        ("python statement", "k.py", "x = 1; y = 2\n", "x", "y = 2\n"),
        ("python last statement takes the `;` before it", "k.py", "x = 1; y = 2\n", "y", "x = 1\n"),
        ("python class attribute", "k.py", "class A: x = 1; y = 2\n", "A.x", "class A: y = 2\n"),
    ]
    for label, name, source, target, expected in deletes:
        _exact(f"delete_symbol sharing a line ({label})",
               _edit_result(name, source, lambda a: a.delete_symbol(target)), expected)
    _exact("delete_symbol sharing a line (crlf)",
           _edit_result("k.js", "class A { a() {} b() {} }\n", lambda a: a.delete_symbol("A.a"), "\r\n"),
           "class A { b() {} }\r\n")
    # A symbol on lines of its own is still deleted line by line.
    _exact("delete_symbol on lines of its own",
           _edit_result("k.js", "function a() {}\nfunction b() {}\n", lambda a: a.delete_symbol("a")),
           "function b() {}\n")
    # The only statement of a Python class body leaves the class without a
    # body, which the save-time check refuses.
    _refused("delete_symbol of a class's only statement on its line",
             _edit_result("k.py", "class A: x = 1\n", lambda a: a.delete_symbol("A.x")),
             "the result would have a syntax error")

    # replace_function replaces only what read_symbol shows; the content's
    # lines after the first keep their indentation relative to it.
    # (label, file name, source, target, content, expected file text)
    replaces = [
        ("js second function", "k.js", "function a() {} function b() {}\n", "b",
         "function b() { return 2; }\n", "function a() {} function b() { return 2; }\n"),
        ("js first function", "k.js", "function a() {} function b() {}\n", "a",
         "function a() { return 1; }", "function a() { return 1; } function b() {}\n"),
        ("js method", "k.js", "class A { a() {} b() {} }\n", "A.a", "a() { return 1; }",
         "class A { a() { return 1; } b() {} }\n"),
        ("js multi-line content", "k.js", "class A {\n  a() {} b() {}\n}\n", "A.a",
         "a() {\n  return 1;\n}", "class A {\n  a() {\n    return 1;\n  } b() {}\n}\n"),
        ("python statement", "k.py", "x = 1; y = 2\n", "y", "y = 3", "x = 1; y = 3\n"),
        ("python class attribute", "k.py", "class A: x = 1\n", "A.x", "x = 2", "class A: x = 2\n"),
        ("ruby method", "k.rb", "class A; def a; end; def b; end; end\n", "A.b", "def b; 2; end",
         "class A; def a; end; def b; 2; end; end\n"),
        ("go function", "k.go", "package main\n\nfunc a() {}; func b() {}\n", "b", "func b() { x() }",
         "package main\n\nfunc a() {}; func b() { x() }\n"),
        ("java method", "K.java", "class A { void a() {} void b() {} }\n", "A.a", "void a() { f(); }",
         "class A { void a() { f(); } void b() {} }\n"),
        ("cpp method", "k.cpp", "class A { void a() {} void b() {} };\n", "A.b", "void b() { f(); }",
         "class A { void a() {} void b() { f(); } };\n"),
    ]
    for label, name, source, target, content, expected in replaces:
        _exact(f"replace_function sharing a line ({label})",
               _edit_result(name, source, lambda a: a.replace_function(target, content)), expected)

    # insert_sibling works where the new lines land right beside the
    # target, and is refused where other code is in between.
    two = "function a() {} function b() {}\n"
    _exact("insert_sibling before the line's first symbol",
           _edit_result("k.js", two, lambda a: a.insert_sibling("a", "function c() {}", "before")),
           "function c() {}\n\nfunction a() {} function b() {}\n")
    _exact("insert_sibling after the line's last symbol",
           _edit_result("k.js", two, lambda a: a.insert_sibling("b", "function c() {}", "after")),
           "function a() {} function b() {}\n\nfunction c() {}\n")
    _exact("insert_sibling after the line's last python statement",
           _edit_result("k.py", "x = 1; y = 2\n", lambda a: a.insert_sibling("y", "z = 3", "after")),
           "x = 1; y = 2\n\nz = 3\n")
    # (label, file name, source, target, position, reason)
    refusals = [
        ("before the line's second symbol", "k.js", two, "b", "before", "shares its first line with other code"),
        ("after the line's first symbol", "k.js", two, "a", "after", "shares its last line with other code"),
        ("before a member after the `{`", "k.js", "class A { a() {} b() {} }\n", "A.a", "before",
         "shares its first line with other code"),
        ("after a member before the `}`", "k.js", "class A { a() {} b() {} }\n", "A.b", "after",
         "shares its last line with other code"),
        ("after a python class's one-line body", "k.py", "class A: x = 1\n", "A.x", "after",
         "shares its line with the start of the code it is part of"),
        ("after a ruby method", "k.rb", "class A; def a; end; def b; end; end\n", "A.a", "after",
         "shares its last line with other code"),
    ]
    for label, name, source, target, position, reason in refusals:
        _refused(f"insert_sibling {label}",
                 _edit_result(name, source, lambda a: a.insert_sibling(target, "z = 1", position)), reason)

    # A leading comment is above the symbol that starts the line.
    _exact("edit_leading_comment add on the line's first symbol",
           _edit_result("k.js", two, lambda a: a.edit_leading_comment("a", "add", "// A.")),
           "// A.\nfunction a() {} function b() {}\n")
    for op, comment in (("add", "// B."), ("replace", "// B."), ("remove", "")):
        _refused(f"edit_leading_comment {op} on the line's second symbol",
                 _edit_result("k.js", "// A.\n" + two, lambda a: a.edit_leading_comment("b", op, comment)),
                 "'b' does not start its line")

    # Signature edits were byte-based already.
    _exact("replace_signature of the line's second symbol",
           _edit_result("k.js", two, lambda a: a.replace_signature("b", "function b(x)")),
           "function a() {} function b(x) {}\n")
    _exact("replace_signature of a one-line python function",
           _edit_result("k.py", "def f(): return 1\n", lambda a: a.replace_signature("f", "def f(x):")),
           "def f(x): return 1\n")
    # add_method rebuilds a one-line class over several lines, and leaves
    # the code after it on the line alone.
    _exact("add_method to a class that shares its line",
           _edit_result("k.js", "class A { a() {} } class B {}\n", lambda a: a.add_method("A", "c() {}")),
           "class A {\n  a() {}\n\n  c() {}\n} class B {}\n")


def test_bodies_sharing_a_line():
    print("\n═══ body tools on a body that shares a line with its signature or braces ═══")

    # replace_function_body rebuilds such a body over several lines, rather
    # than replacing the lines it is on (signature and other code included).
    # (label, file name, source, target, content, expected file text)
    cases = [
        ("js one-line body", "k.js", "function f() { return 1; }\n", "f", "return 2;",
         "function f() {\n  return 2;\n}\n"),
        ("js after another function", "k.js", "function a() {} function f() { return 1; }\n", "f",
         "return 2;", "function a() {} function f() {\n  return 2;\n}\n"),
        ("js first statement on the `{` line", "k.js", "function f() { x();\n  y(); }\n", "f",
         "return 2;", "function f() {\n  return 2;\n}\n"),
        ("js last statement on the `}` line", "k.js", "function f() {\n  x();\n  y(); }\n", "f",
         "return 2;", "function f() {\n  return 2;\n}\n"),
        ("js empty one-line body", "k.js", "function f() {}\n", "f", "return 2;",
         "function f() {\n  return 2;\n}\n"),
        ("python one-line body", "k.py", "def f(): return 1\n", "f", "return 2",
         "def f():\n    return 2\n"),
        ("python method", "k.py", "class A:\n    def f(self): return 1\n", "A.f", "return 2",
         "class A:\n    def f(self):\n        return 2\n"),
        ("python multi-line signature", "k.py", "def f(\n    x,\n): return x\n", "f", "return 2",
         "def f(\n    x,\n):\n    return 2\n"),
        ("ruby one-line method", "k.rb", "def f; 1; end\n", "f", "2", "def f\n  2\nend\n"),
        ("ruby method with parameters", "k.rb", "def f(x) x end\n", "f", "2", "def f(x)\n  2\nend\n"),
        ("go", "k.go", "package main\n\nfunc f() { return }\n", "f", "x()",
         "package main\n\nfunc f() {\n\tx()\n}\n"),
        ("java", "K.java", "class A {\n    void a() { return; }\n}\n", "A.a", "x();",
         "class A {\n    void a() {\n        x();\n    }\n}\n"),
        ("c", "k.c", "int f(void) { return 1; }\n", "f", "return 2;", "int f(void) {\n  return 2;\n}\n"),
    ]
    for label, name, source, target, content, expected in cases:
        _exact(f"replace_function_body sharing a line ({label})",
               _edit_result(name, source, lambda a: a.replace_function_body(target, content)), expected)
    _exact("replace_function_body sharing a line (crlf)",
           _edit_result("k.js", "function f() { return 1; }\n",
                        lambda a: a.replace_function_body("f", "return 2;"), "\r\n"),
           "function f() {\r\n  return 2;\r\n}\r\n")
    # A body on lines of its own is still replaced line by line, comments
    # after the `{` on its line kept.
    _exact("replace_function_body keeps a comment after the `{`",
           _edit_result("k.js", "function f() { // keep\n  x();\n}\n",
                        lambda a: a.replace_function_body("f", "return 2;")),
           "function f() { // keep\n  return 2;\n}\n")

    # A Ruby endless method has an expression, not a body.
    for label, action in (
        ("replace_function_body", lambda a: a.replace_function_body("f", "2")),
        ("insert_in_body", lambda a: a.insert_in_body("f", "x = 1", at="top")),
    ):
        _refused(f"{label} on a ruby endless method",
                 _edit_result("k.rb", "def f = 1\n", action), "'f' is an endless method")

    # The snippet tools search the body only, not code before it on its line.
    _refused("replace_in_body does not match code before the body on its line",
             _edit_result("k.rb", "x = 1; def f; y; end\n",
                          lambda a: a.replace_in_body("f", "x = 1", "x = 2")),
             "Snippet not found in body of 'f'")
    _exact("replace_in_body in a one-line python body",
           _edit_result("k.py", "def f(): return 1\n", lambda a: a.replace_in_body("f", "1", "2")),
           "def f(): return 2\n")
    # insert_in_body refuses a body that shares a line, also after a
    # signature over several lines, and before a Ruby `end`.
    for label, name, source, at in (
        ("python body after a multi-line signature", "k.py", "def f(\n    x,\n): return x\n", "top"),
        ("ruby body before the `end`", "k.rb", "def f\n  x; end\n", "bottom"),
    ):
        _refused(f"insert_in_body at={at}: {label}",
                 _edit_result(name, source, lambda a: a.insert_in_body("f", "y = 1", at=at)),
                 "shares a line with its signature or braces")
    # replace_docstring has no line of its own for a new docstring there.
    _refused("replace_docstring into a one-line python body",
             _edit_result("k.py", "def f(): return 1\n", lambda a: a.replace_docstring("f", '"""Doc."""')),
             "shares a line with its signature")
    _exact("replace_docstring of a one-line python body's docstring",
           _edit_result("k.py", 'def f(): """Old."""\n', lambda a: a.replace_docstring("f", '"""New."""')),
           'def f(): """New."""\n')


_CPP_TEMPLATES = """// Max of two.
template <typename T>
T maxOf(T a, T b) {
    return a > b ? a : b;
}

template <typename T>
class Box {
public:
    T get() { return v; }
    template <typename U>
    U as() { return U(v); }
private:
    T v;
};

int plain() { return 1; }
"""


def test_cpp_templates():
    print("\n═══ C++ templates: the `template <...>` header is part of the symbol ═══")

    src = _CPP_TEMPLATES
    read = lambda action, text=src: _read_result("t.cpp", text, action)
    listing = ("function maxOf (line 2)\nclass Box (line 7)\n  method Box.get (line 10)\n"
               "  method Box.as (line 11)\n  field Box.v (line 14)\nfunction plain (line 17)")
    _exact("list_symbols lists template functions, classes and member templates (reported)",
           read(lambda a: a.list_symbols()), listing)
    _exact("read_symbol of a template function starts at its header (reported)",
           read(lambda a: a.read_symbol("maxOf")),
           "template <typename T>\nT maxOf(T a, T b) {\n    return a > b ? a : b;\n}")
    _exact("read_symbol of a template class",
           read(lambda a: a.read_symbol("Box")),
           src[src.index("template <typename T>\nclass"):src.index("\n\nint plain")])
    _exact("read_symbol of a member template",
           read(lambda a: a.read_symbol("Box.as")),
           "template <typename U>\n    U as() { return U(v); }")
    _exact("read_symbol signature of a template function",
           read(lambda a: a.read_symbol("maxOf", "signature")),
           "template <typename T>\nT maxOf(T a, T b)")
    _exact("read_symbol interface of a template class",
           read(lambda a: a.read_symbol("Box", "interface")),
           "template <typename T>\nclass Box {\npublic:\n    T get() ...\n    template <typename U>\n"
           "    U as() ...\nprivate:\n    T v;\n};")
    _exact("find_references in a template function",
           read(lambda a: a.find_references("maxOf")), "line 3: T maxOf(T a, T b) {")

    after_max = src[src.index("template <typename T>\nclass"):]
    # (label, edit, expected file text)
    cases = [
        ("delete_symbol takes the header and the comment above it (reported)",
         lambda a: a.delete_symbol("maxOf"), after_max),
        ("delete_symbol keeps the comment when asked",
         lambda a: a.delete_symbol("maxOf", include_leading_comments=False), "// Max of two.\n\n" + after_max),
        ("delete_symbol of a template class takes its `;`",
         lambda a: a.delete_symbol("Box"),
         src[: src.index("template <typename T>\nclass")] + "int plain() { return 1; }\n"),
        ("delete_symbol of a member template",
         lambda a: a.delete_symbol("Box.as"), src.replace("    template <typename U>\n    U as() { return U(v); }\n", "")),
        ("insert_sibling before goes above the header and its comment (reported)",
         lambda a: a.insert_sibling("maxOf", "int z() { return 0; }", "before"),
         "int z() { return 0; }\n\n" + src),
        ("insert_sibling after goes after the template class's `;`",
         lambda a: a.insert_sibling("Box", "int z() { return 0; }", "after"),
         src.replace("};\n\nint plain", "};\n\nint z() { return 0; }\n\nint plain")),
        ("insert_sibling before a member template",
         lambda a: a.insert_sibling("Box.as", "int n() { return 0; }", "before"),
         src.replace("\n    template <typename U>", "\n\n    int n() { return 0; }\n\n    template <typename U>")),
        ("edit_leading_comment add goes above the header",
         lambda a: a.edit_leading_comment("Box", "add", "// A box."),
         src.replace("template <typename T>\nclass", "// A box.\ntemplate <typename T>\nclass")),
        ("edit_leading_comment replace: the comment above the header is the symbol's",
         lambda a: a.edit_leading_comment("maxOf", "replace", "// Larger of two."),
         src.replace("// Max of two.", "// Larger of two.")),
        ("edit_leading_comment remove",
         lambda a: a.edit_leading_comment("maxOf", "remove"), src.replace("// Max of two.\n", "")),
        ("replace_function replaces the header too",
         lambda a: a.replace_function("maxOf", "template <class T>\nT maxOf(T a, T b) {\n    return b < a ? a : b;\n}"),
         src.replace("template <typename T>\nT maxOf(T a, T b) {\n    return a > b ? a : b;\n}",
                     "template <class T>\nT maxOf(T a, T b) {\n    return b < a ? a : b;\n}")),
        ("replace_signature keeps the header",
         lambda a: a.replace_signature("maxOf", "T maxOf(T a, T b, T c)"),
         src.replace("T maxOf(T a, T b) {", "T maxOf(T a, T b, T c) {")),
        ("replace_signature starting with `template` replaces it",
         lambda a: a.replace_signature("maxOf", "template <typename T, typename U>\nT maxOf(T a, U b)"),
         src.replace("template <typename T>\nT maxOf(T a, T b) {", "template <typename T, typename U>\nT maxOf(T a, U b) {")),
        ("replace_signature of a member template",
         lambda a: a.replace_signature("Box.as", "template <typename U>\nU as(int n)"),
         src.replace("U as() {", "U as(int n) {")),
    ]
    for label, action, expected in cases:
        _exact(f"cpp template: {label}", _edit_result("t.cpp", src, action), expected)
    _exact("cpp template: delete_symbol (crlf)",
           _edit_result("t.cpp", src, lambda a: a.delete_symbol("maxOf"), "\r\n"),
           after_max.replace("\n", "\r\n"))
    _exact("cpp template: list_symbols (crlf)",
           _read_result("t.cpp", src.replace("\n", "\r\n"), lambda a: a.list_symbols()), listing)

    # A header on the function's own line.
    one = "template <typename T> T id(T x) { return x; }\nint q() { return 0; }\n"
    _exact("cpp template header on the function's line: list_symbols",
           read(lambda a: a.list_symbols(), one), "function id (line 1)\nfunction q (line 2)")
    _exact("cpp template header on the function's line: read_symbol",
           read(lambda a: a.read_symbol("id"), one), "template <typename T> T id(T x) { return x; }")
    _exact("cpp template header on the function's line: delete_symbol",
           _edit_result("t.cpp", one, lambda a: a.delete_symbol("id")), "int q() { return 0; }\n")
    _exact("cpp template header on the function's line: replace_signature",
           _edit_result("t.cpp", one, lambda a: a.replace_signature("id", "T id(T x, T y)")),
           one.replace("T id(T x)", "T id(T x, T y)"))

    # An explicit specialization (`template <>`) is listed under the name it
    # specializes.
    spec = "template <>\nint id<int>(int x) { return 1; }\n\nint q() { return 0; }\n"
    _exact("cpp explicit specialization: list_symbols",
           read(lambda a: a.list_symbols(), spec), "function id (line 1)\nfunction q (line 4)")
    _exact("cpp explicit specialization: read_symbol",
           read(lambda a: a.read_symbol("id"), spec), "template <>\nint id<int>(int x) { return 1; }")
    _exact("cpp explicit specialization: delete_symbol",
           _edit_result("t.cpp", spec, lambda a: a.delete_symbol("id")), "int q() { return 0; }\n")

    # Out-of-line member definitions are top-level functions under their
    # qualified names (a template's without its arguments), with or without
    # a template header; their own names alone find them too.
    plain_out = "struct A { int f(); };\n\nint A::f() { return 1; }\n"
    _exact("cpp out-of-line definition: list_symbols",
           read(lambda a: a.list_symbols(), plain_out), "struct A (line 1)\n  method A.f (line 1)\nfunction A::f (line 3)")
    out = ("template <typename T>\nT Box<T>::get() {\n    return v;\n}\n\n"
           "template <class T> template <class U> U Box<T>::as() { return U(v); }\n")
    _exact("cpp out-of-line template definitions: list_symbols",
           read(lambda a: a.list_symbols(), out), "function Box::get (line 1)\nfunction Box::as (line 6)")
    _exact("cpp out-of-line template definition: read_symbol by its qualified name",
           read(lambda a: a.read_symbol("Box::get"), out), "template <typename T>\nT Box<T>::get() {\n    return v;\n}")
    _exact("cpp out-of-line template definition: read_symbol",
           read(lambda a: a.read_symbol("get"), out), "template <typename T>\nT Box<T>::get() {\n    return v;\n}")
    _exact("cpp nested template headers: read_symbol",
           read(lambda a: a.read_symbol("as"), out), out.split("\n\n")[1].rstrip("\n"))
    _exact("cpp out-of-line template definition: delete_symbol",
           _edit_result("t.cpp", out, lambda a: a.delete_symbol("get")), out.split("\n\n")[1])

    # A template struct is listed as a struct is, with its fields and
    # methods.
    _exact("cpp template struct: list_symbols",
           read(lambda a: a.list_symbols(), "template <typename T>\nstruct Pair {\n    T a;\n    T first() { return a; }\n};\n"),
           "struct Pair (line 1)\n  field Pair.a (line 3)\n  method Pair.first (line 4)")
    _exact("cpp template struct: delete_symbol",
           _edit_result("t.cpp", "int x;\n\ntemplate <typename T>\nstruct Pair {\n    T a;\n};\n",
                        lambda a: a.delete_symbol("Pair")),
           "int x;\n")


def test_sibling_spacing():
    print("\n═══ insert_sibling: blank lines around the new code ═══")

    # PEP 8 in Python (two blank lines around a top-level def or class, one
    # between methods), one blank line elsewhere, on both sides of the new
    # code; the next symbol's leading comment, decorators and `export` are
    # part of it. A target that opens or closes its body or file gets no
    # blank line on that side.
    g = "def g():\n    pass"
    # (label, file name, source, target, content, position, expected file text)
    cases = [
        ("py after a top-level def (reported)", "s.py", "def f():\n    pass\n\n\ndef h():\n    pass\n", "f", g, "after",
         "def f():\n    pass\n\n\ndef g():\n    pass\n\n\ndef h():\n    pass\n"),
        ("py after, the next symbol's comment right below (reported)", "s.py",
         "def f():\n    pass\n# Doc for h\ndef h():\n    pass\n", "f", g, "after",
         "def f():\n    pass\n\n\ndef g():\n    pass\n\n\n# Doc for h\ndef h():\n    pass\n"),
        ("py after, the next symbol's decorator right below", "s.py",
         "def f():\n    pass\n@dec\ndef h():\n    pass\n", "f", g, "after",
         "def f():\n    pass\n\n\ndef g():\n    pass\n\n\n@dec\ndef h():\n    pass\n"),
        ("py after the last symbol of the file", "s.py", "def f():\n    pass\n", "f", g, "after",
         "def f():\n    pass\n\n\ndef g():\n    pass\n"),
        ("py after a method", "s.py",
         "class A:\n    def f(self):\n        pass\n\n    def h(self):\n        pass\n", "A.f",
         "def g(self):\n    pass", "after",
         "class A:\n    def f(self):\n        pass\n\n    def g(self):\n        pass\n\n    def h(self):\n        pass\n"),
        ("py after a class's last method", "s.py",
         "class A:\n    def f(self):\n        pass\n\n\ndef top():\n    pass\n", "A.f",
         "def g(self):\n    pass", "after",
         "class A:\n    def f(self):\n        pass\n\n    def g(self):\n        pass\n\n\ndef top():\n    pass\n"),
        ("py a constant after a class", "s.py", "class A:\n    pass\n\n\nclass B:\n    pass\n", "A", "X = 1", "after",
         "class A:\n    pass\n\n\nX = 1\n\n\nclass B:\n    pass\n"),
        ("py a constant between constants", "s.py", "X = 1\nY = 2\n", "X", "Z = 3", "after",
         "X = 1\nZ = 3\nY = 2\n"),
        ("py before, below imports", "s.py", "import os\n\n\ndef f():\n    pass\n", "f", g, "before",
         "import os\n\n\ndef g():\n    pass\n\n\ndef f():\n    pass\n"),
        ("py before the first symbol of the file", "s.py", "def f():\n    pass\n", "f", "X = 1", "before",
         "X = 1\n\n\ndef f():\n    pass\n"),
        ("py before, below a statement with a comment at its end", "s.py",
         "x = 1  # note\n\ndef f():\n    pass\n", "f", g, "before",
         "x = 1  # note\n\n\ndef g():\n    pass\n\n\ndef f():\n    pass\n"),
        ("py before, below a comment of its own: its blank lines stay", "s.py",
         "# Section\n\ndef f():\n    pass\n", "f", g, "before",
         "# Section\n\ndef g():\n    pass\n\n\ndef f():\n    pass\n"),
        ("py before a class's first method", "s.py", "class A:\n    def f(self):\n        pass\n", "A.f",
         "def g(self):\n    pass", "before",
         "class A:\n    def g(self):\n        pass\n\n    def f(self):\n        pass\n"),
        ("js after", "s.js", "function f() {}\nfunction h() {}\n", "f", "function g() {}", "after",
         "function f() {}\n\nfunction g() {}\n\nfunction h() {}\n"),
        ("js after, the next symbol's JSDoc right below", "s.js",
         "function f() {}\n/** H. */\nfunction h() {}\n", "f", "function g() {}", "after",
         "function f() {}\n\nfunction g() {}\n\n/** H. */\nfunction h() {}\n"),
        ("js after, the next symbol's `export`", "s.js",
         "function f() {}\nexport function h() {}\n", "f", "function g() {}", "after",
         "function f() {}\n\nfunction g() {}\n\nexport function h() {}\n"),
        ("js before", "s.js", "function a() {}\nfunction f() {}\n", "f", "function g() {}", "before",
         "function a() {}\n\nfunction g() {}\n\nfunction f() {}\n"),
        ("js after a class's last member", "s.js", "class A {\n  a() {}\n}\n", "A.a", "c() {}", "after",
         "class A {\n  a() {}\n\n  c() {}\n}\n"),
        ("ts after, the next member's decorator right below", "s.ts",
         "class S {\n  a() {}\n  @Get()\n  b() {}\n}\n", "S.a", "c() {}", "after",
         "class S {\n  a() {}\n\n  c() {}\n\n  @Get()\n  b() {}\n}\n"),
        ("go after, the next function's Godoc right below", "s.go",
         "package main\n\nfunc f() {}\n// H does.\nfunc h() {}\n", "f", "func g() {}", "after",
         "package main\n\nfunc f() {}\n\nfunc g() {}\n\n// H does.\nfunc h() {}\n"),
        ("cpp before a method right after an access label", "s.cpp",
         "class A {\npublic:\n    void f() {}\n};\n", "A.f", "void g() {}", "before",
         "class A {\npublic:\n    void g() {}\n\n    void f() {}\n};\n"),
        ("cpp after a method right before an access label", "s.cpp",
         "class A {\npublic:\n    void f() {}\nprivate:\n    int x;\n};\n", "A.f", "void g() {}", "after",
         "class A {\npublic:\n    void f() {}\n\n    void g() {}\nprivate:\n    int x;\n};\n"),
    ]
    for label, name, source, target, content, position, expected in cases:
        _exact(f"insert_sibling spacing ({label})",
               _edit_result(name, source, lambda a: a.insert_sibling(target, content, position)), expected)
    _exact("insert_sibling spacing (py after, crlf)",
           _edit_result("s.py", "def f():\n    pass\n\ndef h():\n    pass\n",
                        lambda a: a.insert_sibling("f", g, "after"), "\r\n"),
           "def f():\n    pass\n\n\ndef g():\n    pass\n\n\ndef h():\n    pass\n".replace("\n", "\r\n"))


# ──────────────────────────────────────────────
# Re-indented string literals; multi-line array and parameter lists
# ──────────────────────────────────────────────


def test_reindent_string_literals():
    print("\n═══ Re-indented content keeps the text of its multi-line string literals ═══")

    # The lines that start inside a multi-line string literal of the content
    # are part of its value and stay as written while the code around them
    # moves. A Python docstring, a Ruby `<<~` heredoc and a Java text block
    # strip their common indentation, so their lines move with the code, all
    # by as many columns, or all stay when one of them cannot move as far.
    py_cls = "class A:\n    def f(self):\n        return 1\n"
    py_added = "class A:\n    def f(self):\n        return 1\n\n"
    js_cls = "class A {\n  f() {\n    return 1;\n  }\n}\n"
    js_added = "class A {\n  f() {\n    return 1;\n  }\n\n"
    # (label, file name, source, edit, expected file text)
    cases = [
        ("py add_method: a SQL string at column 0 (reported)", "r.py", py_cls,
         lambda a: a.add_method("A", 'def g(self):\n    q = """\nSELECT *\nFROM t\n"""\n    return q'),
         py_added + '    def g(self):\n        q = """\nSELECT *\nFROM t\n"""\n        return q\n'),
        ("py add_method: content at the members' indentation is kept as written", "r.py", py_cls,
         lambda a: a.add_method("A", '    def g(self):\n        q = """\nSELECT *\n  FROM t\n"""\n        return q'),
         py_added + '    def g(self):\n        q = """\nSELECT *\n  FROM t\n"""\n        return q\n'),
        ("py add_method: strings with every prefix", "r.py", py_cls,
         lambda a: a.add_method("A", 'def g(self):\n    return (r"""\nr\n""", b\'\'\'\nb\n\'\'\', f"""\n{self}\n""",\n'
                                     '            u"""\nu\n""", Rb"""\nrb\n""")'),
         py_added + '    def g(self):\n        return (r"""\nr\n""", b\'\'\'\nb\n\'\'\', f"""\n{self}\n""",\n'
                    '                u"""\nu\n""", Rb"""\nrb\n""")\n'),
        ("py add_method: a string continued with a backslash", "r.py", py_cls,
         lambda a: a.add_method("A", 'def g(self):\n    return "a \\\nb"'),
         py_added + '    def g(self):\n        return "a \\\nb"\n'),
        ("py add_method: a docstring moves with the code", "r.py", py_cls,
         lambda a: a.add_method("A", 'def g(self):\n    """Doc.\n\n    More.\n    """\n    return 1'),
         py_added + '    def g(self):\n        """Doc.\n\n        More.\n        """\n        return 1\n'),
        ("py add_method: a docstring line indented less than the code moves as far", "r.py",
         "class A:\n    class B:\n        def f(self):\n            return 1\n",
         lambda a: a.add_method("A.B", '    def g(self):\n        """Doc.\n\n  Two columns in.\n        """\n        return 1'),
         "class A:\n    class B:\n        def f(self):\n            return 1\n\n"
         '        def g(self):\n            """Doc.\n\n      Two columns in.\n            """\n            return 1\n'),
        ("py add_method: a docstring that cannot move back as far stays", "r.py", py_cls,
         lambda a: a.add_method("A", '        def g(self):\n            """Doc.\n\n  Two columns in.\n            """\n'
                                     '            return 1'),
         py_added + '    def g(self):\n        """Doc.\n\n  Two columns in.\n            """\n        return 1\n'),
        ("py add_method: a string after the docstring is no docstring", "r.py", py_cls,
         lambda a: a.add_method("A", 'def g(self):\n    """Doc."""\n    """\nNote.\n"""\n    return 1'),
         py_added + '    def g(self):\n        """Doc."""\n        """\nNote.\n"""\n        return 1\n'),
        ("py replace_function_body: a string stays, the docstring moves", "r.py", "def f():\n    return 1\n",
         lambda a: a.replace_function_body("f", '"""Doc.\n\nMore.\n"""\nq = """\nSELECT\n  x\n"""\nreturn q'),
         'def f():\n    """Doc.\n\n    More.\n    """\n    q = """\nSELECT\n  x\n"""\n    return q\n'),
        ("py replace_function_body: content at the body's indentation is kept as written", "r.py",
         "def f():\n    return 1\n",
         lambda a: a.replace_function_body("f", '    """Doc.\n\nMore.\n    """\n    return 1'),
         'def f():\n    """Doc.\n\nMore.\n    """\n    return 1\n'),
        ("py replace_function_body of a one-line body", "r.py", "def f(): return 1\n",
         lambda a: a.replace_function_body("f", 'q = """\nSELECT\n"""\nreturn q'),
         'def f():\n    q = """\nSELECT\n"""\n    return q\n'),
        ("py replace_function of a method", "r.py", py_cls,
         lambda a: a.replace_function("A.f", 'def f(self):\n    return """\nx\n  y\n"""'),
         'class A:\n    def f(self):\n        return """\nx\n  y\n"""\n'),
        ("py insert_in_body top: an f-string", "r.py", "def f(x):\n    return 1\n",
         lambda a: a.insert_in_body("f", 'q = f"""\nSELECT {x}\n"""', at="top"),
         'def f(x):\n    q = f"""\nSELECT {x}\n"""\n    return 1\n'),
        ("py insert_in_body bottom", "r.py", "def f():\n    x = 1\n",
         lambda a: a.insert_in_body("f", 'q = """\n  a\n"""', at="bottom"),
         'def f():\n    x = 1\n    q = """\n  a\n"""\n'),
        ("py insert_sibling after a method", "r.py", py_cls,
         lambda a: a.insert_sibling("A.f", 'def g(self):\n    return """\nx\n"""', "after"),
         py_added + '    def g(self):\n        return """\nx\n"""\n'),
        ("py add_field", "r.py", py_cls,
         lambda a: a.add_field("A", 'Q = """\nSELECT\n"""'),
         'class A:\n    Q = """\nSELECT\n"""\n\n    def f(self):\n        return 1\n'),
        ("js add_method: a template literal (reported)", "r.js", js_cls,
         lambda a: a.add_method("A", "g() {\n  return `\nSELECT\n  x\n`;\n}"),
         js_added + "  g() {\n    return `\nSELECT\n  x\n`;\n  }\n}\n"),
        ("js add_method into a class indented with tabs: no tabs in the literal", "r.js",
         "class A {\n\tf() {\n\t\treturn 1;\n\t}\n}\n",
         lambda a: a.add_method("A", "g() {\n  return `\n  two\n    four\n`;\n}"),
         "class A {\n\tf() {\n\t\treturn 1;\n\t}\n\n\tg() {\n\t\treturn `\n  two\n    four\n`;\n\t}\n}\n"),
        ("js replace_function_body: a string continued with a backslash", "r.js", "function f() {\n  return 1;\n}\n",
         lambda a: a.replace_function_body("f", "return 'a \\\nb';"),
         "function f() {\n  return 'a \\\nb';\n}\n"),
        ("js insert_in_body: a template literal with a substitution", "r.js", "function f(x) {\n  return 1;\n}\n",
         lambda a: a.insert_in_body("f", "const s = `a ${x}\nb`;", at="top"),
         "function f(x) {\n  const s = `a ${x}\nb`;\n  return 1;\n}\n"),
        ("js replace_function of a member that shares its line", "r.js", "class A {\n  a() {} b() {}\n}\n",
         lambda a: a.replace_function("A.b", "b() {\n  return `\nx\n`;\n}"),
         "class A {\n  a() {} b() {\n    return `\nx\n`;\n  }\n}\n"),
        ("ts add_method: a private method", "r.ts", "class A {\n  f(): number {\n    return 1;\n  }\n}\n",
         lambda a: a.add_method("A", "private g(): string {\n  return `\nSELECT\n`;\n}"),
         "class A {\n  f(): number {\n    return 1;\n  }\n\n  private g(): string {\n    return `\nSELECT\n`;\n  }\n}\n"),
        ("rb add_method: heredocs, %q and a quoted string; a <<~ heredoc moves", "r.rb",
         "class A\n  def f\n    1\n  end\nend\n",
         lambda a: a.add_method("A", 'def g\n  a = <<EOS\nplain\nEOS\n  b = <<-EOS\n  dash\n  EOS\n'
                                     '  c = <<~EOS\n    squiggly\n      deeper\n  EOS\n  d = %q(\nq\n)\n  e = "p\nq"\n'
                                     '  [a, b, c, d, e]\nend'),
         "class A\n  def f\n    1\n  end\n\n"
         '  def g\n    a = <<EOS\nplain\nEOS\n    b = <<-EOS\n  dash\n  EOS\n'
         '    c = <<~EOS\n      squiggly\n        deeper\n    EOS\n    d = %q(\nq\n)\n    e = "p\nq"\n'
         "    [a, b, c, d, e]\n  end\nend\n"),
        ("rb insert_in_body: a heredoc's terminator stays at column 0", "r.rb", "def f\n  1\nend\n",
         lambda a: a.insert_in_body("f", "x = <<SQL\nSELECT\nSQL", at="top"),
         "def f\n  x = <<SQL\nSELECT\nSQL\n  1\nend\n"),
        ("rb insert_in_body: a <<~ heredoc that cannot move back as far stays", "r.rb", "def f\n  1\nend\n",
         lambda a: a.insert_in_body("f", "      x = <<~T\n  a\n    b\n      T", at="top"),
         "def f\n  x = <<~T\n  a\n    b\n      T\n  1\nend\n"),
        ("go replace_function_body: a raw string", "r.go", 'package main\n\nfunc f() string {\n\treturn ""\n}\n',
         lambda a: a.replace_function_body("f", "q := `\nSELECT\n\tx\n`\nreturn q"),
         "package main\n\nfunc f() string {\n\tq := `\nSELECT\n\tx\n`\n\treturn q\n}\n"),
        ("go insert_in_body bottom: a raw string", "r.go", "package main\n\nfunc f() {\n\tx := 1\n\t_ = x\n}\n",
         lambda a: a.insert_in_body("f", "s := `\n  a\n`\n_ = s", at="bottom"),
         "package main\n\nfunc f() {\n\tx := 1\n\t_ = x\n\ts := `\n  a\n`\n\t_ = s\n}\n"),
        ("java add_method: a text block moves with the code, column for column", "R.java",
         "class A {\n    class B {\n        int f() {\n            return 1;\n        }\n    }\n}\n",
         lambda a: a.add_method("A.B", '    String g() {\n        return """\n  x\n    y\n        """;\n    }'),
         "class A {\n    class B {\n        int f() {\n            return 1;\n        }\n\n"
         '        String g() {\n            return """\n      x\n        y\n            """;\n        }\n    }\n}\n'),
        ("cpp add_method: a raw string", "r.cpp", "class A {\npublic:\n    int f() { return 1; }\n};\n",
         lambda a: a.add_method("A", 'const char* g() {\n    return R"(\nSELECT\n)";\n}'),
         'class A {\npublic:\n    int f() { return 1; }\n\n    const char* g() {\n        return R"(\nSELECT\n)";\n    }\n};\n'),
        ("c replace_function_body: a string continued with a backslash", "r.c", "int f(void) {\n    return 0;\n}\n",
         lambda a: a.replace_function_body("f", 'puts("a \\\nb");\nreturn 0;'),
         'int f(void) {\n    puts("a \\\nb");\n    return 0;\n}\n'),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"string literal ({label})", _edit_result(name, source, action), expected)
    _exact("string literal (py add_method, crlf)",
           _edit_result("r.py", py_cls, lambda a: a.add_method("A", 'def g(self):\r\n    return """\r\nx\r\n"""'), "\r\n"),
           (py_added + '    def g(self):\n        return """\nx\n"""\n').replace("\n", "\r\n"))

    # A literal with a syntax error in it is re-indented as code.
    path = _write_temp("r.js", "x = 1;\n")
    _exact("_reindent: an unterminated template literal is re-indented as code",
           repr(Applier(path)._reindent(["f(`", "a"], "  ")), repr(["  f(`", "  a"]))
    os.remove(path)


def test_remove_from_array_lines():
    print("\n═══ remove_from_array: multi-line arrays and their comments ═══")

    # An element on a line of its own goes with that line, a comment at its
    # end included; comments on other lines stay, and so does the array's
    # trailing-comma style. Comments are no elements.
    toml = "a = [\n  1,\n  2, # two\n  3,\n]\n"
    py = "a = [\n    1,\n    2,  # two\n    3,\n]\n"
    # (label, file name, source, value to remove, expected file text)
    cases = [
        ("toml: the element's comment goes with it (reported)", "r.toml", toml, "2", "a = [\n  1,\n  3,\n]\n"),
        ("toml: the element after a comment", "r.toml", toml, "3", "a = [\n  1,\n  2, # two\n]\n"),
        ("toml: a comment on its own line above stays", "r.toml", "a = [\n  1,\n  # about two\n  2,\n  3,\n]\n", "2",
         "a = [\n  1,\n  # about two\n  3,\n]\n"),
        ("toml: the first element", "r.toml", toml, "1", "a = [\n  2, # two\n  3,\n]\n"),
        ("toml: the last element, with no trailing comma", "r.toml", "a = [\n  1, # one\n  2\n]\n", "2",
         "a = [\n  1 # one\n]\n"),
        ("toml: the only element", "r.toml", "a = [\n  1,\n]\n", "1", "a = []\n"),
        ("toml: two elements on a line", "r.toml", "a = [\n  1, 2,\n  3,\n]\n", "2", "a = [\n  1,\n  3,\n]\n"),
        ("toml: inline, the middle element", "r.toml", "a = [1, 2, 3]\n", "2", "a = [1, 3]\n"),
        ("toml: inline, the first element", "r.toml", "a = [1, 2, 3]\n", "1", "a = [2, 3]\n"),
        ("toml: inline, the last element before a comment", "r.toml", "a = [1, 2]  # c\n", "2", "a = [1]  # c\n"),
        ("json: the last element takes the comma before it", "r.json", '{\n  "a": [\n    1,\n    2,\n    3\n  ]\n}\n', "3",
         '{\n  "a": [\n    1,\n    2\n  ]\n}\n'),
        ("json: the middle element", "r.json", '{\n  "a": [\n    1,\n    2,\n    3\n  ]\n}\n', "2",
         '{\n  "a": [\n    1,\n    3\n  ]\n}\n'),
        ("yaml flow: the element's comment goes with it", "r.yaml", "a: [\n  1,\n  2, # two\n  3,\n]\n", "2",
         "a: [\n  1,\n  3,\n]\n"),
        ("yaml flow: a comment on its own line above stays", "r.yaml", "a: [\n  1,\n  # about two\n  2\n]\n", "2",
         "a: [\n  1\n  # about two\n]\n"),
        ("yaml flow: inline", "r.yaml", "a: [1, 2, 3]  # c\n", "1", "a: [2, 3]  # c\n"),
        ("yaml block: comments on other lines stay", "r.yaml", "a:\n  - 1\n  # about two\n  - 2 # two\n  # after\n  - 3\n",
         "2", "a:\n  - 1\n  # about two\n  # after\n  - 3\n"),
        ("py: the element's comment goes with it (reported)", "r.py", py, "2", "a = [\n    1,\n    3,\n]\n"),
        ("py: the element after a comment", "r.py", py, "3", "a = [\n    1,\n    2,  # two\n]\n"),
        ("py: a comment on its own line above stays", "r.py", "a = [\n    1,\n    # about two\n    2,\n    3,\n]\n", "2",
         "a = [\n    1,\n    # about two\n    3,\n]\n"),
        ("py: the last element, with no trailing comma", "r.py", "a = [\n    1,  # one\n    2\n]\n", "2",
         "a = [\n    1  # one\n]\n"),
        ("py: the only element", "r.py", "a = [\n    1,\n]\n", "1", "a = []\n"),
        ("py: inline", "r.py", "a = [1, 2, 3]\n", "1", "a = [2, 3]\n"),
    ]
    for label, name, source, value, expected in cases:
        _exact(f"remove_from_array ({label})", _edit_result(name, source, lambda a: a.remove_from_array("a", value)), expected)
    for name, source in (("r.toml", toml), ("r.py", py)):
        _refused(f"remove_from_array ({name}: a comment is no element)",
                 _edit_result(name, source, lambda a: a.remove_from_array("a", "# two")), "not found")
    for name, source, expected in (
        ("r.toml", toml, "a = [\n  1,\n  3,\n]\n"),
        ("r.py", py, "a = [\n    1,\n    3,\n]\n"),
        ("r.yaml", "a:\n  - 1\n  - 2 # two\n  - 3\n", "a:\n  - 1\n  - 3\n"),
    ):
        _exact(f"remove_from_array ({name}, crlf)",
               _edit_result(name, source, lambda a: a.remove_from_array("a", "2"), "\r\n"), expected.replace("\n", "\r\n"))
    _refused("remove_from_array (js is not supported)",
             _edit_result("r.js", "const a = [1, 2];\n", lambda a: a.remove_from_array("a", "2")), "not supported for .js")


def test_parameter_lines():
    print("\n═══ add_parameter / remove_parameter: one parameter per line ═══")

    # A list written one parameter per line gets the new parameter on a line
    # of its own, at the parameters' indentation (aligned ones included),
    # keeping the trailing-comma style; comments are no parameters and stay
    # on their lines. Other lists get it inline, as before.
    py = "def f(\n    a,\n    b,\n):\n    pass\n"
    # (label, file name, source, target, parameter, position, expected file text)
    adds = [
        ("py, a trailing comma (reported)", "p.py", py, "f", "c=1", "end",
         "def f(\n    a,\n    b,\n    c=1,\n):\n    pass\n"),
        ("py, no trailing comma", "p.py", "def f(\n    a,\n    b\n):\n    pass\n", "f", "c=1", "end",
         "def f(\n    a,\n    b,\n    c=1\n):\n    pass\n"),
        ("py, at the start", "p.py", py, "f", "c", "start",
         "def f(\n    c,\n    a,\n    b,\n):\n    pass\n"),
        ("py, aligned with the `)` on the last line", "p.py", "def f(a,\n      b):\n    pass\n", "f", "c=1", "end",
         "def f(a,\n      b,\n      c=1):\n    pass\n"),
        ("py, aligned, at the start", "p.py", "def f(a,\n      b):\n    pass\n", "f", "c", "start",
         "def f(c,\n      a,\n      b):\n    pass\n"),
        ("py method, aligned", "p.py", "class A:\n    def f(self,\n          a):\n        pass\n", "A.f", "c=1", "end",
         "class A:\n    def f(self,\n          a,\n          c=1):\n        pass\n"),
        ("py, comments at the ends of the lines", "p.py", "def f(\n    a,  # first\n    b,  # second\n):\n    pass\n",
         "f", "c=1", "end", "def f(\n    a,  # first\n    b,  # second\n    c=1,\n):\n    pass\n"),
        ("py, a comment after the last parameter, no comma", "p.py",
         "def f(\n    a,  # first\n    b  # second\n):\n    pass\n", "f", "c=1", "end",
         "def f(\n    a,  # first\n    b,  # second\n    c=1\n):\n    pass\n"),
        ("py, a comment on its own line before the `)` stays last", "p.py",
         "def f(\n    a,\n    b,\n    # more later\n):\n    pass\n", "f", "c=1", "end",
         "def f(\n    a,\n    b,\n    c=1,\n    # more later\n):\n    pass\n"),
        ("py, at the start: above the first parameter's comment", "p.py",
         "def f(\n    # the first\n    a,\n    b,\n):\n    pass\n", "f", "c", "start",
         "def f(\n    c,\n    # the first\n    a,\n    b,\n):\n    pass\n"),
        ("py, after `*`", "p.py", "def f(\n    a,\n    *,\n    b,\n):\n    pass\n", "f", "c=1", "end",
         "def f(\n    a,\n    *,\n    b,\n    c=1,\n):\n    pass\n"),
        ("py, after `/`", "p.py", "def f(\n    a,\n    /,\n):\n    pass\n", "f", "c=1", "end",
         "def f(\n    a,\n    /,\n    c=1,\n):\n    pass\n"),
        ("py, after *args", "p.py", "def f(\n    a,\n    *args,\n):\n    pass\n", "f", "b=1", "end",
         "def f(\n    a,\n    *args,\n    b=1,\n):\n    pass\n"),
        ("py, before **kwargs, which stays last", "p.py", "def f(\n    a,\n    **kwargs,\n):\n    pass\n", "f", "*args", "end",
         "def f(\n    a,\n    *args,\n    **kwargs,\n):\n    pass\n"),
        ("py, a parameter over several lines", "p.py", "def f(\n    a,\n    b={\n        'x': 1,\n    },\n):\n    pass\n",
         "f", "c=1", "end", "def f(\n    a,\n    b={\n        'x': 1,\n    },\n    c=1,\n):\n    pass\n"),
        ("py, two parameters on the last line: inline", "p.py", "def f(\n    a, b,\n):\n    pass\n", "f", "c=1", "end",
         "def f(\n    a, b, c=1,\n):\n    pass\n"),
        ("py, inline before a comment", "p.py", "def f(a, b  # note\n):\n    pass\n", "f", "c=1", "end",
         "def f(a, b, c=1  # note\n):\n    pass\n"),
        ("js", "p.js", "function f(\n  a,\n  b\n) {}\n", "f", "c", "end", "function f(\n  a,\n  b,\n  c\n) {}\n"),
        ("ts (reported)", "p.ts", "function f(\n  a: number,\n  b: string,\n): void {}\n", "f", "c: boolean", "end",
         "function f(\n  a: number,\n  b: string,\n  c: boolean,\n): void {}\n"),
        ("ts arrow function", "p.ts", "const f = (\n  a: number,\n  b: number,\n) => a + b;\n", "f", "c: number", "end",
         "const f = (\n  a: number,\n  b: number,\n  c: number,\n) => a + b;\n"),
        ("go", "p.go", "package main\n\nfunc f(\n\ta int,\n\tb int,\n) {\n}\n", "f", "c int", "end",
         "package main\n\nfunc f(\n\ta int,\n\tb int,\n\tc int,\n) {\n}\n"),
        ("go, aligned with the `)` on the last line", "p.go", "package main\n\nfunc f(a int,\n\tb int) {\n}\n", "f", "c int",
         "end", "package main\n\nfunc f(a int,\n\tb int,\n\tc int) {\n}\n"),
        ("java", "P.java", "class A {\n    void f(\n        int a,\n        int b\n    ) {\n    }\n}\n", "A.f", "int c", "end",
         "class A {\n    void f(\n        int a,\n        int b,\n        int c\n    ) {\n    }\n}\n"),
        ("java, at the start", "P.java", "class A {\n    void f(\n        int a,\n        int b\n    ) {\n    }\n}\n", "A.f",
         "int c", "start", "class A {\n    void f(\n        int c,\n        int a,\n        int b\n    ) {\n    }\n}\n"),
        ("c, block comments", "p.c", "void f(\n    int a, /* a */\n    int b  /* b */\n) {\n}\n", "f", "int c", "end",
         "void f(\n    int a, /* a */\n    int b,  /* b */\n    int c\n) {\n}\n"),
        ("cpp, tabs", "p.cpp", "void f(\n\tint a,\n\tint b\n) {\n}\n", "f", "int c", "end",
         "void f(\n\tint a,\n\tint b,\n\tint c\n) {\n}\n"),
        ("rb", "p.rb", "def f(\n  a,\n  b\n)\n  1\nend\n", "f", "c", "end", "def f(\n  a,\n  b,\n  c\n)\n  1\nend\n"),
        ("rb, no parentheses", "p.rb", "def f a,\n      b\n  1\nend\n", "f", "c", "end",
         "def f a,\n      b,\n      c\n  1\nend\n"),
    ]
    for label, name, source, target, parameter, position, expected in adds:
        result = _edit_result(name, source, lambda a: a.add_parameter(target, parameter, position))
        _exact(f"add_parameter ({label})", result, expected)
    _exact("add_parameter (py, crlf)", _edit_result("p.py", py, lambda a: a.add_parameter("f", "c=1"), "\r\n"),
           "def f(\n    a,\n    b,\n    c=1,\n):\n    pass\n".replace("\n", "\r\n"))
    _exact("add_parameter (go, crlf, at the start)",
           _edit_result("p.go", "package main\n\nfunc f(\n\ta int,\n\tb int,\n) {\n}\n",
                        lambda a: a.add_parameter("f", "c int", "start"), "\r\n"),
           "package main\n\nfunc f(\n\tc int,\n\ta int,\n\tb int,\n) {\n}\n".replace("\n", "\r\n"))

    # (label, file name, source, target, parameter name, expected file text)
    removes = [
        ("py, a line of its own", "p.py", "def f(\n    a,\n    b,\n    c,\n):\n    pass\n", "f", "b",
         "def f(\n    a,\n    c,\n):\n    pass\n"),
        ("py, its comment goes, the others stay", "p.py", "def f(\n    a,  # first\n    b,  # second\n    c,\n):\n    pass\n",
         "f", "b", "def f(\n    a,  # first\n    c,\n):\n    pass\n"),
        ("py, the last one takes the comma before it", "p.py", "def f(\n    a,  # first\n    b  # second\n):\n    pass\n",
         "f", "b", "def f(\n    a  # first\n):\n    pass\n"),
        ("py, a comment on its own line above stays", "p.py", "def f(\n    a,\n    # about b\n    b,\n):\n    pass\n",
         "f", "b", "def f(\n    a,\n    # about b\n):\n    pass\n"),
        ("py, **kwargs and its comment", "p.py", "def f(\n    a,  # a\n    **kwargs,  # rest\n):\n    pass\n", "f", "kwargs",
         "def f(\n    a,  # a\n):\n    pass\n"),
        ("py, aligned, the last one", "p.py", "def f(a,\n      b):\n    pass\n", "f", "b", "def f(a):\n    pass\n"),
        ("py, aligned, the first one", "p.py", "def f(self,\n      a,\n      b):\n    pass\n", "f", "self",
         "def f(a,\n      b):\n    pass\n"),
        ("ts, its comment goes", "p.ts", "function f(\n  a: number, // a\n  b: string, // b\n): void {}\n", "f", "b",
         "function f(\n  a: number, // a\n): void {}\n"),
        ("go, the only one", "p.go", "package main\n\nfunc f(\n\ta int,\n) {\n}\n", "f", "a", "package main\n\nfunc f() {\n}\n"),
        ("java, the last one", "P.java", "class A {\n    void f(\n        int a,\n        int b\n    ) {\n    }\n}\n", "A.f", "b",
         "class A {\n    void f(\n        int a\n    ) {\n    }\n}\n"),
        ("c, block comments", "p.c", "void f(\n    int a, /* a */\n    int b  /* b */\n) {\n}\n", "f", "a",
         "void f(\n    int b  /* b */\n) {\n}\n"),
        ("rb", "p.rb", "def f(\n  a,\n  b\n)\n  1\nend\n", "f", "b", "def f(\n  a\n)\n  1\nend\n"),
        ("rb, no parentheses", "p.rb", "def f a, b\n  1\nend\n", "f", "a", "def f b\n  1\nend\n"),
    ]
    for label, name, source, target, parameter, expected in removes:
        _exact(f"remove_parameter ({label})",
               _edit_result(name, source, lambda a: a.remove_parameter(target, parameter)), expected)
    _exact("remove_parameter (py, crlf)",
           _edit_result("p.py", "def f(\n    a,  # a\n    b,  # b\n):\n    pass\n",
                        lambda a: a.remove_parameter("f", "b"), "\r\n"),
           "def f(\n    a,  # a\n):\n    pass\n".replace("\n", "\r\n"))


def test_interface_as_written():
    print("\n═══ read_symbol depth=interface: members end as written; C/C++ classes end with `;` ═══")

    # The `;` or `,` that the grammar leaves outside a member (TS and JS
    # fields, TS interface members, enum members) is shown with it, and a
    # C/C++ class, struct, union or enum ends with its `};`.
    # (label, file name, source, target, expected interface)
    cases = [
        ("ts class fields keep their `;` (reported)", "i.ts",
         "class A {\n  name: string;\n  age = 3;\n  get(): string {\n    return this.name;\n  }\n}\n", "A",
         "class A {\n  name: string;\n  age = 3;\n  get(): string ...\n}"),
        ("ts field written without `;`", "i.ts",
         "class A {\n  x = 1\n  y: number;\n}\n", "A", "class A {\n  x = 1\n  y: number;\n}"),
        ("ts interface members keep their `;` or `,`", "i.ts",
         "interface I {\n  a: string;\n  b(): void,\n  c?: number\n}\n", "I",
         "interface I {\n  a: string;\n  b(): void,\n  c?: number\n}"),
        ("ts index signature, abstract method and overload", "i.ts",
         "abstract class K {\n  [k: string]: any;\n  abstract m(): void;\n  f(a: string): void;\n"
         "  f(a: any) {}\n}\n", "K",
         "abstract class K {\n  [k: string]: any;\n  abstract m(): void;\n  f(a: string): void;\n"
         "  f(a: any) ...\n}"),
        ("ts enum members keep their commas", "i.ts",
         "enum E {\n  A = 1,\n  B,\n}\n", "E", "enum E {\n  A = 1,\n  B,\n}"),
        ("ts one-line enum", "i.ts", "enum E { A, B }\n", "E", "enum E {\n  A,\n  B\n}"),
        ("js class fields keep their `;`", "i.js",
         "class A {\n  name = 'x';\n  #p = 2;\n  static s;\n  get() {\n    return 1;\n  }\n}\n", "A",
         "class A {\n  name = 'x';\n  #p = 2;\n  static s;\n  get() ...\n}"),
        ("js `;` after a method is not shown", "i.js",
         "class A {\n  get() {};\n}\n", "A", "class A {\n  get() ...\n}"),
        ("java fields", "I.java",
         'class A {\n    int x;\n    private String s = "a";\n    int get() {\n        return x;\n    }\n}\n', "A",
         'class A {\n    int x;\n    private String s = "a";\n    int get() ...\n}'),
        ("java enum constants keep their `,` and `;`", "I.java",
         "enum E {\n    A,\n    B;\n\n    void m() {}\n}\n", "E", "enum E {\n    A,\n    B;\n    void m() ...\n}"),
        ("java enum without a `;`", "I.java", "enum F { X, Y }\n", "F", "enum F {\n    X,\n    Y\n}"),
        ("cpp class ends with `};` (reported)", "i.cpp",
         "class A {\npublic:\n    int x;\n    int get() { return x; }\n    void set(int v);\n};\n", "A",
         "class A {\npublic:\n    int x;\n    int get() ...\n    void set(int v);\n};"),
        ("cpp template class ends with `};`", "i.cpp", _CPP_TEMPLATES, "Box",
         "template <typename T>\nclass Box {\npublic:\n    T get() ...\n    template <typename U>\n"
         "    U as() ...\nprivate:\n    T v;\n};"),
        ("cpp nested class", "i.cpp", "class A {\n    class B {\n        int y;\n    };\n};\n", "A.B",
         "class B {\n    int y;\n};"),
        ("cpp enum", "i.cpp", "enum E { X, Y };\n", "E", "enum E {\n  X,\n  Y\n};"),
        ("c struct", "i.c", "struct S {\n    int a;\n};\n", "S", "struct S {\n    int a;\n};"),
        ("go struct fields", "i.go",
         "package main\n\ntype A struct {\n\tx int\n\ty string\n}\n\nfunc (a A) M() int { return a.x }\n", "A",
         "type A struct {\n\tx int\n\ty string\n}\n\nfunc (a A) M() int ..."),
        ("python statements after a `;`", "i.py", "class A:\n    x = 1; y = 2\n", "A",
         "class A:\n    x = 1;\n    y = 2"),
    ]
    for label, name, source, target, expected in cases:
        _exact(f"read_symbol depth=interface ({label})",
               _read_result(name, source, lambda a: a.read_symbol(target, depth="interface")),
               expected)

    # read_symbol of a C/C++ class, struct, union or enum ends with its `;`,
    # as a template class's does.
    # (label, file name, source, target, expected text)
    reads = [
        ("cpp class (reported)", "r.cpp", "class A {\npublic:\n    int x;\n};\n\nint f() { return 1; }\n", "A",
         "class A {\npublic:\n    int x;\n};"),
        ("cpp union", "r.cpp", "struct S { int a; };\nunion U { int a; };\n", "U", "union U { int a; };"),
        ("cpp enum class", "r.cpp", "enum class E { X };\n", "E", "enum class E { X };"),
        ("cpp forward declaration", "r.cpp", "class C;\n", "C", "class C;"),
        ("cpp nested class", "r.cpp", "class A {\n    class B {\n        int y;\n    };\n};\n", "A.B",
         "class B {\n        int y;\n    };"),
        ("cpp class in a namespace", "r.cpp", "namespace n {\nclass A {};\n}\n", "n.A", "class A {};"),
        ("cpp class with its `;` on the next line", "r.cpp", "class D {\n}\n;\n", "D", "class D {\n}\n;"),
        ("c struct", "r.c", "struct S {\n    int a;\n};\n", "S", "struct S {\n    int a;\n};"),
    ]
    for label, name, source, target, expected in reads:
        _exact(f"read_symbol of a {label} ends with its `;`",
               _read_result(name, source, lambda a: a.read_symbol(target)), expected)

    # The whole-symbol edits take the `;` too, so replace_function's content
    # ends with `};`, as read_symbol shows it.
    cls = "class A {\npublic:\n    int x;\n};\n\nint f() { return 1; }\n"
    pair = "class A {}; class B {};\n"
    nested = "class A {\n    class B {\n        int y;\n    };\n    int x;\n};\n"
    split = "int a;\n\nclass D {\n}\n;\n"
    # (label, file name, source, edit, expected file text)
    edits = [
        ("replace_function with read_symbol's text leaves a cpp class as it was", "e.cpp", cls,
         lambda a: a.replace_function("A", a.read_symbol("A")), cls),
        ("... a cpp class that shares its line", "e.cpp", pair,
         lambda a: a.replace_function("A", a.read_symbol("A")), pair),
        ("replace_function on a nested cpp class takes its `;`", "e.cpp", nested,
         lambda a: a.replace_function("A.B", "class B {\n    int z;\n};"), nested.replace("int y", "int z")),
        ("... a cpp template class", "e.cpp", _CPP_TEMPLATES,
         lambda a: a.replace_function("Box", a.read_symbol("Box")), _CPP_TEMPLATES),
        ("... a c struct", "e.c", "struct S {\n    int a;\n};\n",
         lambda a: a.replace_function("S", a.read_symbol("S")), "struct S {\n    int a;\n};\n"),
        ("replace_function on a cpp class sharing its line takes its `;` (reported)", "e.cpp", pair,
         lambda a: a.replace_function("A", "class C {};"), "class C {}; class B {};\n"),
        ("replace_function on the last cpp class of a line", "e.cpp", pair,
         lambda a: a.replace_function("B", "class C { int x; };"), "class A {}; class C { int x; };\n"),
        ("delete_symbol of the first cpp class of a line", "e.cpp", pair,
         lambda a: a.delete_symbol("A"), "class B {};\n"),
        ("delete_symbol of the last cpp class of a line keeps the `;` before it", "e.cpp", pair,
         lambda a: a.delete_symbol("B"), "class A {};\n"),
        ("delete_symbol of a cpp class", "e.cpp", cls, lambda a: a.delete_symbol("A"), "int f() { return 1; }\n"),
        ("insert_sibling after a cpp class", "e.cpp", cls,
         lambda a: a.insert_sibling("A", "int g;", "after"),
         "class A {\npublic:\n    int x;\n};\n\nint g;\n\nint f() { return 1; }\n"),
        ("insert_sibling before a cpp class", "e.cpp", cls,
         lambda a: a.insert_sibling("A", "int g;", "before"),
         "int g;\n\nclass A {\npublic:\n    int x;\n};\n\nint f() { return 1; }\n"),
        ("replace_function on a cpp class with its `;` on the next line", "e.cpp", split,
         lambda a: a.replace_function("D", "class D {\n    int x;\n};"), "int a;\n\nclass D {\n    int x;\n};\n"),
        ("delete_symbol of a cpp class with its `;` on the next line", "e.cpp", split,
         lambda a: a.delete_symbol("D"), "int a;\n"),
        ("insert_sibling after a cpp class with its `;` on the next line", "e.cpp", split,
         lambda a: a.insert_sibling("D", "int g;", "after"), "int a;\n\nclass D {\n}\n;\n\nint g;\n"),
    ]
    for label, name, source, edit, expected in edits:
        _exact(label, _edit_result(name, source, edit), expected)
    _exact("replace_function on a cpp class sharing its line (crlf)",
           _edit_result("e.cpp", pair, lambda a: a.replace_function("B", "class C {\n    int x;\n};"), "\r\n"),
           "class A {}; class C {\r\n    int x;\r\n};\r\n")


def test_depth_refusals():
    print("\n═══ read_symbol depth=signature/interface on symbols that are not functions or classes ═══")

    def refusal(target, kind, depth):
        if depth == "signature":
            return (f"REFUSED: '{target}' is {kind}, which has no signature (depth='signature' is "
                    "for functions and class headers); read it with depth='full'")
        return (f"REFUSED: '{target}' is {kind}, which has no interface (depth='interface' is "
                "for classes and functions); read it with depth='full'")

    # (label, file name, source, target, what the message calls it)
    cases = [
        ("ts const (reported)", "k.ts", "const X = 1;\n", "X", "a constant"),
        ("ts let", "k.ts", "let y = 2;\n", "y", "a variable"),
        ("ts exported const", "k.ts", "export const Z = 3;\n", "Z", "a constant"),
        ("ts declared const", "k.ts", "declare const d: number;\n", "d", "a constant"),
        ("ts type alias", "k.ts", "type T = number;\n", "T", "a type alias"),
        ("js var", "k.js", "var v = 2;\n", "v", "a variable"),
        ("python module constant", "k.py", "X = 1\n", "X", "a variable"),
        ("python annotated variable", "k.py", "Y: int = 2\n", "Y", "a variable"),
        ("python class attribute", "k.py", "class A:\n    z = 3\n", "A.z", "a field"),
        ("ruby constant", "k.rb", "X = 1\n", "X", "a constant"),
        ("ruby class constant", "k.rb", "class A\n  Y = 2\nend\n", "A.Y", "a constant"),
        ("ruby variable", "k.rb", "x = 1\n", "x", "a variable"),
        ("go var", "k.go", "package main\n\nvar v = 1\n", "v", "a variable"),
        ("go const", "k.go", "package main\n\nconst C = 2\n", "C", "a constant"),
        ("go var in a group", "k.go", "package main\n\nvar (\n\tp = 1\n\tq = 2\n)\n", "q", "a variable"),
        ("c forward declaration", "k.c", "struct S;\n", "S", "a forward declaration"),
        ("cpp forward declaration", "k.cpp", "class C;\n", "C", "a forward declaration"),
        ("cpp opaque enum declaration", "k.cpp", "enum class E : int;\n", "E", "a forward declaration"),
    ]
    for label, name, source, target, kind in cases:
        for depth in ("signature", "interface"):
            _exact(f"read_symbol depth={depth} on a {label}",
                   _read_result(name, source, lambda a: a.read_symbol(target, depth)),
                   refusal(target, kind, depth))

    # A Go type without a struct or interface body has no header, but its
    # interface lists its methods.
    gotype = "package main\n\ntype N int\n\nfunc (n N) Double() N { return n * 2 }\n"
    _exact("read_symbol depth=signature on a go type definition",
           _read_result("k.go", gotype, lambda a: a.read_symbol("N", "signature")),
           "REFUSED: 'N' is a type definition, which has no signature (depth='signature' is for "
           "functions and class headers); read it with depth='interface' for its methods, or depth='full'")
    _exact("read_symbol depth=interface on a go type definition shows its methods",
           _read_result("k.go", gotype, lambda a: a.read_symbol("N", "interface")),
           "type N int\n\nfunc (n N) Double() N ...")

    # Classes give their header, also with nothing in their body, and
    # functions without a body their whole declaration.
    # (label, file name, source, target, expected signature)
    headers = [
        ("go struct", "k.go", "package main\n\ntype A struct {\n\tx int\n}\n", "A", "type A struct"),
        ("go generic struct", "k.go", "package main\n\ntype A[T any] struct {\n\tx T\n}\n", "A",
         "type A[T any] struct"),
        ("go interface", "k.go", "package main\n\ntype I interface {\n\tM() int\n}\n", "I", "type I interface"),
        ("go struct in a group", "k.go", "package main\n\ntype (\n\tA struct{ x int }\n\tB int\n)\n", "A",
         "A struct"),
        ("ruby empty class", "k.rb", "class A < B\nend\n", "A", "class A < B"),
        ("ruby one-line module", "k.rb", "module M; end\n", "M", "module M"),
        ("ruby empty method", "k.rb", "def f(a)\nend\n", "f", "def f(a)"),
        ("ts enum", "k.ts", "enum E { A, B }\n", "E", "enum E"),
        ("ts interface", "k.ts", "interface I {\n  a: string;\n}\n", "I", "interface I"),
        ("cpp struct", "k.cpp", "struct S {\n    int a;\n};\n", "S", "struct S"),
        ("cpp defaulted constructor", "k.cpp", "class A {\n    A() = default;\n};\n", "A.A", "A() = default"),
        ("go function without a body", "k.go", "package main\n\nfunc f() int\n", "f", "func f() int"),
    ]
    for label, name, source, target, expected in headers:
        _exact(f"read_symbol depth=signature on a {label}",
               _read_result(name, source, lambda a: a.read_symbol(target, "signature")), expected)
    _exact("read_symbol depth=interface on an empty ruby class",
           _read_result("k.rb", "class A < B\nend\n", lambda a: a.read_symbol("A", "interface")),
           "class A < B\nend")
    _exact("read_symbol depth=interface on a cpp defaulted constructor",
           _read_result("k.cpp", "class A {\n    A() = default;\n};\n", lambda a: a.read_symbol("A.A", "interface")),
           "A() = default")


def test_review_followups():
    print("\n═══ review follow-ups: containers, separators, comments, tabs, headers ═══")

    # A symbol that is the last of a container with no closing token of
    # its own (a Java enum's body declarations, a C #else branch, a Ruby
    # else branch) is edited alone: the container is not part of it.
    enum = ("enum Mode {\n    ON, OFF;\n\n    int a() {\n        return 1;\n    }\n\n"
            "    // Doc.\n    boolean isOn() {\n        return this == ON;\n    }\n}\n")
    _exact("java enum's last method: delete_symbol",
           _edit_result("M.java", enum, lambda a: a.delete_symbol("Mode.isOn")),
           "enum Mode {\n    ON, OFF;\n\n    int a() {\n        return 1;\n    }\n}\n")
    _exact("java enum's last method: replace_function",
           _edit_result("M.java", enum, lambda a: a.replace_function(
               "Mode.isOn", "boolean isOn() {\n    return false;\n}")),
           enum.replace("return this == ON;", "return false;"))
    _exact("java enum's last method: edit_leading_comment",
           _edit_result("M.java", enum, lambda a: a.edit_leading_comment("Mode.isOn", op="replace", comment="// New.")),
           enum.replace("// Doc.", "// New."))
    _exact("java enum's last method: insert_sibling before",
           _edit_result("M.java", enum, lambda a: a.insert_sibling("Mode.isOn", "void z() {}", "before")),
           enum.replace("    // Doc.", "    void z() {}\n\n    // Doc."))
    branches = ("#ifdef X\nint f(void) { return 1; }\n#else\nint g(void)\n{\n    return 2;\n}\n\n"
                "int h(void)\n{\n    return 3;\n}\n#endif\n")
    _exact("c #else branch's last function: delete_symbol",
           _edit_result("b.c", branches, lambda a: a.delete_symbol("h")),
           "#ifdef X\nint f(void) { return 1; }\n#else\nint g(void)\n{\n    return 2;\n}\n#endif\n")
    _exact("c #else branch's last function: replace_function",
           _edit_result("b.c", branches, lambda a: a.replace_function("h", "int h(void)\n{\n    return 4;\n}")),
           branches.replace("return 3;", "return 4;"))
    _exact("c #elif branch's last function: delete_symbol",
           _edit_result("b.c", branches.replace("#ifdef X", "#if A").replace("#else", "#elif B"),
                        lambda a: a.delete_symbol("h")),
           "#if A\nint f(void) { return 1; }\n#elif B\nint g(void)\n{\n    return 2;\n}\n#endif\n")
    _exact("cpp #else branch's last method: delete_symbol",
           _edit_result("b.cpp", "class W {\npublic:\n#ifdef X\n    void a() {}\n#else\n    void b() {}\n\n"
                        "    void c() {}\n#endif\n};\n", lambda a: a.delete_symbol("W.c")),
           "class W {\npublic:\n#ifdef X\n    void a() {}\n#else\n    void b() {}\n#endif\n};\n")
    ruby_if = "if x\n  def a\n    1\n  end\nelse\n  def b\n    2\n  end\n\n  def c\n    3\n  end\nend\n"
    _exact("ruby else branch's last method: delete_symbol",
           _edit_result("b.rb", ruby_if, lambda a: a.delete_symbol("c")),
           "if x\n  def a\n    1\n  end\nelse\n  def b\n    2\n  end\nend\n")
    _exact("ruby else branch's last method: replace_function",
           _edit_result("b.rb", ruby_if, lambda a: a.replace_function("c", "def c\n  4\nend")),
           ruby_if.replace("    3\n", "    4\n"))
    _exact("ruby when branch's last method: delete_symbol",
           _edit_result("b.rb", "case x\nwhen 1\n  def a\n    1\n  end\n\n  def b\n    2\n  end\nend\n",
                        lambda a: a.delete_symbol("b")),
           "case x\nwhen 1\n  def a\n    1\n  end\nend\n")
    _exact("ruby unless branch's last method: delete_symbol",
           _edit_result("b.rb", "unless defined?(G)\n  def g1\n    7\n  end\n\n  def g2\n    8\n  end\nend\n",
                        lambda a: a.delete_symbol("g2")),
           "unless defined?(G)\n  def g1\n    7\n  end\nend\n")

    # The `;` that JS/TS parse as an empty statement after a declaration
    # is its separator, as an anonymous `;` is.
    semi = "function f() {\n  return 1;\n};\nfunction g() {\n  return 2;\n}\n"
    _exact("js declaration followed by `;`: delete_symbol",
           _edit_result("s.js", semi, lambda a: a.delete_symbol("f")), "function g() {\n  return 2;\n}\n")
    _exact("js declaration followed by `;`: insert_sibling after",
           _edit_result("s.js", semi, lambda a: a.insert_sibling("f", "function h() {}", "after")),
           "function f() {\n  return 1;\n};\n\nfunction h() {}\n\nfunction g() {\n  return 2;\n}\n")
    legacy = "class Legacy {\n  run() {}\n};\n\nfunction g() {}\n"
    _exact("js class followed by `;`: replace_function keeps the `;`",
           _edit_result("s.js", legacy, lambda a: a.replace_function("Legacy", "class Legacy {\n  run() { return 1; }\n}")),
           legacy.replace("run() {}", "run() { return 1; }"))
    _exact("js class followed by `;`: replace_function content with the `;`",
           _edit_result("s.js", legacy, lambda a: a.replace_function("Legacy", "class Legacy {\n  run() { return 1; }\n};")),
           legacy.replace("run() {}", "run() { return 1; }"))
    _exact("js closure's trailing comma stays when the content has none",
           _edit_result("s.js", "const app = {\n  handler: (req) => {\n    return req;\n  },\n  other: 1,\n};\n",
                        lambda a: a.replace_function("app.handler", "handler: (req) => {\n  return 2;\n}")),
           "const app = {\n  handler: (req) => {\n    return 2;\n  },\n  other: 1,\n};\n")
    _exact("ts exported class followed by `;`: delete_symbol",
           _edit_result("s.ts", "export class A {\n  m(): void {}\n};\n\nexport class B {}\n",
                        lambda a: a.delete_symbol("A")),
           "export class B {}\n")
    inline_semi = [
        ("first class", "class A {}; class B {};\n", "A", "class B {};\n"),
        ("second class", "class A {}; class B {};\n", "B", "class A {};\n"),
        ("first function", "function a() {}; function b() {}\n", "a", "function b() {}\n"),
    ]
    for label, source, target, expected in inline_semi:
        _exact(f"js `;` after a symbol sharing its line goes with it ({label})",
               _edit_result("s.js", source, lambda a: a.delete_symbol(target)), expected)

    # Deleting a symbol that shares its line leaves the spaces that were
    # before it; the last entry of a one-line literal takes the comma
    # before it.
    spacing = [
        ("js last entry of an object", "s.js", "const app = { other: 1, handler: () => {} };\n",
         "app.handler", "const app = { other: 1 };\n"),
        ("go last entry of a composite literal", "s.go",
         'package main\n\nvar cmd = Cmd{Use: "x", RunE: func() error { return nil }}\n',
         "cmd.RunE", 'package main\n\nvar cmd = Cmd{Use: "x"}\n'),
        ("go first entry of a composite literal", "s.go",
         'package main\n\nvar cmd = Cmd{RunE: func() error { return nil }, Use: "x"}\n',
         "cmd.RunE", 'package main\n\nvar cmd = Cmd{Use: "x"}\n'),
        ("python statements spaced their own way", "s.py", "x = 1  ;  y = 2  ;  z = 3\n", "y", "x = 1  ;  z = 3\n"),
    ]
    for label, name, source, target, expected in spacing:
        _exact(f"delete_symbol sharing a line ({label})",
               _edit_result(name, source, lambda a: a.delete_symbol(target)), expected)

    # replace_function on a symbol that code follows on its line refuses
    # content ending with a line comment, which would take that code in.
    three = "function a() {} function b() {} function c() {}\n"
    _refused("replace_function sharing a line, content ending with a // comment",
             _edit_result("s.js", three, lambda a: a.replace_function("b", "function b() { return 2; } // note")),
             "The content ends with a comment, and the code after 'b' on its line would become part of it")
    _refused("replace_function sharing a line, content ending with a # comment",
             _edit_result("s.py", "x = 1; y = 2\n", lambda a: a.replace_function("x", "x = 3  # changed")),
             "The content ends with a comment")
    _exact("replace_function sharing a line, content ending with a block comment",
           _edit_result("s.js", three, lambda a: a.replace_function("b", "function b() { return 2; } /* note */")),
           "function a() {} function b() { return 2; } /* note */ function c() {}\n")
    _exact("replace_function sharing a line, a comment where nothing follows",
           _edit_result("s.py", "x = 1; y = 2\n", lambda a: a.replace_function("y", "y = 3  # changed")),
           "x = 1; y = 3  # changed\n")

    # A comment on the line of the entry before stays when the last entry
    # shares its line with the closing bracket; the only entry with a
    # comment of its own leaves an empty container.
    entries = [
        ("python list", "e.py", "a = [\n    1,  # one\n    2]\n",
         lambda a: a.remove_from_array("a", "2"), "a = [\n    1  # one\n]\n"),
        ("toml array", "e.toml", "a = [\n  1,  # one\n  2]\n",
         lambda a: a.remove_from_array("a", "2"), "a = [\n  1  # one\n]\n"),
        ("json array", "e.json", '{"a": [\n  1, // one\n  2]}\n',
         lambda a: a.remove_from_array("a", "2"), '{"a": [\n  1 // one\n]}\n'),
        ("yaml flow sequence", "e.yaml", "a: [1,  # one\n     2]\n",
         lambda a: a.remove_from_array("a", "2"), "a: [1  # one\n     ]\n"),
        ("python aligned list", "e.py", "a = [1,  # one\n     2,  # two\n     3]\n",
         lambda a: a.remove_from_array("a", "3"), "a = [1,  # one\n     2  # two\n]\n"),
        ("python parameters", "e.py", "def f(\n    a,  # first\n    b):\n    pass\n",
         lambda a: a.remove_parameter("f", "b"), "def f(\n    a  # first\n):\n    pass\n"),
        ("ts parameters", "e.ts", "function f(a: string, // first\n           b: number) {}\n",
         lambda a: a.remove_parameter("f", "b"), "function f(a: string // first\n) {}\n"),
        ("go parameters keep the comma", "e.go", "package main\n\nfunc f(a int, // first\n\tb int) {}\n",
         lambda a: a.remove_parameter("f", "b"), "package main\n\nfunc f(a int, // first\n) {}\n"),
        ("ruby parameters", "e.rb", "def f(a, # a\n      b)\nend\n",
         lambda a: a.remove_parameter("f", "b"), "def f(a # a\n)\nend\n"),
        ("js object key", "e.js", "const d = {a: 1, // one\n  b: 2};\n",
         lambda a: a.delete_key("d.b"), "const d = {a: 1 // one\n};\n"),
        ("no comment: cut as before", "e.py", "a = [\n    1,\n    2]\n",
         lambda a: a.remove_from_array("a", "2"), "a = [\n    1]\n"),
        ("only element with a comment", "e.py", "a = [\n    1,  # one\n]\n",
         lambda a: a.remove_from_array("a", "1"), "a = []\n"),
        ("only toml element with a comment", "e.toml", "a = [\n  1,  # one\n]\n",
         lambda a: a.remove_from_array("a", "1"), "a = []\n"),
        ("only parameter with a comment", "e.py", "def f(\n    a,  # x\n):\n    pass\n",
         lambda a: a.remove_parameter("f", "a"), "def f():\n    pass\n"),
        ("only go parameter with a comment", "e.go", "package main\n\nfunc f(\n\ta int, // x\n) {}\n",
         lambda a: a.remove_parameter("f", "a"), "package main\n\nfunc f() {}\n"),
        ("only element, a comment above stays", "e.py", "a = [\n    # above\n    1,  # one\n]\n",
         lambda a: a.remove_from_array("a", "1"), "a = [\n    # above\n]\n"),
    ]
    for label, name, source, action, expected in entries:
        _exact(f"entry removal keeps other comments ({label})", _edit_result(name, source, action), expected)
    _exact("entry removal keeps other comments (crlf)",
           _edit_result("e.py", "a = [\n    1,  # one\n    2]\n", lambda a: a.remove_from_array("a", "2"), "\r\n"),
           "a = [\r\n    1  # one\r\n]\r\n")
    _exact("ruby heredoc constant: delete_symbol (crlf)",
           _edit_result("h.rb", "X = <<~EOS\n  text\nEOS\n\ndef f\n  1\nend\n", lambda a: a.delete_symbol("X"), "\r\n"),
           "def f\r\n  1\r\nend\r\n")

    # A Java enum's `;` shows in its interface where no constant shows it.
    enum_semis = [
        ("after a trailing comma, on its own line", "enum E {\n    A, B,\n    ;\n    void f() {}\n}\n",
         "enum E {\n    A,\n    B,\n    ;\n    void f() ...\n}"),
        ("after a trailing comma, on its line", "enum E {\n    A, B,;\n    void f() {}\n}\n",
         "enum E {\n    A,\n    B,;\n    void f() ...\n}"),
        ("with no constants", "enum E {\n    ;\n    void f() {}\n}\n", "enum E {\n    ;\n    void f() ...\n}"),
        ("after a comment, once", "enum E {\n    A, B // c\n    ;\n    void f() {}\n}\n",
         "enum E {\n    A,\n    B\n    // c\n    ;\n    void f() ...\n}"),
    ]
    for label, source, expected in enum_semis:
        _exact(f"java enum interface shows the `;` ({label})",
               _read_result("E.java", source, lambda a: a.read_symbol("E", "interface")), expected)

    # In a tab-indented class a docstring moves with the code, tabs and all.
    tabbed = "class A:\n\tdef a(self):\n\t\tpass\n"
    _exact("add_method into a tab-indented class: docstring in line with the code",
           _edit_result("t.py", tabbed, lambda a: a.add_method(
               "A", 'def g(self):\n    """Doc.\n\n    More.\n    """\n    return 1')),
           tabbed + '\n\tdef g(self):\n\t\t"""Doc.\n\n\t\tMore.\n\t\t"""\n\t\treturn 1\n')
    _exact("add_method into a tab-indented class: docstring's own indentation and strings kept",
           _edit_result("t.py", tabbed, lambda a: a.add_method(
               "A", 'def g(self):\n    """Doc.\n\n    Example:\n        x = 1\n    """\n'
                    '    s = """\n  raw\n"""\n    return 1')),
           tabbed + '\n\tdef g(self):\n\t\t"""Doc.\n\n\t\tExample:\n\t\t    x = 1\n\t\t"""\n'
                    '\t\ts = """\n  raw\n"""\n\t\treturn 1\n')

    _exact("add_method into a tab-indented class: a tab inside a string does not stop the tabs",
           _edit_result("t.py", tabbed, lambda a: a.add_method(
               "A", 'def g(self):\n    s = """\n\tkept\n"""\n    return s')),
           tabbed + '\n\tdef g(self):\n\t\ts = """\n\tkept\n"""\n\t\treturn s\n')

    # add_parameter goes on a line of its own only in a list written one
    # parameter per line.
    _exact("add_parameter end on a list with several parameters on a line",
           _edit_result("p.py", "import os\n\n\ndef f(a, b, c,\n      d):\n    pass\n",
                        lambda a: a.add_parameter("f", "e=1", "end")),
           "import os\n\n\ndef f(a, b, c,\n      d, e=1):\n    pass\n")
    _exact("add_parameter start on a list with several parameters on a line",
           _edit_result("p.py", "def f(a, b,\n      c):\n    pass\n",
                        lambda a: a.add_parameter("f", "z", "start")),
           "def f(z, a, b,\n      c):\n    pass\n")

    # A Ruby statement that opens a heredoc ends with its body.
    heredoc = "X = <<~EOS\n  text\nEOS\n\ndef f\n  1\nend\n"
    _exact("ruby heredoc constant: delete_symbol",
           _edit_result("h.rb", heredoc, lambda a: a.delete_symbol("X")), "def f\n  1\nend\n")
    _exact("ruby heredoc constant: replace_function",
           _edit_result("h.rb", heredoc, lambda a: a.replace_function("X", "X = 2")), "X = 2\n\ndef f\n  1\nend\n")
    _exact("ruby heredoc constant: read_symbol",
           _read_result("h.rb", heredoc, lambda a: a.read_symbol("X")), "X = <<~EOS\n  text\nEOS")
    _exact("ruby heredoc constant: insert_sibling after",
           _edit_result("h.rb", heredoc, lambda a: a.insert_sibling("X", "Y = 3", "after")),
           "X = <<~EOS\n  text\nEOS\n\nY = 3\n\ndef f\n  1\nend\n")
    _exact("ruby two heredocs on a line: delete_symbol",
           _edit_result("h.rb", "class A\n  X = [<<~A, <<~B]\n    a\n  A\n    b\n  B\n\n  def f\n    1\n  end\nend\n",
                        lambda a: a.delete_symbol("A.X")),
           "class A\n  def f\n    1\n  end\nend\n")

    # replace_signature takes the signature read_symbol gives a symbol
    # with no body.
    point = "package main\n\ntype Point struct {\n\tX int\n}\n"
    signatures = [
        ("go struct", "g.go", point, "Point", "type Point2 struct", point.replace("Point", "Point2")),
        ("go struct, as read", "g.go", point, "Point", "type Point struct", point),
        ("go struct in a group", "g.go", "package main\n\ntype (\n\tA struct{ x int }\n\tB int\n)\n", "A",
         "C struct", "package main\n\ntype (\n\tC struct{ x int }\n\tB int\n)\n"),
        ("go function without a body", "g.go", "package main\n\nfunc f() int\n", "f", "func f(a int) int",
         "package main\n\nfunc f(a int) int\n"),
        ("cpp defaulted constructor", "g.cpp", "class A {\npublic:\n    A() = default;\n};\n", "A.A",
         "A(int x) = default", "class A {\npublic:\n    A(int x) = default;\n};\n"),
        ("ruby empty class", "g.rb", "class A < B\nend\n", "A", "class A < C", "class A < C\nend\n"),
        ("ruby empty method", "g.rb", "def f(a)\nend\n", "f", "def f(a, b)", "def f(a, b)\nend\n"),
    ]
    for label, name, source, target, signature, expected in signatures:
        _exact(f"replace_signature on a {label}",
               _edit_result(name, source, lambda a: a.replace_signature(target, signature)), expected)
    _refused("replace_signature on a constant",
             _edit_result("g.ts", "const X = 1;\n", lambda a: a.replace_signature("X", "const X = 2")),
             "'X' is a constant, which has no signature to replace")


# ──────────────────────────────────────────────
# read_symbol's text given back; Ruby embedded documents
# ──────────────────────────────────────────────


def _round_trip(name: str, source: str, target: str, newline: str = "\n") -> str:
    """Write tests/<name>, run replace_function(target, read_symbol(target))
    on it and return '<unchanged>' when the file is byte for byte as it was,
    else the new file text or 'REFUSED: <error>'; the file is removed
    afterwards."""
    path = _write_temp(name, source, newline)
    before = _read_bytes(path)
    try:
        Applier(path).replace_function(target, Applier(path).read_symbol(target))
        after = _read_bytes(path)
        result = "<unchanged>" if after == before else after.decode("utf-8")
    except ApplierError as e:
        result = f"REFUSED: {e}"
    os.remove(path)
    return result


def test_read_symbol_round_trips():
    print("\n═══ replace_function(t, read_symbol(t)) leaves the file as it was ═══")

    # read_symbol shows a symbol from its first byte: its first line without
    # the indentation of its line, the later lines with all of theirs. Given
    # back to replace_function (or to add_method and insert_sibling at the
    # same depth), that text goes in as it was read, in every language, at
    # any depth, with LF or CRLF and with tabs or spaces. read_symbol shows
    # the code replace_function replaces: a Go `type`, `var` or `const`, the
    # key of a closure in an object or composite literal, a TS `declare`, a
    # C typedef or declaration around a struct, a Ruby `private`, and the
    # `;` that ends a TS abstract method.
    # (label, file name, source, targets)
    cases = [
        ("py method", "r.py", "class A:\n    def m(self):\n        return 1\n", ["A.m"]),
        ("py nested class and its method", "r.py",
         "class A:\n    class B:\n        def m(self):\n            if self:\n                return 1\n            return 2\n",
         ["A.B.m", "A.B"]),
        ("py decorated method", "r.py",
         "class A:\n    @property\n    @cache(\n        size=1,\n    )\n    def m(self):\n        return 1\n", ["A.m"]),
        ("py class attribute over several lines", "r.py", "class A:\n    X = [\n        1,\n    ]\n", ["A.X"]),
        ("py docstring, string and comment at column 0", "r.py",
         'class A:\n    def m(self):\n        """Doc.\n\n        More.\n        """\n# note\n        return """\nraw\n"""\n',
         ["A.m"]),
        ("py 2-space indentation", "r.py", "class A:\n  def m(self):\n    return 1\n", ["A.m"]),
        ("py tabs", "r.py", "class A:\n\tdef m(self):\n\t\treturn 1\n", ["A.m"]),
        ("js method (reported)", "r.js", "class A {\n  m() {\n    return 1;\n  }\n}\n", ["A.m"]),
        ("js method of an exported class", "r.js", "export class A {\n  m() {\n    return 1;\n  }\n}\n", ["A.m"]),
        ("js tabs", "r.js", "class A {\n\tm() {\n\t\treturn 1;\n\t}\n}\n", ["A.m"]),
        ("js closure in an object literal (reported)", "r.js",
         "const app = {\n  handler: () => {\n    return 1;\n  },\n  other: 1,\n};\n", ["app.handler"]),
        ("js closure with an expression body", "r.js", "const app = {\n  handler: (x) =>\n    x * 2,\n};\n",
         ["app.handler"]),
        ("js method sharing its first line", "r.js", "class A {\n  x = 1; m() {\n    return 1;\n  }\n}\n", ["A.m"]),
        ("ts abstract methods", "r.ts",
         "abstract class A {\n  abstract m(): void;\n  abstract n(\n    a: number,\n  ): void;\n}\n", ["A.m", "A.n"]),
        ("ts abstract methods sharing a line", "r.ts",
         "abstract class A {\n  abstract m(): void; abstract n(): void;\n}\n", ["A.m", "A.n"]),
        ("ts declare (reported)", "r.ts", "declare const d: number;\n", ["d"]),
        ("ts decorated method", "r.ts",
         "class A {\n  @Get()\n  @Auth({\n    role: 'x',\n  })\n  m(): void {\n    return;\n  }\n}\n", ["A.m"]),
        ("java enum method (reported)", "R.java", "enum E {\n    X;\n\n    void m() {\n        return;\n    }\n}\n",
         ["E.m"]),
        ("java annotated method", "R.java",
         'class A {\n    @Override\n    public String toString() {\n        return "A";\n    }\n}\n', ["A.toString"]),
        ("java braces on lines of their own", "R.java",
         "class A\n{\n    void m()\n    {\n        return;\n    }\n}\n", ["A.m"]),
        ("rb method in a class in a module (reported)", "r.rb",
         "module M\n  class A\n    def m\n      1\n    end\n  end\nend\n", ["M.A.m", "M.A"]),
        ("rb rescue and ensure", "r.rb",
         "class A\n  def m\n    work\n  rescue => e\n    log e\n  ensure\n    done\n  end\nend\n", ["A.m"]),
        ("rb heredoc constant", "r.rb", "class A\n  X = <<~EOS\n    text\n  EOS\nend\n", ["A.X"]),
        ("rb private def", "r.rb", "class A\n  private def m\n    1\n  end\nend\n", ["A.m"]),
        ("cpp method (reported)", "r.cpp", "class A {\n  void m() {\n    return;\n  }\n};\n", ["A.m"]),
        ("cpp preprocessor lines at column 0", "r.cpp",
         "class A {\n  void m() {\n#ifdef X\n    a();\n#endif\n  }\n};\n", ["A.m"]),
        ("cpp member template", "r.cpp",
         "class A {\n  template <typename T>\n  T m(T x) {\n    return x;\n  }\n};\n", ["A.m"]),
        ("cpp member class", "r.cpp", "struct A {\n  struct B {\n    int x;\n  };\n};\n", ["A.B"]),
        ("cpp class with access labels in a namespace", "r.cpp",
         "namespace ns {\n  class A {\n  public:\n    A() = default;\n  private:\n    int x;\n  };\n}\n", ["ns.A"]),
        ("cpp constructor with its initializer list at its indentation", "r.cpp",
         "class A {\n  A()\n  : x(1) {\n  }\n  int x;\n};\n", ["A.A"]),
        ("c typedef struct (reported)", "r.c", "typedef struct N {\n    int a;\n} N;\n", ["N"]),
        ("c struct with a declarator (reported)", "r.c", "struct S {\n    int a;\n} s;\n", ["S"]),
        ("c struct in a struct", "r.c", "struct A {\n    struct B {\n        int x;\n    } b;\n};\n", ["A.B"]),
        ("go struct (reported)", "r.go", "package main\n\ntype A struct {\n\tx int\n}\n", ["A"]),
        ("go grouped types", "r.go",
         "package main\n\ntype (\n\tA struct{ x int }\n\tB int\n\tC struct {\n\t\ty int\n\t}\n)\n", ["A", "B", "C"]),
        ("go closure in a composite literal (reported)", "r.go",
         'package main\n\nvar cmd = &Command{\n\tUse: "x",\n\tRunE: func(c *Command) error {\n\t\treturn nil\n\t},\n}\n',
         ["cmd.RunE", "cmd"]),
        ("go closure with a label, one level out as gofmt writes it", "r.go",
         "package main\n\nvar cmd = &Command{\n\tRunE: func() error {\n\tloop:\n\t\tfor {\n\t\t\tbreak loop\n\t\t}\n"
         "\t\treturn nil\n\t},\n}\n", ["cmd.RunE"]),
        ("go method", "r.go", "package main\n\nfunc (a *A) M() {\n\treturn\n}\n", ["A.M"]),
        ("py module variable and class attribute over several lines", "r.py",
         "X = [\n    1,\n]\n\n\nclass A:\n    y: dict = {\n        'a': 1,\n    }\n", ["X", "A.y"]),
        ("js module constant over several lines", "r.js", "const n = {\n  a: 1,\n};\nlet m = 2, k = 3;\n", ["n", "k"]),
        ("js class fields", "r.js", "class A {\n  x = 1;\n  static #y = [\n    1,\n  ];\n  z = 2 // z\n}\n",
         ["A.x", "A.#y", "A.z"]),
        ("ts class fields", "r.ts", "class A {\n  @Input() x: number;\n  private readonly r = {\n    a: 1,\n  };\n}\n",
         ["A.x", "A.r"]),
        ("js function with a comment after it (reported)", "r.js", "function b() {} // old\nfunction c() {}\n", ["b"]),
        ("ts constant with a comment after it", "r.ts", "export const x = 1 // x\n", ["x"]),
        ("rb constant in a module", "r.rb", "module M\n  X = [\n    1,\n  ]\nend\n", ["M.X"]),
        ("c anonymous typedef struct", "r.c", "typedef struct {\n    int x;\n} P;\n", ["P", "P.x"]),
    ]
    for label, name, source, targets in cases:
        for target in targets:
            for newline, ending in (("\n", "lf"), ("\r\n", "crlf")):
                check(f"round trip ({label}, {target}, {ending})",
                      _round_trip(name, source, target, newline), "<unchanged>")

    # What read_symbol shows is what replace_function replaces.
    # (label, file name, source, target, expected read_symbol text)
    reads = [
        ("go struct with its `type`", "r.go", "package main\n\ntype A struct {\n\tx int\n}\n", "A",
         "type A struct {\n\tx int\n}"),
        ("go type in a group, without `type`", "r.go",
         "package main\n\ntype (\n\tA struct{ x int }\n\tB int\n)\n", "A", "A struct{ x int }"),
        ("go var with its `var`", "r.go", "package main\n\nvar x = f(\n\t1,\n)\n", "x", "var x = f(\n\t1,\n)"),
        ("go closure with its key", "r.go",
         "package main\n\nvar cmd = &Command{\n\tRunE: func() error {\n\t\treturn nil\n\t},\n}\n", "cmd.RunE",
         "RunE: func() error {\n\t\treturn nil\n\t}"),
        ("js closure with its key", "r.js", "const app = {\n  handler: () => {\n    return 1;\n  },\n};\n",
         "app.handler", "handler: () => {\n    return 1;\n  }"),
        ("ts declare", "r.ts", "declare const d: number;\n", "d", "declare const d: number;"),
        ("ts abstract method with its `;`", "r.ts", "abstract class A {\n  abstract m(): void;\n}\n", "A.m",
         "abstract m(): void;"),
        ("c typedef struct", "r.c", "typedef struct N {\n    int a;\n} N;\n", "N", "typedef struct N {\n    int a;\n} N;"),
        ("c struct with a declarator", "r.c", "struct S {\n    int a;\n} s;\n", "S", "struct S {\n    int a;\n} s;"),
        ("rb private def", "r.rb", "class A\n  private def m\n    1\n  end\nend\n", "A.m",
         "private def m\n    1\n  end"),
    ]
    for label, name, source, target, expected in reads:
        _exact(f"read_symbol ({label})", _read_result(name, source, lambda a: a.read_symbol(target)), expected)

    # Content in the other two shapes goes in as before: relative (its first
    # line at column 0, the others indented from it) and absolute (every
    # line at its file indentation). Text that is both relative and in
    # read_symbol's shape (every later line deeper than the symbol's
    # indentation, in a file indented less than the content) reads as
    # read_symbol shows it.
    py_m = "class A:\n    def m(self):\n        return 1\n"
    js_m = "class A {\n  m() {\n    return 1;\n  }\n}\n"
    rb_m = "module M\n  class A\n    def m\n      1\n    end\n  end\nend\n"
    js_app = "const app = {\n  handler: (x) =>\n    x * 2,\n};\n"
    # (label, file name, source, target, content, expected file text)
    shapes = [
        ("py relative", "r.py", py_m, "A.m", "def m(self):\n    return 2",
         "class A:\n    def m(self):\n        return 2\n"),
        ("py relative, a block first", "r.py", py_m, "A.m", "def m(self):\n    if self:\n        return 2",
         "class A:\n    def m(self):\n        if self:\n            return 2\n"),
        ("py relative with a decorator", "r.py", py_m, "A.m", "@property\ndef m(self):\n    return 2",
         "class A:\n    @property\n    def m(self):\n        return 2\n"),
        ("py absolute", "r.py", py_m, "A.m", "    def m(self):\n        return 2",
         "class A:\n    def m(self):\n        return 2\n"),
        ("py as read, edited", "r.py", py_m, "A.m", "def m(self):\n        x = 2\n        return x",
         "class A:\n    def m(self):\n        x = 2\n        return x\n"),
        ("py as read, a decorator taken out", "r.py",
         "class A:\n    @property\n    def m(self):\n        return 1\n", "A.m", "def m(self):\n        return 2",
         "class A:\n    def m(self):\n        return 2\n"),
        ("py relative and as read: as read", "r.py", "class A:\n  def m(self):\n    return 1\n", "A.m",
         "def m(self):\n    return 2", "class A:\n  def m(self):\n    return 2\n"),
        ("js relative", "r.js", js_m, "A.m", "m() {\n  return 2;\n}", js_m.replace("1", "2")),
        ("js absolute", "r.js", js_m, "A.m", "  m() {\n    return 2;\n  }", js_m.replace("1", "2")),
        ("js as read, edited", "r.js", js_m, "A.m", "m() {\n    const x = 2;\n    return x;\n  }",
         "class A {\n  m() {\n    const x = 2;\n    return x;\n  }\n}\n"),
        ("js relative, continued at the symbol's indentation", "r.js", js_app, "app.handler",
         "handler: (x) =>\n  x * 3", js_app.replace("2", "3")),
        ("js as read from a deeper symbol", "r.js", js_m, "A.m", "m() {\n      return 2;\n    }",
         js_m.replace("1", "2")),
        ("rb relative", "r.rb", rb_m, "M.A.m", "def m\n  2\nend", rb_m.replace("1", "2")),
        ("rb as read, edited", "r.rb", rb_m, "M.A.m", "def m\n      2\n    end", rb_m.replace("1", "2")),
        ("go closure as read, edited", "r.go",
         "package main\n\nvar cmd = &Command{\n\tRunE: func() error {\n\t\treturn nil\n\t},\n}\n", "cmd.RunE",
         "RunE: func() error {\n\t\treturn errors.New(\"x\")\n\t}",
         "package main\n\nvar cmd = &Command{\n\tRunE: func() error {\n\t\treturn errors.New(\"x\")\n\t},\n}\n"),
        ("ts abstract method sharing its line, as read", "r.ts",
         "abstract class A {\n  abstract m(): void; abstract n(): void;\n}\n", "A.m", "abstract m(): number;",
         "abstract class A {\n  abstract m(): number; abstract n(): void;\n}\n"),
    ]
    for label, name, source, target, content, expected in shapes:
        _exact(f"replace_function shape ({label})",
               _edit_result(name, source, lambda a: a.replace_function(target, content)), expected)

    # read_symbol's text of a symbol copied to another class or place goes
    # in at the new place's indentation as well.
    js_b = "class B {\n  n() {\n    return 0;\n  }\n}\n"
    py_b = "class B:\n    def n(self):\n        return 0\n"
    # (label, file name, source, edit, expected file text)
    copies = [
        ("js add_method, read at the same depth", "r.js", js_b,
         lambda a: a.add_method("B", "m() {\n    return 1;\n  }"),
         "class B {\n  n() {\n    return 0;\n  }\n\n  m() {\n    return 1;\n  }\n}\n"),
        ("js add_method, read at another depth", "r.js", js_b,
         lambda a: a.add_method("B", "m() {\n      return 1;\n    }"),
         "class B {\n  n() {\n    return 0;\n  }\n\n  m() {\n    return 1;\n  }\n}\n"),
        ("py add_method, read at the same depth", "r.py", py_b,
         lambda a: a.add_method("B", "def m(self):\n        return 1"),
         "class B:\n    def n(self):\n        return 0\n\n    def m(self):\n        return 1\n"),
        ("py insert_sibling, read at the same depth", "r.py", py_b,
         lambda a: a.insert_sibling("B.n", "@property\n    def m(self):\n        return 1", "after"),
         "class B:\n    def n(self):\n        return 0\n\n    @property\n    def m(self):\n        return 1\n"),
        ("java add_field, read at the same depth", "R.java", "class B {\n    void n() {\n    }\n}\n",
         lambda a: a.add_field("B", "@Deprecated\n    void m() {\n        return;\n    }"),
         "class B {\n    @Deprecated\n    void m() {\n        return;\n    }\n\n    void n() {\n    }\n}\n"),
        ("py add_top_level, read from a method", "r.py", "x = 1\n",
         lambda a: a.add_top_level("@staticmethod\n    def m():\n        return 1"),
         "x = 1\n\n\n@staticmethod\ndef m():\n    return 1\n"),
        ("rb add_top_level, read from a nested class", "r.rb", "X = 1\n",
         lambda a: a.add_top_level("class B\n    def f\n      1\n    end\n  end"),
         "X = 1\n\nclass B\n  def f\n    1\n  end\nend\n"),
    ]
    for label, name, source, action, expected in copies:
        _exact(f"read_symbol text copied ({label})", _edit_result(name, source, action), expected)


def test_ruby_embedded_documents():
    print("\n═══ Ruby embedded documents (=begin ... =end) stay at column 0 ═══")

    # Ruby reads an embedded document only from a `=begin` at the start of a
    # line to an `=end` at the start of one, so re-indented content keeps
    # their lines as written, like the lines of a multi-line string.
    # tree-sitter-ruby also reads an indented `=begin` as a comment, which
    # Ruby rejects: an edit that would write one is refused, and in the
    # content one is code like any other line.
    cls = "class A\n  def f\n    1\n  end\nend\n"
    # (label, file name, source, edit, expected file text)
    cases = [
        ("add_method (reported)", "e.rb", cls,
         lambda a: a.add_method("A", "def g\n=begin\nx\n=end\n  1\nend"),
         "class A\n  def f\n    1\n  end\n\n  def g\n=begin\nx\n=end\n    1\n  end\nend\n"),
        ("add_method into a class indented with tabs", "e.rb", "class A\n\tdef f\n\t\t1\n\tend\nend\n",
         lambda a: a.add_method("A", "def g\n=begin\n  x\n    y\n=end\n  1\nend"),
         "class A\n\tdef f\n\t\t1\n\tend\n\n\tdef g\n=begin\n  x\n    y\n=end\n\t\t1\n\tend\nend\n"),
        ("add_field", "e.rb", cls, lambda a: a.add_field("A", "=begin\nDoc.\n=end\nX = 1"),
         "class A\n=begin\nDoc.\n=end\n  X = 1\n\n  def f\n    1\n  end\nend\n"),
        ("replace_function", "e.rb", cls,
         lambda a: a.replace_function("A.f", "def f\n=begin\nx\n=end\n  2\nend"),
         "class A\n  def f\n=begin\nx\n=end\n    2\n  end\nend\n"),
        ("replace_function, the document first", "e.rb", cls,
         lambda a: a.replace_function("A.f", "=begin\nDoc.\n=end\ndef f\n  2\nend"),
         "class A\n=begin\nDoc.\n=end\n  def f\n    2\n  end\nend\n"),
        ("replace_function of a method sharing its line", "e.rb", "class A\n  def e; end; def f\n    1\n  end\nend\n",
         lambda a: a.replace_function("A.f", "def f\n=begin\nx\n=end\n  2\nend"),
         "class A\n  def e; end; def f\n=begin\nx\n=end\n    2\n  end\nend\n"),
        ("replace_function_body", "e.rb", cls,
         lambda a: a.replace_function_body("A.f", "=begin\nx\n=end\n2"),
         "class A\n  def f\n=begin\nx\n=end\n    2\n  end\nend\n"),
        ("replace_function_body of a one-line body", "e.rb", "class A\n  def f; 1; end\nend\n",
         lambda a: a.replace_function_body("A.f", "=begin\nx\n=end\n2"),
         "class A\n  def f\n=begin\nx\n=end\n    2\n  end\nend\n"),
        ("insert_in_body at the top", "e.rb", cls,
         lambda a: a.insert_in_body("A.f", "=begin\nx\n=end", at="top"),
         "class A\n  def f\n=begin\nx\n=end\n    1\n  end\nend\n"),
        ("insert_in_body at the bottom", "e.rb", cls,
         lambda a: a.insert_in_body("A.f", "2\n=begin\nx\n=end", at="bottom"),
         "class A\n  def f\n    1\n    2\n=begin\nx\n=end\n  end\nend\n"),
        ("insert_sibling", "e.rb", cls,
         lambda a: a.insert_sibling("A.f", "def g\n=begin\nx\n=end\n  1\nend", "after"),
         "class A\n  def f\n    1\n  end\n\n  def g\n=begin\nx\n=end\n    1\n  end\nend\n"),
        ("edit_leading_comment", "e.rb", cls,
         lambda a: a.edit_leading_comment("A.f", op="add", comment="=begin\nDoc.\n=end"),
         "class A\n=begin\nDoc.\n=end\n  def f\n    1\n  end\nend\n"),
        ("a =begin line in a heredoc is its text", "e.rb", cls,
         lambda a: a.add_method("A", "def g\n  <<~EOS\n  =begin\n  EOS\nend"),
         "class A\n  def f\n    1\n  end\n\n  def g\n    <<~EOS\n    =begin\n    EOS\n  end\nend\n"),
        ("an indented =begin in the content is code", "e.rb", "def f\n  1\nend\n",
         lambda a: a.insert_sibling("f", "  def g\n  =begin\n  x\n  =end\n    1\n  end", "after"),
         "def f\n  1\nend\n\ndef g\n=begin\nx\n=end\n  1\nend\n"),
        ("a file with an indented =begin already is not guarded", "e.rb",
         "class A\n  =begin\n  x\n  =end\n  def f\n    1\n  end\nend\n",
         lambda a: a.replace_function_body("A.f", "2"),
         "class A\n  =begin\n  x\n  =end\n  def f\n    2\n  end\nend\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"embedded document ({label})", _edit_result(name, source, action), expected)
    nested = "module M\n  class A\n    def f\n=begin\nx\n=end\n      1\n    end\n  end\nend\n"
    for target in ("M.A.f", "M.A"):
        check(f"embedded document (round trip of {target})", _round_trip("e.rb", nested, target), "<unchanged>")

    # An edit that would write `=begin` anywhere but at the start of a line.
    _refused("embedded document (add_method with an indented =begin)",
             _edit_result("e.rb", cls, lambda a: a.add_method("A", "def g\n  =begin\n  x\n  =end\n  1\nend")),
             "line 7, column 5 (an embedded document's =begin must start its line)")
    _refused("embedded document (insert_in_body with an indented =begin)",
             _edit_result("e.rb", cls, lambda a: a.insert_in_body("A.f", "    =begin\n    x\n    =end\n", before="    1")),
             "line 3, column 5 (an embedded document's =begin must start its line)")


# ──────────────────────────────────────────────
# Symbol discovery: definitions, C/C++/Go/Java kinds, nesting, C++ names
# ──────────────────────────────────────────────


def _depth_text(target: str, kind_or_text: str, depth: str) -> str:
    """What read_symbol(target, depth) gives for depth 'signature' or
    'interface': kind_or_text itself, or for a symbol that is neither a
    function nor a class ('a macro', 'a field', ...) its refusal."""
    if not kind_or_text.startswith("a "):
        return kind_or_text
    if depth == "signature":
        return (f"REFUSED: '{target}' is {kind_or_text}, which has no signature (depth='signature' "
                "is for functions and class headers); read it with depth='full'")
    return (f"REFUSED: '{target}' is {kind_or_text}, which has no interface (depth='interface' "
            "is for classes and functions); read it with depth='full'")


def _listed_targets_resolve(label: str, name: str, source: str):
    """check() that every entry list_symbols lists for source is what its
    name targets: no other entry is listed under that name, read_symbol
    finds it, at the listed line, its other depths read it or refuse it
    for what it is, and replace_function given read_symbol's text leaves
    the file as it was."""
    listed = _read_result(name, source, lambda a: a.list_symbols())

    def found_at(a, target):
        node = a.parser.find_node_by_name(target)
        return "no line" if node is None else str(a._symbol_span(node)[0].start_point[0] + 1)

    seen = set()
    for line in listed.splitlines():
        entry, number = line.rsplit(" (line ", 1)
        number = number.rstrip(")")
        target = " ".join(entry.split()[1:])
        result = _read_result(name, source, lambda a: a.read_symbol(target))
        at = _read_result(name, source, lambda a: found_at(a, target))
        depths = [_read_result(name, source, lambda a: a.read_symbol(target, depth)) for depth in ("signature", "interface")]
        refused = [d for d in depths if d.startswith("REFUSED") and ", which has no " not in d]
        if target in seen:
            result = "FAIL: listed twice"
        elif result.startswith("REFUSED"):
            result = "FAIL: " + result
        elif at != number:
            result = f"FAIL: listed at line {number}, found at {at}"
        elif refused:
            result = "FAIL: " + refused[0]
        else:
            trip = _round_trip(name, source, target)
            result = "PASS" if trip == "<unchanged>" else f"FAIL: round trip: {trip}"
        seen.add(target)
        check(f"{label}: listed '{target}' resolves", result, "PASS")


def test_symbol_discovery():
    print("\n═══ symbol discovery: definitions over declarations, new kinds, nesting, C++ names ═══")

    # Each listed symbol with what read_symbol shows at depth full, at
    # depth signature and interface (one text for both, or a tuple; a kind
    # for a symbol that has neither), and the file delete_symbol leaves.
    # replace_function given read_symbol's text leaves the file as it was.
    # (label, file name, source, list_symbols, [(target, full, short, deleted)])
    cases = [
        # A forward declaration yields to the definition, in either order.
        ("c struct forward declaration (reported)", "k.c",
         "struct S;\n\nstruct S {\n    int a;\n};\n\nint use(struct S *s) { return s->a; }\n",
         "struct S (line 3)\n  field S.a (line 4)\nfunction use (line 7)",
         [("S", "struct S {\n    int a;\n};", ("struct S", "struct S {\n    int a;\n};"),
           "struct S;\n\nint use(struct S *s) { return s->a; }\n"),
          ("S.a", "int a;", "a field", "struct S;\n\nstruct S {\n};\n\nint use(struct S *s) { return s->a; }\n")]),
        ("c struct defined before its forward declaration", "k.c",
         "struct S {\n    int a;\n};\nstruct S;\n",
         "struct S (line 1)\n  field S.a (line 2)",
         [("S", "struct S {\n    int a;\n};", ("struct S", "struct S {\n    int a;\n};"), "struct S;\n")]),
        ("cpp class forward declaration", "k.cpp",
         "class A;\n\nclass A {\npublic:\n    int x;\n};\n",
         "class A (line 3)\n  field A.x (line 5)",
         [("A", "class A {\npublic:\n    int x;\n};", ("class A", "class A {\npublic:\n    int x;\n};"), "class A;\n")]),
        ("cpp union forward declaration", "k.cpp",
         "union U;\nunion U {\n    int i;\n    float f;\n};\n",
         "union U (line 2)\n  field U.i (line 3)\n  field U.f (line 4)",
         [("U", "union U {\n    int i;\n    float f;\n};", ("union U", "union U {\n    int i;\n    float f;\n};"),
           "union U;\n")]),
        ("cpp opaque enum declaration", "k.cpp",
         "enum class E : int;\nenum class E : int {\n    X,\n    Y\n};\n",
         "enum E (line 2)",
         [("E", "enum class E : int {\n    X,\n    Y\n};", ("enum class E : int", "enum class E : int {\n    X,\n    Y\n};"),
           "enum class E : int;\n")]),
        # A prototype yields to the function's definition; alone, it is the
        # function, without a body.
        ("c prototype and definition", "k.c",
         "int f(int);\n\nint f(int x) {\n    return x;\n}\n",
         "function f (line 3)",
         [("f", "int f(int x) {\n    return x;\n}", "int f(int x)", "int f(int);\n")]),
        ("c definition and a later prototype", "k.c",
         "int f(int x) {\n    return x;\n}\n\nint f(int);\n",
         "function f (line 1)",
         [("f", "int f(int x) {\n    return x;\n}", "int f(int x)", "int f(int);\n")]),
        ("c prototypes", "k.h",
         "int f(int);\nint g(void);\n",
         "function f (line 1)\nfunction g (line 2)",
         [("f", "int f(int);", "int f(int)", "int g(void);\n"),
          ("g", "int g(void);", "int g(void)", "int f(int);\n")]),
        ("c extern declaration and definition", "k.c",
         "extern int g;\nint g = 1;\n",
         "variable g (line 2)",
         [("g", "int g = 1;", "a variable", "extern int g;\n")]),
        ("c extern declaration", "k.h",
         "extern int g;\nint h(void);\n",
         "variable g (line 1)\nfunction h (line 2)",
         [("g", "extern int g;", "a variable", "int h(void);\n")]),
        # A typedef of a struct's name is the name's target, the struct
        # `struct Node`'s (its fields are found through the name), and a
        # Java field the name's, the method `A.size()`'s.
        ("c typedef before its struct", "k.c",
         "typedef struct Node Node;\n\nstruct Node {\n    Node *next;\n};\n",
         "type Node (line 1)\nstruct struct Node (line 3)\n  field Node.next (line 4)",
         [("Node", "typedef struct Node Node;",
           ("REFUSED: 'Node' is a type alias, which has no signature (depth='signature' is for functions and "
            "class headers); read it with depth='full', and the struct it names with 'struct Node'",
            "REFUSED: 'Node' is a type alias, which has no interface (depth='interface' is for classes and "
            "functions); read it with depth='full', and the struct it names with 'struct Node'"),
           "struct Node {\n    Node *next;\n};\n"),
          ("struct Node", "struct Node {\n    Node *next;\n};", ("struct Node", "struct Node {\n    Node *next;\n};"),
           "typedef struct Node Node;\n")]),
        ("java field and accessor sharing a name", "K.java",
         "class A {\n    private int size;\n\n    int size() {\n        return size;\n    }\n}\n",
         "class A (line 1)\n  field A.size (line 2)\n  method A.size() (line 4)",
         [("A.size()", "int size() {\n        return size;\n    }", "int size()", "class A {\n    private int size;\n}\n"),
          ("A.size", "private int size;", "a field", "class A {\n    int size() {\n        return size;\n    }\n}\n")]),
        ("cpp methods declared in their class", "k.cpp",
         "class A {\npublic:\n    A();\n    int g();\n    virtual void v() = 0;\n};\n\nint A::g() { return 1; }\n",
         "class A (line 1)\n  method A.A (line 3)\n  method A.g (line 4)\n  method A.v (line 5)\nfunction A::g (line 8)",
         [("A.A", "A();", "A()", "class A {\npublic:\n    int g();\n    virtual void v() = 0;\n};\n\nint A::g() { return 1; }\n"),
          ("A.g", "int g();", "int g()", "class A {\npublic:\n    A();\n    virtual void v() = 0;\n};\n\nint A::g() { return 1; }\n"),
          ("A.v", "virtual void v() = 0;", "virtual void v() = 0",
           "class A {\npublic:\n    A();\n    int g();\n};\n\nint A::g() { return 1; }\n"),
          ("g", "int A::g() { return 1; }", "int A::g()",
           "class A {\npublic:\n    A();\n    int g();\n    virtual void v() = 0;\n};\n")]),
        # TS: overload signatures are one symbol with the implementation
        # after them, and functions declared without one (`declare
        # function` twice) one symbol of their own.
        ("ts overloads and declared functions", "k.ts",
         "function f(a: string): void;\nfunction f(a: any) {\n  return a;\n}\n"
         "declare function g(x: number): void;\ndeclare function g(x: string): void;\n",
         "function f (line 1)\nfunction g (line 5)",
         [("f", "function f(a: string): void;\nfunction f(a: any) {\n  return a;\n}", "function f(a: any)",
           "declare function g(x: number): void;\ndeclare function g(x: string): void;\n"),
          ("g", "declare function g(x: number): void;\ndeclare function g(x: string): void;",
           "declare function g(x: number): void",
           "function f(a: string): void;\nfunction f(a: any) {\n  return a;\n}\n")]),
        ("ts method overloads (listed once, as before)", "k.ts",
         "class K {\n  m(a: string): void;\n  m(a: any) {}\n}\n",
         "class K (line 1)\n  method K.m (line 2)",
         [("K.m", "m(a: string): void;\n  m(a: any) {}", "m(a: any)", "class K {\n}\n")]),

        # Macros, typedefs, globals (reported).
        ("c macro, typedef and global (reported)", "k.c",
         "#define M 1\ntypedef int I;\nint g = 1;\nint f(void) { return g; }\n",
         "macro M (line 1)\ntype I (line 2)\nvariable g (line 3)\nfunction f (line 4)",
         [("M", "#define M 1", "a macro", "typedef int I;\nint g = 1;\nint f(void) { return g; }\n"),
          ("I", "typedef int I;", "a type alias", "#define M 1\nint g = 1;\nint f(void) { return g; }\n"),
          ("g", "int g = 1;", "a variable", "#define M 1\ntypedef int I;\nint f(void) { return g; }\n")]),
        ("c function-like macro over two lines", "k.c",
         "#define F(x) \\\n    ((x) + 1)\nint y;\n",
         "macro F (line 1)\nvariable y (line 3)",
         [("F", "#define F(x) \\\n    ((x) + 1)", "a macro", "int y;\n"),
          ("y", "int y;", "a variable", "#define F(x) \\\n    ((x) + 1)\n")]),
        ("c header with an include guard", "k.h",
         "#ifndef H\n#define H\n\nstruct P {\n    int x;\n};\nint area(struct P p);\n\n#endif\n",
         "macro H (line 2)\nstruct P (line 4)\n  field P.x (line 5)\nfunction area (line 7)",
         [("H", "#define H", "a macro", "#ifndef H\n\nstruct P {\n    int x;\n};\nint area(struct P p);\n\n#endif\n"),
          ("area", "int area(struct P p);", "int area(struct P p)",
           "#ifndef H\n#define H\n\nstruct P {\n    int x;\n};\n\n#endif\n")]),
        ("c typedefs of structs", "k.c",
         "typedef struct N {\n    int v;\n} N;\ntypedef struct {\n    int x;\n} P;\ntypedef int (*cb)(int);\n",
         "struct N (line 1)\n  field N.v (line 2)\ntype P (line 4)\n  field P.x (line 5)\ntype cb (line 7)",
         [("N", "typedef struct N {\n    int v;\n} N;", ("typedef struct N", "typedef struct N {\n    int v;\n} N;"),
           "typedef struct {\n    int x;\n} P;\ntypedef int (*cb)(int);\n"),
          ("P", "typedef struct {\n    int x;\n} P;", ("typedef struct", "typedef struct {\n    int x;\n} P;"),
           "typedef struct N {\n    int v;\n} N;\ntypedef int (*cb)(int);\n"),
          ("P.x", "int x;", "a field",
           "typedef struct N {\n    int v;\n} N;\ntypedef struct {\n} P;\ntypedef int (*cb)(int);\n"),
          ("cb", "typedef int (*cb)(int);", "a type alias",
           "typedef struct N {\n    int v;\n} N;\ntypedef struct {\n    int x;\n} P;\n")]),
        ("cpp aliases, constants and variables", "k.cpp",
         "using U = int;\ntemplate <class T>\nusing V = T;\nconstexpr int N = 3;\nconst int K = 1;\n"
         "const char *name = \"x\";\nstatic int s;\nint (*fp)(int);\n",
         "type U (line 1)\ntype V (line 2)\nconstant N (line 4)\nconstant K (line 5)\nvariable name (line 6)\n"
         "variable s (line 7)\nvariable fp (line 8)",
         [("V", "template <class T>\nusing V = T;", "a type alias",
           "using U = int;\nconstexpr int N = 3;\nconst int K = 1;\nconst char *name = \"x\";\nstatic int s;\nint (*fp)(int);\n"),
          ("N", "constexpr int N = 3;", "a constant",
           "using U = int;\ntemplate <class T>\nusing V = T;\nconst int K = 1;\nconst char *name = \"x\";\nstatic int s;\nint (*fp)(int);\n"),
          ("fp", "int (*fp)(int);", "a variable",
           "using U = int;\ntemplate <class T>\nusing V = T;\nconstexpr int N = 3;\nconst int K = 1;\nconst char *name = \"x\";\nstatic int s;\n")]),
        ("cpp static members and their definitions", "k.cpp",
         "struct A {\n    static int n;\n    static constexpr int N = 3;\n    using T = int;\n};\nint A::n = 0;\n",
         "struct A (line 1)\n  field A.n (line 2)\n  field A.N (line 3)\n  type A.T (line 4)\nvariable A::n (line 6)",
         [("A.n", "static int n;", "a field",
           "struct A {\n    static constexpr int N = 3;\n    using T = int;\n};\nint A::n = 0;\n"),
          ("A.T", "using T = int;", "a type alias",
           "struct A {\n    static int n;\n    static constexpr int N = 3;\n};\nint A::n = 0;\n"),
          ("n", "int A::n = 0;", "a variable",
           "struct A {\n    static int n;\n    static constexpr int N = 3;\n    using T = int;\n};\n")]),
        ("go type aliases, variables and constants", "k.go",
         "package main\n\ntype T = int\n\ntype (\n\tA = int\n\tB struct{}\n)\n\nvar v = 1\n\nconst (\n\tC = 2\n\tD = 3\n)\n\nfunc f() {}\n",
         "type T (line 3)\ntype A (line 6)\nstruct B (line 7)\nvariable v (line 10)\nconstant C (line 13)\n"
         "constant D (line 14)\nfunction f (line 17)",
         [("T", "type T = int", "a type alias",
           "package main\n\ntype (\n\tA = int\n\tB struct{}\n)\n\nvar v = 1\n\nconst (\n\tC = 2\n\tD = 3\n)\n\nfunc f() {}\n"),
          ("A", "A = int", "a type alias",
           "package main\n\ntype T = int\n\ntype (\n\tB struct{}\n)\n\nvar v = 1\n\nconst (\n\tC = 2\n\tD = 3\n)\n\nfunc f() {}\n"),
          ("D", "D = 3", "a constant",
           "package main\n\ntype T = int\n\ntype (\n\tA = int\n\tB struct{}\n)\n\nvar v = 1\n\nconst (\n\tC = 2\n)\n\nfunc f() {}\n")]),
        ("java fields (reported)", "K.java",
         "class A {\n    int x;\n    @Deprecated\n    static final int X = 1;\n\n    void m() {}\n}\n",
         "class A (line 1)\n  field A.x (line 2)\n  field A.X (line 3)\n  method A.m (line 6)",
         [("A.x", "int x;", "a field", "class A {\n    @Deprecated\n    static final int X = 1;\n\n    void m() {}\n}\n"),
          ("A.X", "@Deprecated\n    static final int X = 1;", "a field", "class A {\n    int x;\n\n    void m() {}\n}\n")]),
        ("java interface constants", "K.java",
         "interface I {\n    int K = 3;\n    void i();\n}\n",
         "interface I (line 1)\n  field I.K (line 2)\n  method I.i (line 3)",
         [("I.K", "int K = 3;", "a field", "interface I {\n    void i();\n}\n")]),

        # Nested classes are listed with their members.
        ("cpp nested class (reported)", "k.cpp",
         "class A {\n    class B {\n        int m() { return 1; }\n    };\n};\n",
         "class A (line 1)\n  class A.B (line 2)\n    method A.B.m (line 3)",
         [("A.B", "class B {\n        int m() { return 1; }\n    };",
           ("class B", "class B {\n    int m() ...\n};"), "class A {\n};\n"),
          ("A.B.m", "int m() { return 1; }", "int m()", "class A {\n    class B {\n    };\n};\n")]),
        ("c nested struct", "k.c",
         "struct A {\n    struct B {\n        int x;\n    } b;\n    int y;\n};\n",
         "struct A (line 1)\n  struct A.B (line 2)\n    field A.B.x (line 3)\n  field A.b (line 2)\n  field A.y (line 5)",
         [("A.b", "struct B {\n        int x;\n    } b;", "a field",
           "REFUSED: 'b' is declared together with 'B' in one declaration, so delete_symbol would delete it too. "
           "Give replace_function the declaration without 'b' (read_symbol shows it), or make this edit with your "
           "normal edit tool."),
          ("A.B.x", "int x;", "a field", "struct A {\n    struct B {\n    } b;\n    int y;\n};\n")]),
        ("cpp namespace", "k.cpp",
         "namespace ns {\nint f() { return 1; }\nclass C {};\nint v = 2;\n}\n",
         "namespace ns (line 1)\n  function ns.f (line 2)\n  class ns.C (line 3)\n  variable ns.v (line 4)",
         [("ns.v", "int v = 2;", "a variable", "namespace ns {\nint f() { return 1; }\nclass C {};\n}\n")]),
        ("java nested types", "K.java",
         "class A {\n    class B {\n        int m() { return 1; }\n    }\n    enum E {\n        P;\n        void e() {}\n    }\n"
         "    interface I {\n        void i();\n    }\n    record R(int a) {\n        void r() {}\n    }\n}\n",
         "class A (line 1)\n  class A.B (line 2)\n    method A.B.m (line 3)\n  enum A.E (line 5)\n    method A.E.e (line 7)\n"
         "  interface A.I (line 9)\n    method A.I.i (line 10)\n  record A.R (line 12)\n    method A.R.r (line 13)",
         [("A.E.e", "void e() {}", "void e()",
           "class A {\n    class B {\n        int m() { return 1; }\n    }\n    enum E {\n        P;\n    }\n"
           "    interface I {\n        void i();\n    }\n    record R(int a) {\n        void r() {}\n    }\n}\n")]),
        ("python nested classes", "k.py",
         "class A:\n    class B:\n        def m(self):\n            return 1\n\n    @dataclass\n    class C:\n        x: int\n\n"
         "    def n(self):\n        pass\n",
         "class A (line 1)\n  class A.B (line 2)\n    method A.B.m (line 3)\n  class A.C (line 6)\n    field A.C.x (line 8)\n"
         "  method A.n (line 10)",
         [("A.C", "@dataclass\n    class C:\n        x: int", ("class C:", "@dataclass\nclass C:\n    x: int"),
           "class A:\n    class B:\n        def m(self):\n            return 1\n\n    def n(self):\n        pass\n")]),
        ("ruby nested modules and classes", "k.rb",
         "module M\n  class A\n    def m\n    end\n\n    private def p\n    end\n  end\n\n  module N\n    def self.s; end\n  end\n\n"
         "  def self.f\n  end\nend\n",
         "module M (line 1)\n  class M.A (line 2)\n    method M.A.m (line 3)\n    method M.A.p (line 6)\n"
         "  module M.N (line 10)\n    method M.N.s (line 11)\n  method M.f (line 14)",
         [("M.A.p", "private def p\n    end", "private def p",
           "module M\n  class A\n    def m\n    end\n  end\n\n  module N\n    def self.s; end\n  end\n\n  def self.f\n  end\nend\n")]),
        ("ts namespaces", "k.ts",
         "namespace N {\n  export class C {\n    m() {}\n  }\n  export function f() {}\n  export const h = () => 1;\n}\n"
         "module Q {\n  function g(): void;\n}\n",
         "namespace N (line 1)\n  class N.C (line 2)\n    method N.C.m (line 3)\n  function N.f (line 5)\n  function N.h (line 6)\n"
         "namespace Q (line 8)\n  function Q.g (line 9)",
         [("N.C", "export class C {\n    m() {}\n  }", ("class C", "export class C {\n  m() ...\n}"),
           "namespace N {\n  export function f() {}\n  export const h = () => 1;\n}\nmodule Q {\n  function g(): void;\n}\n"),
          ("N.C.m", "m() {}", "m()",
           "namespace N {\n  export class C {\n  }\n  export function f() {}\n  export const h = () => 1;\n}\nmodule Q {\n  function g(): void;\n}\n"),
          ("Q.g", "function g(): void;", "function g(): void",
           "namespace N {\n  export class C {\n    m() {}\n  }\n  export function f() {}\n  export const h = () => 1;\n}\nmodule Q {\n}\n")]),

        # Destructors and operators, named as written (reported).
        ("cpp destructor and operators (reported)", "k.cpp",
         "class A {\npublic:\n    A() {}\n    ~A() {}\n    bool operator==(const A& o) const { return true; }\n"
         "    int operator()(int x) { return x; }\n    int& operator[](int i);\n    operator bool() const { return true; }\n};\n",
         "class A (line 1)\n  method A.A (line 3)\n  method A.~A (line 4)\n  method A.operator== (line 5)\n"
         "  method A.operator() (line 6)\n  method A.operator[] (line 7)\n  method A.operator bool (line 8)",
         [("A.~A", "~A() {}", "~A()",
           "class A {\npublic:\n    A() {}\n    bool operator==(const A& o) const { return true; }\n"
           "    int operator()(int x) { return x; }\n    int& operator[](int i);\n    operator bool() const { return true; }\n};\n"),
          ("A.operator==", "bool operator==(const A& o) const { return true; }", "bool operator==(const A& o) const",
           "class A {\npublic:\n    A() {}\n    ~A() {}\n"
           "    int operator()(int x) { return x; }\n    int& operator[](int i);\n    operator bool() const { return true; }\n};\n"),
          ("A.operator()", "int operator()(int x) { return x; }", "int operator()(int x)",
           "class A {\npublic:\n    A() {}\n    ~A() {}\n    bool operator==(const A& o) const { return true; }\n"
           "    int& operator[](int i);\n    operator bool() const { return true; }\n};\n"),
          ("A.operator[]", "int& operator[](int i);", "int& operator[](int i)",
           "class A {\npublic:\n    A() {}\n    ~A() {}\n    bool operator==(const A& o) const { return true; }\n"
           "    int operator()(int x) { return x; }\n    operator bool() const { return true; }\n};\n"),
          ("A.operator bool", "operator bool() const { return true; }", "operator bool() const",
           "class A {\npublic:\n    A() {}\n    ~A() {}\n    bool operator==(const A& o) const { return true; }\n"
           "    int operator()(int x) { return x; }\n    int& operator[](int i);\n};\n")]),
        ("cpp destructor and operators defined outside their class", "k.cpp",
         "class A {\npublic:\n    ~A();\n    bool operator == (const A& o) const;\n    operator const char *() const;\n};\n\n"
         "A::~A() {\n}\n\nbool A::operator==(const A& o) const { return true; }\n\nA::operator const char*() const { return 0; }\n",
         "class A (line 1)\n  method A.~A (line 3)\n  method A.operator== (line 4)\n  method A.operator const char* (line 5)\n"
         "function A::~A (line 8)\nfunction A::operator== (line 11)\nfunction A::operator const char* (line 13)",
         [("A.~A", "~A();", "~A()",
           "class A {\npublic:\n    bool operator == (const A& o) const;\n    operator const char *() const;\n};\n\n"
           "A::~A() {\n}\n\nbool A::operator==(const A& o) const { return true; }\n\nA::operator const char*() const { return 0; }\n"),
          ("~A", "A::~A() {\n}", "A::~A()",
           "class A {\npublic:\n    ~A();\n    bool operator == (const A& o) const;\n    operator const char *() const;\n};\n\n"
           "bool A::operator==(const A& o) const { return true; }\n\nA::operator const char*() const { return 0; }\n"),
          ("operator const char*", "A::operator const char*() const { return 0; }", "A::operator const char*() const",
           "class A {\npublic:\n    ~A();\n    bool operator == (const A& o) const;\n    operator const char *() const;\n};\n\n"
           "A::~A() {\n}\n\nbool A::operator==(const A& o) const { return true; }\n")]),
    ]
    for label, name, source, listing, targets in cases:
        _exact(f"{label}: list_symbols", _read_result(name, source, lambda a: a.list_symbols()), listing)
        _listed_targets_resolve(label, name, source)
        for target, full, short, deleted in targets:
            _exact(f"{label}: read_symbol('{target}')",
                   _read_result(name, source, lambda a: a.read_symbol(target)), full)
            for depth, text in zip(("signature", "interface"), short if isinstance(short, tuple) else (short, short)):
                _exact(f"{label}: read_symbol('{target}', '{depth}')",
                       _read_result(name, source, lambda a: a.read_symbol(target, depth)),
                       _depth_text(target, text, depth))
            check(f"{label}: replace_function('{target}', read_symbol) round trip",
                  _round_trip(name, source, target), "<unchanged>")
            check(f"{label}: replace_function('{target}', read_symbol) round trip (crlf)",
                  _round_trip(name, source, target, "\r\n"), "<unchanged>")
            _exact(f"{label}: delete_symbol('{target}')",
                   _edit_result(name, source, lambda a: a.delete_symbol(target)), deleted)

    # A namespace's interface shows its functions' signatures, exported
    # ones too.
    ns = "namespace N {\n  export function f() {\n    return 1;\n  }\n  function g(): void;\n}\n"
    _exact("ts namespace: read_symbol depth=interface",
           _read_result("k.ts", ns, lambda a: a.read_symbol("N", "interface")),
           "namespace N {\n  export function f() ...\n  function g(): void;\n}")

    # A target written with other spacing finds the same operator.
    spaced = "struct P {\n    bool operator == (const P&) const;\n};\n"
    for target in ("P.operator==", "P.operator ==", "P.operator  =="):
        _exact(f"cpp operator target '{target}'",
               _read_result("k.cpp", spaced, lambda a: a.read_symbol(target)), "bool operator == (const P&) const;")

    # A type only referred to (`struct S *p;`) is no declaration of it.
    _exact("c struct only referred to: list_symbols",
           _read_result("k.c", "struct S *p;\n", lambda a: a.list_symbols()), "variable p (line 1)")
    check("c struct only referred to: not a target",
          _read_result("k.c", "struct S *p;\n", lambda a: a.read_symbol("S")), "Target 'S' not found")
    # A function's own variables are no targets; a struct it defines is, as
    # before, with its fields.
    local = "void f() {\n    struct L { int a; };\n    int x = 1;\n    for (int i = 0; i < 2; i++) {}\n}\n"
    for target in ("x", "i"):
        check(f"cpp local '{target}': not a target",
              _read_result("k.cpp", local, lambda a: a.read_symbol(target)), f"Target '{target}' not found")
    _exact("cpp local struct field: a target", _read_result("k.cpp", local, lambda a: a.read_symbol("L.a")), "int a;")
    _exact("cpp template forward declaration: the definition is the target",
           _read_result("k.cpp", "template <class T> class X;\ntemplate <class T> class X {\n    T v;\n};\n",
                        lambda a: a.read_symbol("X")),
           "template <class T> class X {\n    T v;\n};")

    # The other edits on the new kinds.
    # (label, file name, source, edit, expected file text)
    edits = [
        ("insert_sibling after a macro", "k.c", "#define M 1\nint g = 1;\n",
         lambda a: a.insert_sibling("M", "#define N 2", "after"), "#define M 1\n#define N 2\nint g = 1;\n"),
        ("insert_sibling after a macro over two lines", "k.c", "#define F(x) \\\n    ((x) + 1)\nint y;\n",
         lambda a: a.insert_sibling("F", "#define G 2", "after"), "#define F(x) \\\n    ((x) + 1)\n\n#define G 2\n\nint y;\n"),
        ("insert_sibling before a global", "k.c", "#define M 1\nint g = 1;\n",
         lambda a: a.insert_sibling("g", "int h = 2;", "before"), "#define M 1\nint h = 2;\nint g = 1;\n"),
        ("replace_function on a macro", "k.c", "#define M 1\nint g = 1;\n",
         lambda a: a.replace_function("M", "#define M 2"), "#define M 2\nint g = 1;\n"),
        ("edit_leading_comment add on a typedef", "k.c", "#define M 1\ntypedef int I;\n",
         lambda a: a.edit_leading_comment("I", "add", "// An int."), "#define M 1\n// An int.\ntypedef int I;\n"),
        ("edit_leading_comment add on a macro", "k.c", "int g;\n#define M 1\n",
         lambda a: a.edit_leading_comment("M", "add", "// One."), "int g;\n// One.\n#define M 1\n"),
        ("edit_leading_comment remove on a prototype", "k.h", "// Doubles.\nint f(int);\n",
         lambda a: a.edit_leading_comment("f", "remove"), "int f(int);\n"),
        ("insert_sibling after a java field", "K.java", "class A {\n    int x;\n}\n",
         lambda a: a.insert_sibling("A.x", "int y;", "after"), "class A {\n    int x;\n\n    int y;\n}\n"),
        ("edit_leading_comment add on a java field", "K.java", "class A {\n    int x;\n}\n",
         lambda a: a.edit_leading_comment("A.x", "add", "// The x."), "class A {\n    // The x.\n    int x;\n}\n"),
        ("replace_function on a java field", "K.java", "class A {\n    int x;\n}\n",
         lambda a: a.replace_function("A.x", "long x = 2;"), "class A {\n    long x = 2;\n}\n"),
        ("edit_leading_comment add on a destructor", "k.cpp", "class A {\n    ~A() {}\n};\n",
         lambda a: a.edit_leading_comment("A.~A", "add", "// Frees."), "class A {\n    // Frees.\n    ~A() {}\n};\n"),
        ("insert_sibling after an operator", "k.cpp", "class A {\n    bool operator==(const A&) const;\n};\n",
         lambda a: a.insert_sibling("A.operator==", "bool operator!=(const A&) const;", "after"),
         "class A {\n    bool operator==(const A&) const;\n\n    bool operator!=(const A&) const;\n};\n"),
        ("replace_function_body on a destructor", "k.cpp", "class A {\n    ~A() {\n        x();\n    }\n};\n",
         lambda a: a.replace_function_body("A.~A", "free(p);"), "class A {\n    ~A() {\n        free(p);\n    }\n};\n"),
        ("add_field to a typedef of a struct", "k.c", "typedef struct {\n    int x;\n} P;\n",
         lambda a: a.add_field("P", "int y;"), "typedef struct {\n    int y;\n    int x;\n} P;\n"),
        ("insert_sibling after a go type alias", "k.go", "package main\n\ntype T = int\n",
         lambda a: a.insert_sibling("T", "type U = string", "after"), "package main\n\ntype T = int\n\ntype U = string\n"),
    ]
    for label, name, source, action, expected in edits:
        _exact(label, _edit_result(name, source, action), expected)

    # A declaration of several names shows them all; delete_symbol leaves
    # it alone rather than delete the other names, and replace_function
    # replaces what read_symbol shows.
    # (label, file name, source, list_symbols or None, target, read_symbol, the other names)
    several = [
        ("c variables", "k.c", "int a, *b;\nint c;\n", "variable a (line 1)\nvariable b (line 1)\nvariable c (line 2)",
         "b", "int a, *b;", "'a'"),
        ("c typedefs", "k.c", "typedef struct {\n    int x;\n} P, *PP;\n",
         "type P (line 1)\n  field P.x (line 2)\ntype PP (line 1)", "PP", "typedef struct {\n    int x;\n} P, *PP;", "'P'"),
        ("cpp fields", "k.cpp", "struct A {\n    int x, y, z;\n};\n",
         "struct A (line 1)\n  field A.x (line 2)\n  field A.y (line 2)\n  field A.z (line 2)", "A.y", "int x, y, z;",
         "'x' and 'z'"),
        ("java fields", "K.java", "class A {\n    private int x, y = 2;\n}\n",
         "class A (line 1)\n  field A.x (line 2)\n  field A.y (line 2)", "A.x", "private int x, y = 2;", "'y'"),
        ("go variables", "k.go", "package main\n\nvar a, b = 1, 2\n", "variable a (line 3)\nvariable b (line 3)",
         "b", "var a, b = 1, 2", "'a'"),
        ("js constants", "k.js", "const a = 1, b = 2;\nfoo();\n", None, "b", "const a = 1, b = 2;", "'a'"),
    ]
    for label, name, source, listing, target, full, others in several:
        if listing is not None:
            _exact(f"several names ({label}): list_symbols", _read_result(name, source, lambda a: a.list_symbols()), listing)
        _exact(f"several names ({label}): read_symbol('{target}')",
               _read_result(name, source, lambda a: a.read_symbol(target)), full)
        check(f"several names ({label}): round trip", _round_trip(name, source, target), "<unchanged>")
        _refused(f"several names ({label}): delete_symbol('{target}')",
                 _edit_result(name, source, lambda a: a.delete_symbol(target)),
                 f"'{target.split('.')[-1]}' is declared together with {others} in one declaration, so "
                 "delete_symbol would delete")
    _exact("several names: replace_function replaces the declaration read_symbol shows",
           _edit_result("k.c", "int a, *b;\nint c;\n", lambda a: a.replace_function("b", "int a;\nlong *b;")),
           "int a;\nlong *b;\nint c;\n")

    # find_references finds destructors and operators by their names.
    refs_src = ("class A {\npublic:\n    ~A();\n    bool operator==(const A& o) const;\n    operator bool() const;\n};\n\n"
                "A::~A() {}\nbool A::operator==(const A& o) const { return true; }\nA::operator bool() const { return 1; }\n"
                "void f(A *a) { a->~A(); }\n")
    # (target, expected lines)
    refs = [
        ("~A", "line 3: ~A();\nline 8: A::~A() {}\nline 11: void f(A *a) { a->~A(); }"),
        ("operator==", "line 4: bool operator==(const A& o) const;\n"
         "line 9: bool A::operator==(const A& o) const { return true; }"),
        ("operator bool", "line 5: operator bool() const;\nline 10: A::operator bool() const { return 1; }"),
        ("g", None),
    ]
    for target, expected in refs:
        found = _read_result("k.cpp", refs_src, lambda a: a.find_references(target))
        if expected is None:
            check(f"find_references('{target}') finds nothing", found, f"(no references to '{target}' found")
            continue
        # In line order, which find_references does not keep.
        if found.startswith("line "):
            found = "\n".join(sorted(found.splitlines(), key=lambda line: int(line.split(":")[0].split()[-1])))
        _exact(f"find_references('{target}')", found, expected)
    # Macros, globals and fields are found by their names as before.
    # (file name, source, target, expected lines)
    named = [
        ("k.c", "#define M 1\nint g = M;\nint f(void) { return g; }\n", "M",
         "line 1: #define M 1\nline 2: int g = M;"),
        ("k.c", "#define M 1\nint g = M;\nint f(void) { return g; }\n", "g",
         "line 2: int g = M;\nline 3: int f(void) { return g; }"),
        ("K.java", "class A {\n    int x;\n    int m() { return x; }\n}\n", "x",
         "line 2: int x;\nline 3: int m() { return x; }"),
    ]
    for name, source, target, expected in named:
        found = _read_result(name, source, lambda a: a.find_references(target))
        found = "\n".join(sorted(found.splitlines(), key=lambda line: int(line.split(":")[0].split()[-1])))
        _exact(f"find_references('{target}') in {name}", found, expected)


# ──────────────────────────────────────────────
# Deeper comments; Go grouped parameters; byte order marks; Python lists
# ──────────────────────────────────────────────


def test_deeper_comments():
    print("\n═══ leading comments: a comment indented deeper ends the code above ═══")

    # A comment line indented deeper than a symbol is the end of the code
    # above it, never the symbol's leading comment, whatever the tool.
    # (label, file name, source, action, expected file text)
    end_of_f = "def f():\n    return 1\n    # end of f\ndef g():\n    pass\n"
    documented = "def f():\n    return 1\n    # end of f\n# doc g\ndef g():\n    pass\n"
    class_comment = "class A:\n    def a(self):\n        pass\n    # class-level comment\nX = 1\n"
    js_class = "class A {\n  m() {}\n    // deep\n  n() {}\n}\n"
    cases = [
        ("py insert_sibling before (reported)", "k.py", end_of_f,
         lambda a: a.insert_sibling("g", "def h():\n    pass", "before"),
         "def f():\n    return 1\n    # end of f\n\n\ndef h():\n    pass\n\n\ndef g():\n    pass\n"),
        ("py delete_symbol after a class (reported)", "k.py", class_comment,
         lambda a: a.delete_symbol("X"),
         "class A:\n    def a(self):\n        pass\n    # class-level comment\n"),
        ("py delete_symbol keeps the comment, takes its own", "k.py", documented,
         lambda a: a.delete_symbol("g"), "def f():\n    return 1\n    # end of f\n"),
        ("py delete_symbol of a decorated def", "k.py",
         "def f():\n    return 1\n    # end of f\n@dec\ndef g():\n    pass\n",
         lambda a: a.delete_symbol("g"), "def f():\n    return 1\n    # end of f\n"),
        ("py insert_sibling before a documented def", "k.py", documented,
         lambda a: a.insert_sibling("g", "def h():\n    pass", "before"),
         "def f():\n    return 1\n    # end of f\n\n\ndef h():\n    pass\n\n\n# doc g\ndef g():\n    pass\n"),
        ("py insert_sibling before an assignment", "k.py", class_comment,
         lambda a: a.insert_sibling("X", "Y = 2", "before"),
         "class A:\n    def a(self):\n        pass\n    # class-level comment\n\n\nY = 2\n\nX = 1\n"),
        ("py edit_leading_comment add", "k.py", end_of_f,
         lambda a: a.edit_leading_comment("g", "add", "# doc g"),
         "def f():\n    return 1\n    # end of f\n# doc g\ndef g():\n    pass\n"),
        ("py edit_leading_comment replace adds", "k.py", end_of_f,
         lambda a: a.edit_leading_comment("g", "replace", "# doc g"),
         "def f():\n    return 1\n    # end of f\n# doc g\ndef g():\n    pass\n"),
        ("py edit_leading_comment replace keeps the deeper one", "k.py", documented,
         lambda a: a.edit_leading_comment("g", "replace", "# new doc"),
         "def f():\n    return 1\n    # end of f\n# new doc\ndef g():\n    pass\n"),
        ("py edit_leading_comment remove keeps the deeper one", "k.py", documented,
         lambda a: a.edit_leading_comment("g", "remove"),
         "def f():\n    return 1\n    # end of f\ndef g():\n    pass\n"),
        # Comments at the symbol's indentation or less still count.
        ("py comment at the method's indentation", "k.py",
         "class A:\n    x = 1\n    # doc m\n    def m(self):\n        pass\n",
         lambda a: a.delete_symbol("A.m"), "class A:\n    x = 1\n"),
        ("py comment less indented than the method", "k.py",
         "class A:\n    x = 1\n# doc m\n    def m(self):\n        pass\n",
         lambda a: a.delete_symbol("A.m"), "class A:\n    x = 1\n"),
        ("js delete_symbol keeps a deeper comment", "k.js", js_class,
         lambda a: a.delete_symbol("A.n"), "class A {\n  m() {}\n    // deep\n}\n"),
        ("js insert_sibling before, below a deeper comment", "k.js", js_class,
         lambda a: a.insert_sibling("A.n", "h() {}", "before"),
         "class A {\n  m() {}\n    // deep\n\n  h() {}\n\n  n() {}\n}\n"),
        ("js deeper one-line block comment", "k.js",
         "function f() {\n  return 1;\n}\n  /* about f */\nfunction g() {}\n",
         lambda a: a.delete_symbol("g"), "function f() {\n  return 1;\n}\n  /* about f */\n"),
        ("js deeper multi-line block comment", "k.js",
         "function f() {\n  return 1;\n}\n  /*\n   * about f\n   */\nfunction g() {}\n",
         lambda a: a.delete_symbol("g"), "function f() {\n  return 1;\n}\n  /*\n   * about f\n   */\n"),
        ("js deeper line comment above a block comment", "k.js",
         "function f() {\n  return 1;\n}\n  // about f\n/** Doc g. */\nfunction g() {}\n",
         lambda a: a.delete_symbol("g"), "function f() {\n  return 1;\n}\n  // about f\n"),
        ("java Javadoc with deeper continuation lines", "K.java",
         "class A {\n    int x;\n\n    /**\n     * Doc.\n     */\n    void m() {}\n}\n",
         lambda a: a.delete_symbol("A.m"), "class A {\n    int x;\n}\n"),
        ("cpp tab-indented class", "k.cpp",
         "class A {\n\tint x;\n\t\t// deep\n\tvoid m() {}\n};\n",
         lambda a: a.delete_symbol("A.m"), "class A {\n\tint x;\n\t\t// deep\n};\n"),
        ("go edit_leading_comment add", "k.go",
         "package main\n\nvar x = 1\n\t// about x\nfunc g() {}\n",
         lambda a: a.edit_leading_comment("g", "add", "// g does nothing."),
         "package main\n\nvar x = 1\n\t// about x\n// g does nothing.\nfunc g() {}\n"),
        ("rb delete_symbol keeps a deeper comment", "k.rb",
         "def f\n  1\nend\n  # stray\ndef g\nend\n",
         lambda a: a.delete_symbol("g"), "def f\n  1\nend\n  # stray\n"),
        ("yaml edit_leading_comment add", "k.yaml", "a:\n  b: 1\n  # about b\nc: 2\n",
         lambda a: a.edit_leading_comment("c", "add", "# about c"),
         "a:\n  b: 1\n  # about b\n# about c\nc: 2\n"),
        ("yaml edit_leading_comment replace", "k.yaml", "a:\n  b: 1\n  # about b\n# old\nc: 2\n",
         lambda a: a.edit_leading_comment("c", "replace", "# new"),
         "a:\n  b: 1\n  # about b\n# new\nc: 2\n"),
        ("toml edit_leading_comment add above a table", "k.toml", "[a]\nx = 1\n  # about x\n[b]\ny = 2\n",
         lambda a: a.edit_leading_comment("b", "add", "# table b"),
         "[a]\nx = 1\n  # about x\n# table b\n[b]\ny = 2\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"deeper comment: {label}", _edit_result(name, source, action), expected)
    _exact("deeper comment: py insert_sibling before (crlf)",
           _edit_result("k.py", end_of_f, lambda a: a.insert_sibling("g", "def h():\n    pass", "before"), "\r\n"),
           "def f():\r\n    return 1\r\n    # end of f\r\n\r\n\r\ndef h():\r\n    pass\r\n\r\n\r\ndef g():\r\n    pass\r\n")

    # Nothing to remove when the only comment above is deeper.
    # (label, file name, source, target)
    refusals = [
        ("py", "k.py", end_of_f, "g"),
        ("py after a class", "k.py", class_comment, "X"),
        ("js", "k.js", js_class, "A.n"),
        ("yaml", "k.yaml", "a:\n  b: 1\n  # about b\nc: 2\n", "c"),
        ("toml", "k.toml", "[a]\nx = 1\n  # about x\n[b]\ny = 2\n", "b"),
    ]
    for label, name, source, target in refusals:
        _refused(f"deeper comment: {label} edit_leading_comment remove",
                 _edit_result(name, source, lambda a: a.edit_leading_comment(target, "remove")),
                 f"No leading comment found above '{target}'")


def test_go_grouped_parameters():
    print("\n═══ remove_parameter: Go parameters that share a type ═══")

    go = "package main\n\n"
    # (label, source, target, parameter, expected file text or a refusal)
    cases = [
        ("first of a pair (reported)", "func f(a, b int) {}\n", "f", "a", "func f(b int) {}\n"),
        ("last of a pair (reported)", "func f(a, b int) {}\n", "f", "b", "func f(a int) {}\n"),
        ("middle of three", "func f(a, b, c int) {}\n", "f", "b", "func f(a, c int) {}\n"),
        ("pair before another type, first", "func f(a, b int, c string) {}\n", "f", "a",
         "func f(b int, c string) {}\n"),
        ("pair before another type, second", "func f(a, b int, c string) {}\n", "f", "b",
         "func f(a int, c string) {}\n"),
        ("parameter after a pair", "func f(a, b int, c string) {}\n", "f", "c", "func f(a, b int) {}\n"),
        ("variadic", "func f(a, b int, rest ...string) {}\n", "f", "rest", "func f(a, b int) {}\n"),
        ("before a variadic", "func f(a, b int, rest ...string) {}\n", "f", "a",
         "func f(b int, rest ...string) {}\n"),
        ("one per line, first", "func f(\n\ta, b int,\n\tc string,\n) {}\n", "f", "a",
         "func f(\n\tb int,\n\tc string,\n) {}\n"),
        ("one per line, second", "func f(\n\ta, b int,\n\tc string,\n) {}\n", "f", "b",
         "func f(\n\ta int,\n\tc string,\n) {}\n"),
        ("one per line, after the pair", "func f(\n\ta, b int,\n\tc string,\n) {}\n", "f", "c",
         "func f(\n\ta, b int,\n) {}\n"),
        ("method", "type T struct{}\n\nfunc (r *T) m(a, b int) {}\n", "T.m", "b",
         "type T struct{}\n\nfunc (r *T) m(a int) {}\n"),
        ("named results stay", "func f(a, b int) (n int, err error) { return }\n", "f", "b",
         "func f(a int) (n int, err error) { return }\n"),
        # Types are no names, and neither are the receiver and the results.
        ("type only", "func f(int, string) {}\n", "f", "int", None),
        ("func type only", "func f(func(x int)) {}\n", "f", "x", None),
        ("receiver", "type T struct{}\n\nfunc (r *T) m(a, b int) {}\n", "T.m", "r", None),
        ("named result", "func f(a, b int) (n int, err error) { return }\n", "f", "n", None),
    ]
    for label, source, target, parameter, expected in cases:
        result = _edit_result("k.go", go + source, lambda a: a.remove_parameter(target, parameter))
        if expected is None:
            _refused(f"go remove_parameter ({label})", result,
                     f"Parameter '{parameter}' not found in '{target}'")
        else:
            _exact(f"go remove_parameter ({label})", result, go + expected)
    _exact("go remove_parameter (first of a pair, crlf)",
           _edit_result("k.go", go + "func f(\n\ta, b int,\n) {}\n", lambda a: a.remove_parameter("f", "a"), "\r\n"),
           (go + "func f(\n\tb int,\n) {}\n").replace("\n", "\r\n"))
    # Removing every name, one at a time, leaves ().
    path = _write_temp("k.go", go + "func f(a, b int) {}\n")
    try:
        Applier(path).remove_parameter("f", "b")
        Applier(path).remove_parameter("f", "a")
        result = read_file(path)
    except ApplierError as e:
        result = f"REFUSED: {e}"
    os.remove(path)
    _exact("go remove_parameter: both names of a pair", result, go + "func f() {}\n")
    # add_parameter goes after the whole declaration.
    _exact("go add_parameter after a pair",
           _edit_result("k.go", go + "func f(a, b int) {}\n", lambda a: a.add_parameter("f", "c string")),
           go + "func f(a, b int, c string) {}\n")


def test_byte_order_mark():
    print("\n═══ UTF-8 byte order mark: kept first, never part of the text ═══")

    bom = "\ufeff"
    py = bom + "def f():\n    pass\n\n\ndef g():\n    pass\n"
    # (label, file name, source, action, expected file text)
    cases = [
        ("js insert_sibling before (reported)", "k.js", bom + "function f() {}\n",
         lambda a: a.insert_sibling("f", "function g() {}", "before"),
         bom + "function g() {}\n\nfunction f() {}\n"),
        ("js insert_sibling above a leading comment (reported)", "k.js", bom + "// doc\nfunction f() {}\n",
         lambda a: a.insert_sibling("f", "function g() {}", "before"),
         bom + "function g() {}\n\n// doc\nfunction f() {}\n"),
        ("py delete_symbol (reported)", "k.py", py, lambda a: a.delete_symbol("f"), bom + "def g():\n    pass\n"),
        ("py insert_sibling before (reported)", "k.py", bom + "def f():\n    pass\n",
         lambda a: a.insert_sibling("f", "def g():\n    pass", "before"),
         bom + "def g():\n    pass\n\n\ndef f():\n    pass\n"),
        ("py replace_function", "k.py", py, lambda a: a.replace_function("f", "def f():\n    return 1"),
         bom + "def f():\n    return 1\n\n\ndef g():\n    pass\n"),
        ("py replace_in_body", "k.py", py, lambda a: a.replace_in_body("f", "pass", "return 1"),
         bom + "def f():\n    return 1\n\n\ndef g():\n    pass\n"),
        ("py edit_leading_comment remove", "k.py", bom + "# doc\ndef f():\n    pass\n",
         lambda a: a.edit_leading_comment("f", "remove"), bom + "def f():\n    pass\n"),
        ("py edit_leading_comment add", "k.py", bom + "def f():\n    pass\n",
         lambda a: a.edit_leading_comment("f", "add", "# doc"), bom + "# doc\ndef f():\n    pass\n"),
        ("py encoding declaration stays first", "k.py", bom + "# -*- coding: utf-8 -*-\ndef f():\n    pass\n",
         lambda a: a.insert_sibling("f", "def g():\n    pass", "before"),
         bom + "# -*- coding: utf-8 -*-\ndef g():\n    pass\n\n\ndef f():\n    pass\n"),
        ("rb magic comment stays first", "k.rb", bom + "# frozen_string_literal: true\ndef f\nend\n",
         lambda a: a.insert_sibling("f", "def g\nend", "before"),
         bom + "# frozen_string_literal: true\ndef g\nend\n\ndef f\nend\n"),
        ("py add_top_level at the top", "k.py", bom + "import os\n\n\ndef f():\n    pass\n",
         lambda a: a.add_top_level("X = 1", "top"),
         bom + "import os\n\nX = 1\n\n\ndef f():\n    pass\n"),
        ("py add_top_level into a file that is only the mark", "k.py", bom,
         lambda a: a.add_top_level("X = 1"), bom + "X = 1\n"),
        ("py add_import at the top", "k.py", bom + "def f():\n    pass\n", lambda a: a.add_import("import os"),
         bom + "import os\n\n\ndef f():\n    pass\n"),
        ("go add_import", "k.go", bom + 'package main\n\nimport "os"\n\nfunc f() {}\n',
         lambda a: a.add_import('import "fmt"'),
         bom + 'package main\n\nimport "fmt"\nimport "os"\n\nfunc f() {}\n'),
        ("json replace_value", "k.json", bom + '{\n  "a": 1\n}\n', lambda a: a.replace_value("a", "2"),
         bom + '{\n  "a": 2\n}\n'),
        ("json add_key", "k.json", bom + '{"a": 1}\n', lambda a: a.add_key("", "b", "2"), bom + '{"a": 1, "b": 2}\n'),
        ("yaml add_key", "k.yaml", bom + "a: 1\n", lambda a: a.add_key("", "b", "2"), bom + "a: 1\nb: 2\n"),
        ("toml add_key", "k.toml", bom + "a = 1\n", lambda a: a.add_key("", "b", "2"), bom + "a = 1\nb = 2\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"bom: {label}", _edit_result(name, source, action), expected)
    # With CRLF line endings, both are kept.
    _exact("bom: py insert_sibling after (crlf)",
           _edit_result("k.py", bom + "def f():\n    pass\n", lambda a: a.insert_sibling("f", "def g():\n    pass", "after"), "\r\n"),
           bom + "def f():\r\n    pass\r\n\r\n\r\ndef g():\r\n    pass\r\n")
    _exact("bom: py insert_sibling before (crlf)",
           _edit_result("k.py", bom + "def f():\n    pass\n", lambda a: a.insert_sibling("f", "def g():\n    pass", "before"), "\r\n"),
           bom + "def g():\r\n    pass\r\n\r\n\r\ndef f():\r\n    pass\r\n")
    # Several edits in a row through one Applier.
    path = _write_temp("k.py", py)
    try:
        app = Applier(path)
        app.insert_sibling("f", "X = 1", "before")
        app.delete_symbol("g")
        result = _read_bytes(path).decode("utf-8")
    except ApplierError as e:
        result = f"REFUSED: {e}"
    os.remove(path)
    _exact("bom: two edits through one Applier", result, bom + "X = 1\n\n\ndef f():\n    pass\n")

    # The mark is no text: not in what the read tools return.
    # (label, file name, source, action, expected result)
    reads = [
        ("read_symbol", "k.py", bom + "X = 1\n", lambda a: a.read_symbol("X"), "X = 1"),
        ("read_symbol js", "k.js", bom + "const X = 1;\n", lambda a: a.read_symbol("X"), "const X = 1;"),
        ("find_references", "k.py", bom + "x = 1\n\n\ndef f():\n    return x\n",
         lambda a: a.find_references("x"), "line 1: x = 1\nline 5: return x"),
        ("list_symbols", "k.py", py, lambda a: a.list_symbols(), "function f (line 1)\nfunction g (line 5)"),
        ("read_imports", "k.py", bom + "import os\n", lambda a: a.read_imports(), "import os"),
    ]
    for label, name, source, action, expected in reads:
        _exact(f"bom: {label}", _read_result(name, source, action), expected)

    # The syntax check sees the text after the mark.
    _refused("bom: py syntax error refused",
             _edit_result("k.py", py, lambda a: a.replace_function("f", "def f(:\n    pass")),
             "syntax error at line 1")
    _refused("bom: json syntax error refused",
             _edit_result("k.json", bom + '{"a": 1}\n', lambda a: a.replace_value("a", "1,")),
             "syntax error")

    # Files in other encodings are refused with what they are.
    # (label, file name, raw bytes, reason)
    encodings = [
        ("utf-16", "k.py", "def f():\n    pass\n".encode("utf-16"), "k.py is UTF-16 text (it starts with a UTF-16 byte order mark)"),
        ("utf-16 be", "k.py", b"\xfe\xff" + "def f():\n".encode("utf-16-be"), "is UTF-16 text"),
        ("utf-32", "k.py", "def f():\n    pass\n".encode("utf-32"), "k.py is UTF-32 text"),
        ("latin-1", "k.py", "X = 'caf\xe9'\n".encode("latin-1"), "k.py is not UTF-8 text ("),
    ]
    for label, name, data, reason in encodings:
        path = os.path.join(TESTS_DIR, name)
        with open(path, "wb") as f:
            f.write(data)
        result = _refusal(lambda: Applier(path).delete_symbol("f"))
        check(f"bom: {label} file refused", result, reason)
        check(f"bom: {label} refusal names UTF-8", result, "ast-editor reads and writes UTF-8 files only")
        check(f"bom: {label} file unchanged", "<unchanged>" if _read_bytes(path) == data else "CHANGED", "<unchanged>")
        os.remove(path)


def test_lone_surrogate():
    print("\n═══ a lone surrogate in new text: refused, the file kept ═══")
    # JSON lets a client send half of a surrogate pair, which has no UTF-8 form.
    lone = chr(0xD800)
    reason = "lone surrogate, U+D800, which is not a character"
    for label, name, src, action in [
        ("py replace_function_body", "s.py", "def f():\n    return 1\n",
         lambda a: a.replace_function_body("f", "return '" + lone + "'")),
        ("py replace_function", "s.py", "def f():\n    return 1\n",
         lambda a: a.replace_function("f", "def f():\n    return '" + lone + "'")),
        ("js replace_in_body", "s.js", "function f() {\n  return 1;\n}\n",
         lambda a: a.replace_in_body("f", "1", "'" + lone + "'")),
        ("py insert_in_body", "s.py", "def f():\n    x = 1\n",
         lambda a: a.insert_in_body("f", "y = '" + lone + "'", after="x = 1")),
        ("py add_parameter", "s.py", "def f(a):\n    pass\n", lambda a: a.add_parameter("f", "b='" + lone + "'")),
        ("py replace_docstring", "s.py", 'def f():\n    """D."""\n',
         lambda a: a.replace_docstring("f", '"""' + lone + '"""')),
        ("py edit_leading_comment", "s.py", "def f():\n    pass\n",
         lambda a: a.edit_leading_comment("f", "add", "# " + lone)),
        ("json replace_value", "s.json", '{\n  "a": 1\n}\n', lambda a: a.replace_value("a", '"' + lone + '"')),
        ("yaml add_key", "s.yaml", "a: 1\n", lambda a: a.add_key("", "b", '"' + lone + '"')),
        ("toml append_to_array", "s.toml", "a = [1]\n", lambda a: a.append_to_array("a", '"' + lone + '"')),
        ("py read_symbol target", "s.py", "def f():\n    pass\n", lambda a: a.read_symbol("f" + lone)),
    ]:
        _refused(label, _edit_result(name, src, action), reason)


def test_python_list_append():
    print("\n═══ append_to_array on Python lists: layout, comments, trailing commas ═══")

    # (label, source, target, value, expected file text)
    cases = [
        ("comment after the last element (reported)", "a = [\n    1,\n    2,  # two\n]\n", "a", "3",
         "a = [\n    1,\n    2,  # two\n    3,\n]\n"),
        ("comment, no trailing comma", "a = [\n    1,\n    2  # two\n]\n", "a", "3",
         "a = [\n    1,\n    2,  # two\n    3\n]\n"),
        ("one per line, no trailing comma", "a = [\n    1,\n    2\n]\n", "a", "3", "a = [\n    1,\n    2,\n    3\n]\n"),
        ("comment on a line of its own after the last", "a = [\n    1,\n    # more later\n]\n", "a", "2",
         "a = [\n    1,\n    2,\n    # more later\n]\n"),
        ("only a comment", "a = [\n    # none yet\n]\n", "a", "1", "a = [\n    # none yet\n    1,\n]\n"),
        ("comment after the bracket", "a = [  # list\n    1,\n]\n", "a", "2", "a = [  # list\n    1,\n    2,\n]\n"),
        ("inline", "a = [1, 2]\n", "a", "3", "a = [1, 2, 3]\n"),
        ("inline with a trailing comma", "a = [1, 2,]\n", "a", "3", "a = [1, 2, 3,]\n"),
        ("inline with a comment after it", "a = [1, 2]  # nums\n", "a", "3", "a = [1, 2, 3]  # nums\n"),
        ("empty", "a = []\n", "a", "3", "a = [3]\n"),
        ("empty over two lines", "a = [\n]\n", "a", "3", "a = [\n    3,\n]\n"),
        ("nested inline", "a = [[1, 2], [3]]\n", "a", "[4]", "a = [[1, 2], [3], [4]]\n"),
        ("nested one per line", "a = [\n    [1, 2],\n    [3],\n]\n", "a", "[4]",
         "a = [\n    [1, 2],\n    [3],\n    [4],\n]\n"),
        ("splat", "a = [*b, 1]\n", "a", "2", "a = [*b, 1, 2]\n"),
        ("class attribute", "class A:\n    L = [\n        1,  # one\n    ]\n", "A.L", "2",
         "class A:\n    L = [\n        1,  # one\n        2,\n    ]\n"),
        ("two-space indentation", "a = [\n  1,  # one\n]\n", "a", "2", "a = [\n  1,  # one\n  2,\n]\n"),
    ]
    for label, source, target, value, expected in cases:
        _exact(f"py append_to_array ({label})",
               _edit_result("k.py", source, lambda a: a.append_to_array(target, value)), expected)
    _exact("py append_to_array (comment after the last element, crlf)",
           _edit_result("k.py", "a = [\n    1,\n    2,  # two\n]\n", lambda a: a.append_to_array("a", "3"), "\r\n"),
           "a = [\r\n    1,\r\n    2,  # two\r\n    3,\r\n]\r\n")
    # Tuples, sets and JS arrays are not lists the tool appends to.
    _refused("py append_to_array on a tuple",
             _edit_result("k.py", "a = (1, 2)\n", lambda a: a.append_to_array("a", "3")),
             "Target 'a' is a tuple, not a list")
    _refused("py append_to_array on a set",
             _edit_result("k.py", "a = {1, 2}\n", lambda a: a.append_to_array("a", "3")),
             "Target 'a' is a set, not a list")
    _refused("js append_to_array",
             _edit_result("k.js", "const a = [1, 2];\n", lambda a: a.append_to_array("a", "3")),
             "append_to_array is not supported for .js")
    # Dict literals with comments already go through the same entry code.
    # (label, source, action, expected file text)
    dicts = [
        ("add_key after a comment", "d = {\n    'a': 1,\n    'b': 2,  # two\n}\n",
         lambda a: a.add_key("d", "'c'", "3"), "d = {\n    'a': 1,\n    'b': 2,  # two\n    'c': 3,\n}\n"),
        ("add_key, comment and no trailing comma", "d = {\n    'a': 1  # one\n}\n",
         lambda a: a.add_key("d", "'b'", "2"), "d = {\n    'a': 1,  # one\n    'b': 2\n}\n"),
        ("delete_key with its comment", "d = {\n    'a': 1,\n    'b': 2,  # two\n}\n",
         lambda a: a.delete_key("d.'b'"), "d = {\n    'a': 1,\n}\n"),
        ("delete_key keeps a comment above the next key", "d = {\n    'a': 1,\n    # about b\n    'b': 2,\n}\n",
         lambda a: a.delete_key("d.'a'"), "d = {\n    # about b\n    'b': 2,\n}\n"),
    ]
    for label, source, action, expected in dicts:
        _exact(f"py dict {label}", _edit_result("k.py", source, action), expected)


# ──────────────────────────────────────────────
# Final review follow-ups: read_symbol shapes, names declared together,
# merged namespaces, Go parameter comments, list entries, byte order marks
# ──────────────────────────────────────────────


def test_final_review_followups():
    print("\n═══ final review follow-ups ═══")

    # Relative Python content whose lines at the target's indentation are
    # a nested symbol's decorators is re-indented as relative content: only
    # a symbol's own headers (its first line a decorator) may sit there.
    nested = "class A:\n    class B:\n        def m(self):\n            return 1\n\n    def n(self):\n        pass\n"
    inner = "class Inner:\n    @property\n    def a(self):\n        return 1\n\n    @staticmethod\n    def b():\n        return 2"
    inner_at_4 = ("    class Inner:\n        @property\n        def a(self):\n            return 1\n\n"
                  "        @staticmethod\n        def b():\n            return 2\n")
    # (label, file name, source, edit, expected file text)
    cases = [
        ("py replace_function, a decorated method first (reported)", "f.py", nested,
         lambda a: a.replace_function("A.B", "class B:\n    @property\n    def p(self):\n        return 1"),
         "class A:\n    class B:\n        @property\n        def p(self):\n            return 1\n\n    def n(self):\n        pass\n"),
        ("py add_method, decorated methods (reported)", "f.py", "class Outer:\n    pass\n",
         lambda a: a.add_method("Outer", inner), "class Outer:\n    pass\n\n" + inner_at_4),
        ("py insert_sibling, decorated methods (reported)", "f.py", "class Outer:\n    def m(self):\n        pass\n",
         lambda a: a.insert_sibling("Outer.m", inner, "after"),
         "class Outer:\n    def m(self):\n        pass\n\n" + inner_at_4),
        ("py replace_function, a decorated inner function (reported)", "f.py", nested,
         lambda a: a.replace_function("A.n", "def n(self):\n    @cache\n    def inner():\n        return 1"),
         "class A:\n    class B:\n        def m(self):\n            return 1\n\n"
         "    def n(self):\n        @cache\n        def inner():\n            return 1\n"),
        # A symbol's own decorators still read as read_symbol shows them.
        ("py replace_function, its own decorators as read", "f.py",
         "class A:\n    @property\n    @cache\n    def m(self):\n        return 1\n",
         lambda a: a.replace_function("A.m", "@property\n    @cache\n    def m(self):\n        return 2"),
         "class A:\n    @property\n    @cache\n    def m(self):\n        return 2\n"),
        # At column 0 the content goes in as written, and so does
        # add_top_level's content when its lines at an indentation are not
        # those of a symbol read there: a macro's continued lines, a
        # Whitesmiths body.
        ("c add_top_level, a macro with an indented brace", "f.c", "int x;\n",
         lambda a: a.add_top_level("#define SWAP(a, b) \\\n    { \\\n        int t = a; \\\n    }"),
         "int x;\n\n#define SWAP(a, b) \\\n    { \\\n        int t = a; \\\n    }\n"),
        ("c add_top_level, Whitesmiths braces", "f.c", "int x;\n",
         lambda a: a.add_top_level("int f(void)\n    {\n    return 0;\n    }"),
         "int x;\n\nint f(void)\n    {\n    return 0;\n    }\n"),
        ("js replace_function at column 0, an indented brace", "f.js", "const x = 1;\n",
         lambda a: a.replace_function("x", "const x =\n  {\n  a: 1,\n  };"), "const x =\n  {\n  a: 1,\n  };\n"),
        ("cpp add_method, a Whitesmiths body is relative content", "f.cpp", "class A {\n  int v;\n};\n",
         lambda a: a.add_method("A", "void m()\n  {\n  v = 1;\n  }"),
         "class A {\n  int v;\n\n  void m()\n    {\n    v = 1;\n    }\n};\n"),
        # A comment after the symbol on its last line is not part of it: it
        # stays after new content, unless the content ends with one.
        ("cpp replace_function keeps a field's comment", "f.cpp", "struct A {\n    int x;  // the x\n    int y;\n};\n",
         lambda a: a.replace_function("A.x", "long x;"), "struct A {\n    long x;  // the x\n    int y;\n};\n"),
        ("cpp replace_function, content with its own comment", "f.cpp",
         "struct A {\n    int x;  // the x\n    int y;\n};\n",
         lambda a: a.replace_function("A.x", "long x;  // wider"), "struct A {\n    long x;  // wider\n    int y;\n};\n"),
        ("cpp replace_function, the comment given too", "f.cpp", "struct A {\n    int x;  // the x\n};\n",
         lambda a: a.replace_function("A.x", "long x;  // the x"), "struct A {\n    long x;  // the x\n};\n"),
        ("py replace_function keeps a comment after a value over several lines", "f.py", "X = 1  # note\nY = 2\n",
         lambda a: a.replace_function("X", "X = [\n    1,\n]"), "X = [\n    1,\n]  # note\nY = 2\n"),
        ("py replace_function, a # in a string is no comment", "f.py", "X = 1  # note\n",
         lambda a: a.replace_function("X", "X = '# not'"), "X = '# not'  # note\n"),
        ("go replace_function keeps the comment after a closing brace", "f.go", "package p\n\nfunc f() {\n}  // f\n",
         lambda a: a.replace_function("f", "func f() {\n\treturn\n}"), "package p\n\nfunc f() {\n\treturn\n}  // f\n"),
        ("c replace_function keeps a block comment over two lines", "f.c",
         "struct A {\n    int x; /* a\n       b */\n    int y;\n};\n", lambda a: a.replace_function("A.x", "long x;"),
         "struct A {\n    long x; /* a\n       b */\n    int y;\n};\n"),
        ("c replace_function, content with its own comment, a block comment over two lines", "f.c",
         "struct A {\n    int x; /* a\n       b */\n    int y;\n};\n", lambda a: a.replace_function("A.x", "long x; // own"),
         "struct A {\n    long x; // own\n    int y;\n};\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"final review ({label})", _edit_result(name, source, action), expected)
    _exact("final review (relative C++ initializer list at the symbol's indentation reads as read_symbol shows it)",
           _edit_result("f.cpp", "class A {\npublic:\n    A()\n        : v(1) {}\n    int v;\n};\n",
                        lambda a: a.replace_function("A.A", "A()\n    : v(2) {}")),
           "class A {\npublic:\n    A()\n    : v(2) {}\n    int v;\n};\n")

    # (label, file name, source, target)
    trips = [
        ("c macro with an indented brace", "f.c",
         "#define SWAP(a, b) \\\n    { \\\n        int t = a; \\\n        a = b; \\\n        b = t; \\\n    }\n\nint x;\n", "SWAP"),
        ("c Whitesmiths function", "f.c", "int f(void)\n    {\n    return 0;\n    }\n", "f"),
        ("js const with an indented brace", "f.js", "const x =\n  {\n  a: 1,\n  };\n", "x"),
        ("cpp field with a comment", "f.cpp", "struct A {\n    int x;  // the x\n    int y;\n};\n", "A.x"),
        ("java field with a comment", "F.java", "class A {\n    private int x;  // the x\n    private int y;\n}\n", "A.x"),
        ("cpp namespace with a closing comment", "f.cpp", "namespace geo {\nint f();\n}  // namespace geo\n", "geo"),
        ("c function with a comment", "f.c", "int f() { return 1; }  // note\nint g() { return 2; }\n", "f"),
        ("py assignment with a comment", "f.py", "X = 1  # note\nY = 2\n", "X"),
        ("py assignment with a ; and a comment", "f.py", "X = 1;  # c\nY = 2\n", "X"),
        ("rb method with a comment after end", "f.rb", "def f\n  1\nend # f\n", "f"),
        ("js class with a ; and a comment", "f.js", "class A {};  // c\nlet b;\n", "A"),
        ("ts abstract method with a comment", "f.ts", "abstract class A {\n  abstract m(): void;  // c\n}\n", "A.m"),
        ("c field with a block comment over two lines", "f.c", "struct A {\n    int x; /* a\n       b */\n    int y;\n};\n",
         "A.x"),
    ]
    for label, name, source, target in trips:
        for newline, ending in (("\n", "lf"), ("\r\n", "crlf")):
            check(f"final review round trip ({label}, {ending})", _round_trip(name, source, target, newline), "<unchanged>")

    # Removing or replacing one name of a declaration that defines a C/C++
    # type, or declares C++ structured bindings, keeps the other names.
    declared = "is declared together with {} in one declaration, so delete_symbol would delete it too"
    # (label, file name, source, target, other names)
    together = [
        ("variable and its struct (reported)", "k.c", "struct S { int a; } s;\nint z;\n", "s", "'S'"),
        ("struct and its variable (reported)", "k.c", "struct S { int a; } s;\nint z;\n", "S", "'s'"),
        ("typedef and its struct (reported)", "k.c", "typedef struct N { int v; } Node;\nint z;\n", "Node", "'N'"),
        ("variable and its enum (reported)", "k.c", "enum E { R, G } e;\nint z;\n", "e", "'E'"),
        ("variable and its class (reported)", "k.cpp", "class A { int x; } a;\nint z;\n", "a", "'A'"),
        ("structured bindings (reported)", "k.cpp", "auto [x, y] = pair;\nint z;\n", "x", "'y'"),
        ("variable and its struct, struct used later", "k.c",
         "struct config {\n    int debug;\n} cfg;\n\nint use(void) { struct config c; c.debug = 0; return c.debug; }\n",
         "cfg", "'config'"),
    ]
    for label, name, source, target, others in together:
        _refused(f"final review delete_symbol ({label})", _edit_result(name, source, lambda a: a.delete_symbol(target)),
                 f"'{target}' " + declared.format(others))
    _exact("final review delete_symbol (a typedef named as its struct goes whole)",
           _edit_result("k.c", "typedef struct Node { int v; } Node;\nint z;\n", lambda a: a.delete_symbol("Node")), "int z;\n")
    _exact("final review list_symbols (structured bindings)",
           _read_result("k.cpp", "auto [x, y] = pair;\nint z;\n", lambda a: a.list_symbols()),
           "variable x (line 1)\nvariable y (line 1)\nvariable z (line 2)")
    replaced = ("is declared together with {} in one declaration, which replace_function replaces whole "
                "(read_symbol shows it), and the content would drop it. Keep {} in the content")
    # (label, file name, source, target, content, other names)
    drops = [
        ("c variables (reported)", "k.c", "int a = 1, b = 2;\nint f(void) { return a; }\n", "b", "int b = 3;", "'a'"),
        ("go variables (reported)", "k.go", "package p\n\nvar a, b = 1, 2\n", "b", "var b = 3", "'a'"),
        ("java fields (reported)", "K.java", "class A { int a = 1, b = 2; }\n", "A.b", "int b = 3;", "'a'"),
        ("c struct of a variable (reported)", "k.c", "struct S { int a; } s;\nint z;\n", "s", "struct S t;", "'S'"),
        ("js constants", "k.js", "const a = 1, b = 2;\n", "b", "const b = 3;", "'a'"),
        ("c variable of a struct", "k.c", "struct S { int a; } s;\nint z;\n", "S", "struct S { long a; };", "'s'"),
    ]
    for label, name, source, target, content, others in drops:
        _refused(f"final review replace_function ({label})",
                 _edit_result(name, source, lambda a: a.replace_function(target, content)),
                 f"'{target.split('.')[-1]}' " + replaced.format(others, others))
    # (label, file name, source, target, content, expected file text)
    kept = [
        ("c variables", "k.c", "int a = 1, b = 2;\n", "b", "int a = 1, b = 3;", "int a = 1, b = 3;\n"),
        ("c struct of a variable", "k.c", "struct S { int a; } s;\nint z;\n", "s", "struct S { long a; } s;",
         "struct S { long a; } s;\nint z;\n"),
        ("java fields, one per declaration", "K.java", "class A {\n    int a = 1, b = 2;\n}\n", "A.b",
         "int a = 1;\nint b = 3;", "class A {\n    int a = 1;\n    int b = 3;\n}\n"),
    ]
    for label, name, source, target, content, expected in kept:
        _exact(f"final review replace_function keeps the names ({label})",
               _edit_result(name, source, lambda a: a.replace_function(target, content)), expected)

    # A namespace opened again in its scope (C++, TS), or merged with a TS
    # class, function or enum of its name, is one container: its members
    # are found in every block, a definition in a later block wins over a
    # forward declaration in an earlier one, and it is listed once.
    reopened = "namespace n { class A; }\n\nnamespace n {\nclass A {\n  int x;\n};\n}\n"
    prototype = "namespace n {\nvoid f();\n}\nnamespace n {\nvoid f() {}\n}\n"
    ts_class = ("export class Foo {\n  bar(): number {\n    return 1;\n  }\n}\n\n"
                "export namespace Foo {\n  export const VERSION = 1;\n  export function parse() {}\n}\n")
    ts_enum = "export enum Color { Red }\nexport namespace Color {\n  export function parse(s: string): Color { return Color.Red; }\n}\n"
    ts_function = "export function build() {}\nexport namespace build {\n  export const x = 1;\n}\n"
    ts_reopened = "namespace N {\n  export class C {}\n}\nmodule N {\n  export class D {}\n}\n"
    # (label, file name, source, list_symbols, [(target, read_symbol)])
    merged = [
        ("cpp namespace reopened, a class (reported)", "k.cpp", reopened,
         "namespace n (line 1)\n  class n.A (line 4)\n    field n.A.x (line 5)",
         [("n.A", "class A {\n  int x;\n};"), ("n.A.x", "int x;")]),
        ("cpp namespace reopened, a function (reported)", "k.cpp", prototype,
         "namespace n (line 1)\n  function n.f (line 5)", [("n.f", "void f() {}")]),
        ("ts class and namespace (reported)", "k.ts", ts_class,
         "class Foo (line 1)\n  method Foo.bar (line 2)\n  constant Foo.VERSION (line 8)\n  function Foo.parse (line 9)",
         [("Foo", None), ("Foo.bar", "bar(): number {\n    return 1;\n  }"), ("Foo.parse", "export function parse() {}"),
          ("Foo.VERSION", "export const VERSION = 1;")]),
        ("ts class and a namespace not exported", "k.ts", ts_class.replace("export namespace", "namespace"),
         "class Foo (line 1)\n  method Foo.bar (line 2)\n  constant Foo.VERSION (line 8)\n  function Foo.parse (line 9)",
         [("Foo.parse", "export function parse() {}")]),
        ("ts enum and namespace (reported)", "k.ts", ts_enum, "enum Color (line 1)\n  function Color.parse (line 3)",
         [("Color", "export enum Color { Red }"),
          ("Color.parse", "export function parse(s: string): Color { return Color.Red; }")]),
        ("ts function and namespace (reported)", "k.ts", ts_function, "function build (line 1)\n  constant build.x (line 3)",
         [("build", "export function build() {}"), ("build.x", "export const x = 1;")]),
        ("ts namespace reopened as a module", "k.ts", ts_reopened,
         "namespace N (line 1)\n  class N.C (line 2)\n  class N.D (line 5)",
         [("N.C", "export class C {}"), ("N.D", "export class D {}")]),
    ]
    for label, name, source, listing, reads in merged:
        _exact(f"final review merged ({label}): list_symbols", _read_result(name, source, lambda a: a.list_symbols()), listing)
        _listed_targets_resolve(f"final review merged ({label})", name, source)
        for target, full in reads:
            if full is None:
                full = _read_result(name, source, lambda a: a.read_symbol(target))
                check(f"final review merged ({label}): read_symbol('{target}') is the class",
                      full, "export class Foo {\n  bar(): number {")
                continue
            _exact(f"final review merged ({label}): read_symbol('{target}')",
                   _read_result(name, source, lambda a: a.read_symbol(target)), full)
    # (label, file name, source, edit, expected file text)
    merged_edits = [
        ("cpp delete_symbol on the class, not its forward declaration", "k.cpp", reopened,
         lambda a: a.delete_symbol("n.A"), "namespace n { class A; }\n\nnamespace n {\n}\n"),
        ("cpp add_field in the class's block", "k.cpp", reopened, lambda a: a.add_field("n.A", "int y;"),
         "namespace n { class A; }\n\nnamespace n {\nclass A {\n  int y;\n  int x;\n};\n}\n"),
        ("cpp replace_function_body of the definition", "k.cpp", prototype,
         lambda a: a.replace_function_body("n.f", "return;"),
         "namespace n {\nvoid f();\n}\nnamespace n {\nvoid f() {\n  return;\n}\n}\n"),
        ("ts replace_function_body of a class member (reported)", "k.ts", ts_class,
         lambda a: a.replace_function_body("Foo.bar", "return 2;"), ts_class.replace("return 1;", "return 2;")),
    ]
    for label, name, source, action, expected in merged_edits:
        _exact(f"final review merged ({label})", _edit_result(name, source, action), expected)

    # Alternatives in a C/C++ preprocessor conditional are listed once, as
    # the name targets the first; C++ overloads are listed by their
    # parameter types.
    _exact("final review list_symbols (alternatives in #ifdef ... #else)",
           _read_result("k.c", "#ifdef X\nint f(void) { return 1; }\n#else\nint f(void) { return 2; }\n#endif\n",
                        lambda a: a.list_symbols()), "function f (line 2)")
    _exact("final review list_symbols (cpp overloads)",
           _read_result("k.cpp", "void g(int) {}\nvoid g(double) {}\n", lambda a: a.list_symbols()),
           "function g(int) (line 1)\nfunction g(double) (line 2)")

    # Removing one Go name of a declaration of several keeps the comments
    # of the others.
    commented = "package p\n\nfunc f(\n\ta, // first\n\tb, // second\n\tc int, // third\n) {}\n"
    own_line = "package p\n\nfunc f(\n\ta,\n\t// about b\n\tb int,\n) {}\n"
    # (label, source, parameter, expected file text)
    params = [
        ("first name with comments", commented, "a", "package p\n\nfunc f(\n\tb, // second\n\tc int, // third\n) {}\n"),
        ("middle name with comments (reported)", commented, "b",
         "package p\n\nfunc f(\n\ta, // first\n\tc int, // third\n) {}\n"),
        ("last name with comments (reported)", commented, "c",
         "package p\n\nfunc f(\n\ta, // first\n\tb int, // second\n) {}\n"),
        ("last name after a block comment (reported)", "package p\n\nfunc f(a /* x */, b int) {}\n", "b",
         "package p\n\nfunc f(a /* x */ int) {}\n"),
        ("a comment on a line of its own is the next name's", own_line, "a",
         "package p\n\nfunc f(\n\t// about b\n\tb int,\n) {}\n"),
        ("a name goes with the comment above it", own_line, "b", "package p\n\nfunc f(\n\ta int,\n) {}\n"),
        ("one per line, no comments", "package p\n\nfunc f(\n\ta,\n\tb int,\n\tc string,\n) {}\n", "b",
         "package p\n\nfunc f(\n\ta int,\n\tc string,\n) {}\n"),
    ]
    for label, source, parameter, expected in params:
        _exact(f"final review go remove_parameter ({label})",
               _edit_result("k.go", source, lambda a: a.remove_parameter("f", parameter)), expected)
    _exact("final review go remove_parameter (last name with comments, crlf)",
           _edit_result("k.go", commented, lambda a: a.remove_parameter("f", "c"), "\r\n"),
           "package p\r\n\r\nfunc f(\r\n\ta, // first\r\n\tb int, // second\r\n) {}\r\n")

    # A value that ends with a comment gets its comma before it; a list
    # aligned under its `[` keeps one element per line.
    # (label, file name, source, value, expected file text)
    lists = [
        ("py value with a comment (reported)", "k.py", "a = [\n    1,\n]\n", "3  # new", "a = [\n    1,\n    3,  # new\n]\n"),
        ("toml value with a comment (reported)", "k.toml", "a = [\n    1,\n]\n", "3  # new",
         "a = [\n    1,\n    3,  # new\n]\n"),
        ("py empty list over two lines, value with a comment", "k.py", "a = [\n]\n", "3  # new", "a = [\n    3,  # new\n]\n"),
        ("py value with a # in a string", "k.py", "a = [\n    1,\n]\n", "'#x'", "a = [\n    1,\n    '#x',\n]\n"),
        ("py no trailing comma, value with a comment", "k.py", "a = [\n    1\n]\n", "3  # new",
         "a = [\n    1,\n    3  # new\n]\n"),
        ("py aligned under its bracket (reported)", "k.py", "a = [1,\n     2]\n", "9", "a = [1,\n     2,\n     9]\n"),
        ("py aligned under its bracket, a comment (reported)", "k.py", "a = [1,  # one\n     2]\n", "9",
         "a = [1,  # one\n     2,\n     9]\n"),
        ("toml aligned under its bracket", "k.toml", "a = [1,\n     2]\n", "9", "a = [1,\n     2,\n     9]\n"),
        ("py two per line stays inline", "k.py", "a = [1, 2,\n     3]\n", "9", "a = [1, 2,\n     3, 9]\n"),
    ]
    for label, name, source, value, expected in lists:
        _exact(f"final review append_to_array ({label})",
               _edit_result(name, source, lambda a: a.append_to_array("a", value)), expected)

    # Content that starts a byte order mark file with its own mark leaves
    # one mark.
    bom = "\ufeff"
    _exact("final review byte order mark (replace_function with a marked content)",
           _edit_result("k.py", bom + "def f():\n    pass\n", lambda a: a.replace_function("f", bom + "def f():\n    return 1")),
           bom + "def f():\n    return 1\n")
    _exact("final review byte order mark (add_top_level at the top with a marked content)",
           _edit_result("k.py", bom + "def f():\n    pass\n", lambda a: a.add_top_level(bom + "X = 1", "top")),
           bom + "X = 1\n\n\ndef f():\n    pass\n")


# ──────────────────────────────────────────────
# Targets: overloads by parameter types, overload groups, keyword-prefixed
# tags and types, listed targets that resolve
# ──────────────────────────────────────────────


def test_overloaded_targets():
    print("\n═══ targets: C++ and Java overloads named by their parameter types ═══")

    # A name that one scope gives several functions with different
    # parameter types is refused, naming each overload as its target; a
    # last part `name(T1, T2)` picks one by its parameter types as written,
    # without names and default values, whatever the spacing. list_symbols
    # names only the overloads that way.
    java = "class A {\n    int m(int x) { return x; }\n    int m(String s) { return 0; }\n}\n"
    _exact("java overloads: list_symbols", _read_result("K.java", java, lambda a: a.list_symbols()),
           "class A (line 1)\n  method A.m(int) (line 2)\n  method A.m(String) (line 3)")
    _exact("java overloads: the name is refused (reported)",
           _read_result("K.java", java, lambda a: a.read_symbol("A.m")),
           "REFUSED: 'A.m' is overloaded: A.m(int) (line 2), A.m(String) (line 3); add the parameter types.")
    # (target, read_symbol, or None for none found)
    for target, full in [
        ("A.m(String)", "int m(String s) { return 0; }"),
        ("A.m( int )", "int m(int x) { return x; }"),
        ("A.m(long)", None),
        ("A.m()", None),
        ("A.m(int, int)", None),
    ]:
        result = _read_result("K.java", java, lambda a: a.read_symbol(target))
        if full is None:
            check(f"java overloads: read_symbol('{target}') finds none", result, f"Target '{target}' not found")
        else:
            _exact(f"java overloads: read_symbol('{target}')", result, full)
    _exact("java overloads: read_symbol('A.m(int)', 'signature')",
           _read_result("K.java", java, lambda a: a.read_symbol("A.m(int)", "signature")), "int m(int x)")
    _exact("java overloads: read_symbol('A.m(String)', 'interface')",
           _read_result("K.java", java, lambda a: a.read_symbol("A.m(String)", "interface")), "int m(String s)")
    # A name that is not overloaded takes its parameter types too.
    _exact("java: a method that is not overloaded, by its parameter types",
           _read_result("K.java", "class A {\n    void f(int a, String b) {}\n}\n",
                        lambda a: a.read_symbol("A.f(int,String)")), "void f(int a, String b) {}")

    # Java varargs, arrays (either way), generics, qualified names and
    # modifiers; constructors are `A.A(...)`.
    spelled = ("class A {\n    void f(String... a) {}\n    void f(java.util.List<String> l, int[] b) {}\n"
               "    void f(final Map<String, Integer> m, int c[]) {}\n    A(int a) {}\n    A() {}\n}\n")
    _exact("java parameter spellings: list_symbols", _read_result("K.java", spelled, lambda a: a.list_symbols()),
           "class A (line 1)\n  method A.f(String...) (line 2)\n  method A.f(java.util.List<String>, int[]) (line 3)\n"
           "  method A.f(Map<String, Integer>, int[]) (line 4)\n  method A.A(int) (line 5)\n  method A.A() (line 6)")
    for target, full in [
        ("A.f(String ...)", "void f(String... a) {}"),
        ("A.f(String...)", "void f(String... a) {}"),
        ("A.f(java.util.List<String>,int[])", "void f(java.util.List<String> l, int[] b) {}"),
        ("A.f(Map<String,Integer>, int [])", "void f(final Map<String, Integer> m, int c[]) {}"),
        ("A.A()", "A() {}"),
        ("A.A(int)", "A(int a) {}"),
    ]:
        _exact(f"java parameter spellings: read_symbol('{target}')",
               _read_result("K.java", spelled, lambda a: a.read_symbol(target)), full)

    # C++: constructors, out-of-line definitions (`A::A(int)`), operators,
    # const overloads (`A.get(int) const`), references, templates and
    # default values.
    cpp = ("class A {\npublic:\n    A();\n    A(int x);\n    ~A();\n    bool operator==(const A &o) const;\n"
           "    int &get(int i);\n    const int &get(int i) const;\n    void s(const std::string &s, int n = 1);\n"
           "    void s(std::map<int, int> m);\n};\n\nA::A() {}\n\nA::A(int x) {}\n\n"
           "bool A::operator==(const A& o) const { return true; }\n")
    _exact("cpp overloads: list_symbols (reported)", _read_result("k.cpp", cpp, lambda a: a.list_symbols()),
           "class A (line 1)\n  method A.A() (line 3)\n  method A.A(int) (line 4)\n  method A.~A (line 5)\n"
           "  method A.operator== (line 6)\n  method A.get(int) (line 7)\n  method A.get(int) const (line 8)\n"
           "  method A.s(const std::string &, int) (line 9)\n  method A.s(std::map<int, int>) (line 10)\n"
           "function A::A() (line 13)\nfunction A::A(int) (line 15)\nfunction A::operator== (line 17)")
    for target, full in [
        ("A.A(int)", "A(int x);"),
        ("A.A( )", "A();"),
        ("A::A(int)", "A::A(int x) {}"),
        ("A::A()", "A::A() {}"),
        ("A.operator==(const A &)", "bool operator==(const A &o) const;"),
        ("A.operator==(const A&)", "bool operator==(const A &o) const;"),
        ("A.operator ==", "bool operator==(const A &o) const;"),
        ("A::operator==(const A &)", "bool A::operator==(const A& o) const { return true; }"),
        ("operator==", "bool A::operator==(const A& o) const { return true; }"),
        ("A.get(int)", "int &get(int i);"),
        ("A.get(int) const", "const int &get(int i) const;"),
        ("A.s(const std::string&, int)", "void s(const std::string &s, int n = 1);"),
        ("A.s(const std::string &,int)", "void s(const std::string &s, int n = 1);"),
        ("A.s(std::map<int,int>)", "void s(std::map<int, int> m);"),
        ("A.~A()", "~A();"),
        ("A.s(std::string)", None),
        ("A.get(int) volatile", None),
    ]:
        result = _read_result("k.cpp", cpp, lambda a: a.read_symbol(target))
        if full is None:
            check(f"cpp overloads: read_symbol('{target}') finds none", result, f"Target '{target}' not found")
        else:
            _exact(f"cpp overloads: read_symbol('{target}')", result, full)
    _exact("cpp overloads: read_symbol('A') is the class",
           _read_result("k.cpp", cpp, lambda a: a.read_symbol("A")), cpp[: cpp.index("};") + 2])
    for target, overloads in [
        ("A.A", "A.A() (line 3), A.A(int) (line 4)"),
        ("A::A", "A::A() (line 13), A::A(int) (line 15)"),
        ("A.get", "A.get(int) (line 7), A.get(int) const (line 8)"),
        ("A.s", "A.s(const std::string &, int) (line 9), A.s(std::map<int, int>) (line 10)"),
    ]:
        _exact(f"cpp overloads: '{target}' is refused",
               _read_result("k.cpp", cpp, lambda a: a.read_symbol(target)),
               f"REFUSED: '{target}' is overloaded: {overloads}; add the parameter types.")

    # Every tool that takes a target takes the parameter types.
    jsrc = ("class A {\n    // Doubles.\n    int m(int x) {\n        x++;\n        return x * 2;\n    }\n\n"
            "    int m(String s) {\n        return 0;\n    }\n}\n")
    one = "    // Doubles.\n    int m(int x) {\n        x++;\n        return x * 2;\n    }\n"
    two = "    int m(String s) {\n        return 0;\n    }\n"
    # (tool, target, other arguments, keyword arguments, expected file text)
    edits = [
        ("replace_function", "A.m(String)", ("int m(String s) {\n    return 1;\n}",), {},
         jsrc.replace(two, two.replace("0", "1"))),
        ("replace_function_body", "A.m(String)", ("return 1;",), {}, jsrc.replace(two, two.replace("0", "1"))),
        ("replace_in_body", "A.m(int)", ("x * 2", "x * 3"), {}, jsrc.replace(one, one.replace("x * 2", "x * 3"))),
        ("insert_in_body", "A.m(String)", ("log();",), {"at": "top"},
         jsrc.replace(two, two.replace("        return", "        log();\n        return"))),
        ("delete_in_body", "A.m(int)", ("        x++;\n",), {}, jsrc.replace(one, one.replace("        x++;\n", ""))),
        ("replace_signature", "A.m(String)", ("int m(CharSequence s)",), {},
         jsrc.replace("int m(String s)", "int m(CharSequence s)")),
        ("add_parameter", "A.m(String)", ("int n",), {}, jsrc.replace("int m(String s)", "int m(String s, int n)")),
        ("remove_parameter", "A.m(int)", ("x",), {}, jsrc.replace("int m(int x)", "int m()")),
        ("delete_symbol", "A.m(int)", (), {}, jsrc.replace(one + "\n", "")),
        ("insert_sibling", "A.m(String)", ("int k() {\n    return 2;\n}", "before"), {},
         jsrc.replace(two, "    int k() {\n        return 2;\n    }\n\n" + two)),
        ("edit_leading_comment", "A.m(String)", ("add", "// Zero."), {}, jsrc.replace(two, "    // Zero.\n" + two)),
        ("edit_leading_comment", "A.m(int)", ("remove",), {}, jsrc.replace("    // Doubles.\n", "")),
    ]
    for tool, target, args, kwargs, expected in edits:
        _exact(f"java overloads: {tool}('{target}')",
               _edit_result("K.java", jsrc, lambda a: getattr(a, tool)(target, *args, **kwargs)), expected)
        _refused(f"java overloads: {tool}('A.m')",
                 _edit_result("K.java", jsrc, lambda a: getattr(a, tool)("A.m", *args, **kwargs)),
                 "REFUSED: 'A.m' is overloaded: A.m(int) (line 3), A.m(String) (line 8); add the parameter types.")
    # (label, edit, expected file text)
    cpp_edits = [
        ("delete_symbol of an out-of-line constructor", lambda a: a.delete_symbol("A::A(int)"),
         cpp.replace("A::A(int x) {}\n\n", "")),
        ("add_parameter to a constructor", lambda a: a.add_parameter("A.A(int)", "int y"),
         cpp.replace("A(int x);", "A(int x, int y);")),
        ("edit_leading_comment on a const overload", lambda a: a.edit_leading_comment("A.get(int) const", "add", "// Reads."),
         cpp.replace("    const int &get", "    // Reads.\n    const int &get")),
        ("replace_signature of an overload", lambda a: a.replace_signature("A.s(std::map<int, int>)", "void s(std::map<int, long> m)"),
         cpp.replace("std::map<int, int> m", "std::map<int, long> m")),
        ("replace_function of an operator", lambda a: a.replace_function("A::operator==(const A&)", "bool A::operator==(const A& o) const { return false; }"),
         cpp.replace("{ return true; }", "{ return false; }")),
    ]
    for label, action, expected in cpp_edits:
        _exact(f"cpp overloads: {label}", _edit_result("k.cpp", cpp, action), expected)

    # Overloads by qualified name, prototypes, templates and free
    # functions; a name that names functions of different classes is
    # ambiguous, as one of them is no overload of another.
    # (label, file name, source, list_symbols, [(target, read_symbol or refusal)])
    cases = [
        ("cpp out-of-line definitions of two classes", "k.cpp", "int A::g() { return 1; }\nint B::g() { return 2; }\n",
         "function A::g (line 1)\nfunction B::g (line 2)",
         [("g", "REFUSED: 'g' is ambiguous: A::g (line 1), B::g (line 2); use one of these targets."),
          ("B::g", "int B::g() { return 2; }"), ("A::g()", "int A::g() { return 1; }")]),
        ("cpp free overloads", "k.cpp", "void g(int) {}\nvoid g(double) {}\n",
         "function g(int) (line 1)\nfunction g(double) (line 2)",
         [("g(double)", "void g(double) {}"),
          ("g", "REFUSED: 'g' is overloaded: g(int) (line 1), g(double) (line 2); add the parameter types.")]),
        ("cpp a prototype and the definition of another overload", "k.cpp", "int f(int);\nint f(double x) { return 0; }\n",
         "function f(int) (line 1)\nfunction f(double) (line 2)",
         [("f(int)", "int f(int);"), ("f(double)", "int f(double x) { return 0; }")]),
        ("cpp a prototype and its definition", "k.cpp", "int f(int);\nint f(int x) { return x; }\n",
         "function f (line 2)", [("f", "int f(int x) { return x; }"), ("f(int)", "int f(int x) { return x; }")]),
        ("cpp a template and an overload", "k.cpp", "template <class T>\nT id(T x) { return x; }\nint id(int x) { return x; }\n",
         "function id(T) (line 1)\nfunction id(int) (line 3)",
         [("id(T)", "template <class T>\nT id(T x) { return x; }"), ("id(int)", "int id(int x) { return x; }")]),
        ("cpp variadic and function pointer parameters", "k.cpp",
         "void h(int a, ...);\nvoid h(int (*cb)(int), char *argv[]);\n",
         "function h(int, ...) (line 1)\nfunction h(int (*)(int), char *[]) (line 2)",
         [("h(int,...)", "void h(int a, ...);"), ("h(int(*)(int), char*[])", "void h(int (*cb)(int), char *argv[]);")]),
        ("cpp methods in a namespace", "k.cpp", "namespace n {\nvoid f(int);\nvoid f(long);\n}\n",
         "namespace n (line 1)\n  function n.f(int) (line 2)\n  function n.f(long) (line 3)",
         [("n.f(long)", "void f(long);"),
          ("n.f", "REFUSED: 'n.f' is overloaded: n.f(int) (line 2), n.f(long) (line 3); add the parameter types.")]),
        ("c (void) is no parameters", "k.c", "int f(void);\nint f(void) { return 0; }\n",
         "function f (line 2)", [("f(void)", "int f(void) { return 0; }"), ("f()", "int f(void) { return 0; }")]),
        ("java field and method sharing a name (reported)", "K.java",
         "class A {\n    int x;\n    int x() { return x; }\n}\n",
         "class A (line 1)\n  field A.x (line 2)\n  method A.x() (line 3)",
         [("A.x", "int x;"), ("A.x()", "int x() { return x; }")]),
        ("java field and overloaded methods sharing a name", "K.java",
         "class A {\n    int x;\n    int x() { return x; }\n    void x(int v) { x = v; }\n}\n",
         "class A (line 1)\n  field A.x (line 2)\n  method A.x() (line 3)\n  method A.x(int) (line 4)",
         [("A.x", "int x;"), ("A.x()", "int x() { return x; }"), ("A.x(int)", "void x(int v) { x = v; }")]),
        ("c macro and function sharing a name", "k.c", "#define size 3\nint size(void);\n",
         "macro size (line 1)\nfunction size() (line 2)",
         [("size", "#define size 3"), ("size()", "int size(void);")]),
        ("cpp call operator overloads", "k.cpp",
         "struct A {\n    int operator()(int x);\n    int operator()(int x, int y);\n    int operator()();\n};\n",
         "struct A (line 1)\n  method A.operator()(int) (line 2)\n  method A.operator()(int, int) (line 3)\n"
         "  method A.operator()() (line 4)",
         [("A.operator() (int, int)", "int operator()(int x, int y);"), ("A.operator()()", "int operator()();"),
          ("A.operator()", "REFUSED: 'A.operator()' is overloaded: A.operator()(int) (line 2), A.operator()(int, int) "
           "(line 3), A.operator()() (line 4); add the parameter types.")]),
        ("cpp overloads by ref-qualifier", "k.cpp", "struct S {\n  int &g() &;\n  int g() &&;\n};\n",
         "struct S (line 1)\n  method S.g() & (line 2)\n  method S.g() && (line 3)",
         [("S.g() &&", "int g() &&;"), ("S.g()&", "int &g() &;"),
          ("S.g()", "REFUSED: 'S.g()' is overloaded: S.g() & (line 2), S.g() && (line 3); add the method qualifiers.")]),
        ("cpp out-of-line template overloads", "k.cpp",
         "template <class T>\nvoid Box<T>::f(T x) {}\ntemplate <class T>\nvoid Box<T>::f(int x) {}\n",
         "function Box::f(T) (line 1)\nfunction Box::f(int) (line 3)",
         [("Box::f(int)", "template <class T>\nvoid Box<T>::f(int x) {}"), ("f(T)", "template <class T>\nvoid Box<T>::f(T x) {}")]),
        ("cpp overloads in two blocks of a namespace", "k.cpp", "namespace n {\nvoid f(int);\n}\nnamespace n {\nvoid f(long);\n}\n",
         "namespace n (line 1)\n  function n.f(int) (line 2)\n  function n.f(long) (line 5)",
         [("n.f(long)", "void f(long);"),
          ("n.f", "REFUSED: 'n.f' is overloaded: n.f(int) (line 2), n.f(long) (line 5); add the parameter types.")]),
        ("java interface and enum overloads", "K.java",
         "interface I {\n    void m(int a);\n    void m(String s);\n}\nenum E {\n    A, B;\n    E() {}\n    E(int x) {}\n}\n",
         "interface I (line 1)\n  method I.m(int) (line 2)\n  method I.m(String) (line 3)\nenum E (line 5)\n"
         "  method E.E() (line 7)\n  method E.E(int) (line 8)",
         [("I.m(String)", "void m(String s);"), ("E.E(int)", "E(int x) {}")]),
    ]
    for label, name, source, listing, targets in cases:
        _exact(f"{label}: list_symbols", _read_result(name, source, lambda a: a.list_symbols()), listing)
        _listed_targets_resolve(label, name, source)
        for target, full in targets:
            _exact(f"{label}: read_symbol('{target}')", _read_result(name, source, lambda a: a.read_symbol(target)), full)


def test_overload_groups():
    print("\n═══ TS overload signatures and Python @overload stubs are part of their function ═══")

    # The signatures directly before a TS function or method, and the
    # Python @overload stubs before a function, are one symbol with it, as
    # its decorators are: read_symbol shows them, replace_function and
    # delete_symbol take them, insert_sibling(before) and the leading
    # comment go above the first, and replace_signature edits the
    # implementation's signature. Signatures with no implementation
    # (`declare function` twice) are one symbol too.
    ts = "// Echoes.\nfunction f(a: string): void;\nfunction f(a: any) {\n  return a;\n}\n\nconst g = 1;\n"
    group = "function f(a: string): void;\nfunction f(a: any) {\n  return a;\n}"
    _exact("ts overloads: list_symbols", _read_result("k.ts", ts, lambda a: a.list_symbols()),
           "function f (line 2)\nconstant g (line 7)")
    _exact("ts overloads: read_symbol (reported)", _read_result("k.ts", ts, lambda a: a.read_symbol("f")), group)
    _exact("ts overloads: read_symbol signature, the implementation's",
           _read_result("k.ts", ts, lambda a: a.read_symbol("f", "signature")), "function f(a: any)")
    check("ts overloads: round trip", _round_trip("k.ts", ts, "f"), "<unchanged>")
    # (label, file name, source, edit, expected file text)
    edits = [
        ("ts delete_symbol (reported)", "k.ts", ts, lambda a: a.delete_symbol("f"), "const g = 1;\n"),
        ("ts replace_function", "k.ts", ts,
         lambda a: a.replace_function("f", "function f(a: number): number;\nfunction f(a: any) {\n  return a;\n}"),
         ts.replace("a: string): void", "a: number): number")),
        ("ts insert_sibling before", "k.ts", ts, lambda a: a.insert_sibling("f", "const h = 2;", "before"),
         "const h = 2;\n\n" + ts),
        ("ts insert_sibling after", "k.ts", ts, lambda a: a.insert_sibling("f", "const h = 2;", "after"),
         ts.replace("}\n\n", "}\n\nconst h = 2;\n\n")),
        ("ts edit_leading_comment replace", "k.ts", ts, lambda a: a.edit_leading_comment("f", "replace", "// Returns a."),
         ts.replace("// Echoes.", "// Returns a.")),
        ("ts edit_leading_comment add above the first signature", "k.ts", ts.replace("// Echoes.\n", ""),
         lambda a: a.edit_leading_comment("f", "add", "// Returns a."), ts.replace("// Echoes.", "// Returns a.")),
        ("ts replace_signature, the implementation's", "k.ts", ts,
         lambda a: a.replace_signature("f", "function f(a: unknown)"), ts.replace("f(a: any)", "f(a: unknown)")),
        ("ts exported overloads: delete_symbol", "k.ts",
         "export function f(a: string): void;\nexport function f(a: any) {}\n\nlet y = 1;\n",
         lambda a: a.delete_symbol("f"), "let y = 1;\n"),
        ("ts method overloads: delete_symbol (reported)", "k.ts", "class K {\n  m(a: string): void;\n  m(a: any) {}\n}\n",
         lambda a: a.delete_symbol("K.m"), "class K {\n}\n"),
        ("ts method overloads: insert_sibling before", "k.ts",
         "class K {\n  n() {}\n\n  m(a: string): void;\n  m(a: any) {}\n}\n",
         lambda a: a.insert_sibling("K.m", "k() {}", "before"),
         "class K {\n  n() {}\n\n  k() {}\n\n  m(a: string): void;\n  m(a: any) {}\n}\n"),
        ("ts declared overloads: delete_symbol", "k.ts",
         "declare function g(x: number): void;\ndeclare function g(x: string): void;\nlet y = 1;\n",
         lambda a: a.delete_symbol("g"), "let y = 1;\n"),
        ("py @overload stubs: delete_symbol (reported)", "k.py",
         "from typing import overload\n\n\n@overload\ndef f(a: int) -> int: ...\n@overload\ndef f(a: str) -> str: ...\n"
         "def f(a):\n    return a\n\n\ndef g():\n    pass\n",
         lambda a: a.delete_symbol("f"), "from typing import overload\n\n\ndef g():\n    pass\n"),
        ("py @overload stubs: insert_sibling before", "k.py",
         "x = 1\n\n\n@overload\ndef f(a: int) -> int: ...\ndef f(a):\n    return a\n",
         lambda a: a.insert_sibling("f", "y = 2", "before"),
         "x = 1\n\ny = 2\n\n\n@overload\ndef f(a: int) -> int: ...\ndef f(a):\n    return a\n"),
        ("py @overload stubs: replace_signature, the implementation's", "k.py",
         "@overload\ndef f(a: int) -> int: ...\ndef f(a):\n    return a\n",
         lambda a: a.replace_signature("f", "def f(a, b=None):"),
         "@overload\ndef f(a: int) -> int: ...\ndef f(a, b=None):\n    return a\n"),
    ]
    for label, name, source, action, expected in edits:
        _exact(label, _edit_result(name, source, action), expected)

    # (label, file name, source, list_symbols, target, read_symbol, signature)
    reads = [
        ("ts method overloads", "k.ts", "class K {\n  m(a: string): void;\n  m(a: any) {}\n}\n",
         "class K (line 1)\n  method K.m (line 2)", "K.m", "m(a: string): void;\n  m(a: any) {}", "m(a: any)"),
        ("ts exported overloads", "k.ts", "export function f(a: string): void;\nexport function f(a: any) {}\n",
         "function f (line 1)", "f", "export function f(a: string): void;\nexport function f(a: any) {}", "function f(a: any)"),
        ("ts declared overloads without an implementation", "k.ts",
         "declare function g(x: number): void;\ndeclare function g(x: string): void;\n",
         "function g (line 1)", "g", "declare function g(x: number): void;\ndeclare function g(x: string): void;",
         "declare function g(x: number): void"),
        ("ts abstract method overloads", "k.ts",
         "abstract class B {\n  abstract n(a: string): void;\n  abstract n(a: number): void;\n}\n",
         "class B (line 1)\n  method B.n (line 2)", "B.n", "abstract n(a: string): void;\n  abstract n(a: number): void;",
         "abstract n(a: string): void"),
        ("py @overload stubs", "k.py",
         "@overload\ndef f(a: int) -> int: ...\n@overload\ndef f(a: str) -> str: ...\ndef f(a):\n    return a\n",
         "function f (line 1)", "f",
         "@overload\ndef f(a: int) -> int: ...\n@overload\ndef f(a: str) -> str: ...\ndef f(a):\n    return a", "def f(a):"),
        ("py typing.overload stubs of a method", "k.py",
         "class A:\n    @typing.overload\n    def m(self, a: int) -> int: ...\n    @typing.overload\n"
         "    def m(self, a: str) -> str: ...\n    def m(self, a):\n        return a\n",
         "class A (line 1)\n  method A.m (line 2)", "A.m",
         "@typing.overload\n    def m(self, a: int) -> int: ...\n    @typing.overload\n    def m(self, a: str) -> str: ...\n"
         "    def m(self, a):\n        return a", "def m(self, a):"),
        ("py @overload stubs without an implementation", "k.py",
         "@overload\ndef f(a: int) -> int: ...\n@overload\ndef f(a: str) -> str: ...\n",
         "function f (line 1)", "f", "@overload\ndef f(a: int) -> int: ...\n@overload\ndef f(a: str) -> str: ...",
         "def f(a: int) -> int:"),
        ("py @overload stubs of a static method", "k.py",
         "class A:\n    @overload\n    @staticmethod\n    def m(a: int) -> int: ...\n    @staticmethod\n    def m(a):\n"
         "        return a\n\n    def n(self):\n        pass\n",
         "class A (line 1)\n  method A.m (line 2)\n  method A.n (line 9)", "A.m",
         "@overload\n    @staticmethod\n    def m(a: int) -> int: ...\n    @staticmethod\n    def m(a):\n        return a",
         "def m(a):"),
        ("py @overload stubs over several lines (h11, cryptography)", "k.py",
         "class C:\n    @overload\n    def send(self, event: Closed) -> None:\n        ...\n\n    @typing.overload\n"
         "    def send(\n        self,\n        event: Data,\n    ) -> bytes: ...\n\n    def send(self, event):\n"
         "        \"\"\"Send it.\"\"\"\n        return b''\n",
         "class C (line 1)\n  method C.send (line 2)", "C.send",
         "@overload\n    def send(self, event: Closed) -> None:\n        ...\n\n    @typing.overload\n    def send(\n"
         "        self,\n        event: Data,\n    ) -> bytes: ...\n\n    def send(self, event):\n        \"\"\"Send it.\"\"\"\n"
         "        return b''", "def send(self, event):"),
        ("ts overloads in a namespace, a comment between", "k.ts",
         "namespace N {\n  export function f(a: string): void;\n  // The implementation.\n  export function f(a: any) {}\n}\n",
         "namespace N (line 1)\n  function N.f (line 2)", "N.f",
         "export function f(a: string): void;\n  // The implementation.\n  export function f(a: any) {}", "function f(a: any)"),
    ]
    for label, name, source, listing, target, full, signature in reads:
        _exact(f"{label}: list_symbols", _read_result(name, source, lambda a: a.list_symbols()), listing)
        _listed_targets_resolve(label, name, source)
        _exact(f"{label}: read_symbol", _read_result(name, source, lambda a: a.read_symbol(target)), full)
        _exact(f"{label}: read_symbol signature", _read_result(name, source, lambda a: a.read_symbol(target, "signature")),
               signature)
        check(f"{label}: round trip", _round_trip(name, source, target), "<unchanged>")
        check(f"{label}: round trip (crlf)", _round_trip(name, source, target, "\r\n"), "<unchanged>")

    # Python redefinitions of a name are left as they were: each is listed,
    # and the name targets the first (reported).
    redefined = "def f():\n    return 1\n\n\ndef f():\n    return 2\n"
    _exact("py redefinition: list_symbols (reported)", _read_result("k.py", redefined, lambda a: a.list_symbols()),
           "function f (line 1)\nfunction f (line 5)")
    _exact("py redefinition: read_symbol is the first (reported)",
           _read_result("k.py", redefined, lambda a: a.read_symbol("f")), "def f():\n    return 1")


def test_keyword_targets():
    print("\n═══ targets: `struct stat`, `type User`: tags and types that share a name with a value ═══")

    # A C/C++ struct, union, enum or class that shares its name with a
    # function, variable or typedef is the target of `struct stat` (`union
    # u`, `enum e`, `class C`), the name alone being the other symbol's,
    # and list_symbols lists it so; alone, the name targets it as before.
    # A TS type alias or interface that shares its name with a value
    # (`const User`) is `type User` or `interface User`, the name alone
    # being the value's. A dotted path takes the keyword in front of it
    # all: `type N.User`, `struct outer.inner`.
    stat = "struct stat {\n    int size;\n};\nint stat(const char *path, struct stat *st);\n"
    tsuser = "const User = { a: 1 };\ntype User = { a: number };\n"
    zod = (
        "import { z } from 'zod';\n\n"
        "export const User = z.object({ name: z.string() });\n\n"
        "/** The user type. */\n"
        "export type User = z.infer<typeof User>;\n"
    )
    props = "export interface Props {\n  a: number;\n}\nexport const Props = (p: Props) => p.a;\n"
    nested = "struct outer {\n    struct inner {\n        int a;\n    } x;\n    int inner;\n};\n"
    # (label, file name, source, list_symbols, [(target, read_symbol, or None for none found)])
    cases = [
        ("c struct and function (reported)", "k.c", stat,
         "struct struct stat (line 1)\n  field stat.size (line 2)\nfunction stat (line 4)",
         [("stat", "int stat(const char *path, struct stat *st);"), ("struct stat", "struct stat {\n    int size;\n};"),
          ("stat.size", "int size;"), ("struct  stat", "struct stat {\n    int size;\n};"), ("union stat", None)]),
        ("cpp struct and function", "k.cpp", stat,
         "struct struct stat (line 1)\n  field stat.size (line 2)\nfunction stat (line 4)",
         [("stat", "int stat(const char *path, struct stat *st);"), ("struct stat", "struct stat {\n    int size;\n};"),
          ("class stat", None)]),
        ("c struct alone", "k.c", "struct S {\n    int a;\n};\n", "struct S (line 1)\n  field S.a (line 2)",
         [("S", "struct S {\n    int a;\n};"), ("struct S", "struct S {\n    int a;\n};")]),
        ("c union and enum", "k.c", "union u {\n    int a;\n};\nint u;\nenum e { X };\nint e(void);\n",
         "union union u (line 1)\n  field u.a (line 2)\nvariable u (line 4)\nenum enum e (line 5)\nfunction e (line 6)",
         [("union u", "union u {\n    int a;\n};"), ("u", "int u;"), ("enum e", "enum e { X };"), ("e", "int e(void);")]),
        ("c typedef before its struct (reported)", "k.c", "typedef struct Node Node;\n\nstruct Node {\n    Node *next;\n};\n",
         "type Node (line 1)\nstruct struct Node (line 3)\n  field Node.next (line 4)",
         [("Node", "typedef struct Node Node;"), ("struct Node", "struct Node {\n    Node *next;\n};"),
          ("Node.next", "Node *next;")]),
        ("c typedef of a struct of its name", "k.c", "typedef struct N {\n    int v;\n} N;\n",
         "struct N (line 1)\n  field N.v (line 2)",
         [("N", "typedef struct N {\n    int v;\n} N;"), ("struct N", "typedef struct N {\n    int v;\n} N;")]),
        ("c nested struct and field of one name", "k.c", nested,
         "struct outer (line 1)\n  struct struct outer.inner (line 2)\n    field outer.inner.a (line 3)\n"
         "  field outer.x (line 2)\n  field outer.inner (line 5)",
         [("outer.inner", "int inner;"), ("struct outer.inner", "struct inner {\n        int a;\n    } x;"),
          ("outer.inner.a", "int a;")]),
        ("cpp class and variable", "k.cpp", "class C {};\nint C;\n", "class class C (line 1)\nvariable C (line 2)",
         [("class C", "class C {};"), ("C", "int C;"), ("struct C", None)]),
        ("ts type and value (reported)", "k.ts", tsuser, "constant User (line 1)\ntype type User (line 2)",
         [("User", "const User = { a: 1 };"), ("type User", "type User = { a: number };"), ("interface User", None)]),
        ("ts zod pattern (reported)", "k.ts", zod, "constant User (line 3)\ntype type User (line 6)",
         [("User", "export const User = z.object({ name: z.string() });"),
          ("type User", "export type User = z.infer<typeof User>;")]),
        ("ts interface and function", "k.ts", props, "interface interface Props (line 1)\nfunction Props (line 4)",
         [("Props", "export const Props = (p: Props) => p.a;"),
          ("interface Props", "export interface Props {\n  a: number;\n}")]),
        ("ts three declarations", "k.ts", "const U = 1;\ntype U = number;\ninterface U {}\n",
         "constant U (line 1)\ntype type U (line 2)\ninterface interface U (line 3)",
         [("U", "const U = 1;"), ("type U", "type U = number;"), ("interface U", "interface U {}")]),
        ("ts types alone", "k.ts", "type T = number;\ninterface I {}\n", "type T (line 1)\ninterface I (line 2)",
         [("T", "type T = number;"), ("type T", "type T = number;"), ("I", "interface I {}"),
          ("interface I", "interface I {}"), ("interface T", None)]),
        ("ts a type and a value in a namespace", "k.ts", "namespace N {\n  export const T = 1;\n  export type T = number;\n}\n",
         "namespace N (line 1)\n  constant N.T (line 2)\n  type type N.T (line 3)",
         [("N.T", "export const T = 1;"), ("type N.T", "export type T = number;")]),
        ("ts class and interface merged", "k.ts", "class A {\n  x = 1;\n}\ninterface A {\n  y: number;\n}\n",
         "class A (line 1)\n  field A.x (line 2)\ninterface interface A (line 4)",
         [("A", "class A {\n  x = 1;\n}"), ("interface A", "interface A {\n  y: number;\n}")]),
        ("ts declared const and type", "k.ts", "declare const X: number;\ntype X = string;\n",
         "constant X (line 1)\ntype type X (line 2)",
         [("X", "declare const X: number;"), ("type X", "type X = string;")]),
    ]
    for label, name, source, listing, targets in cases:
        _exact(f"{label}: list_symbols", _read_result(name, source, lambda a: a.list_symbols()), listing)
        _listed_targets_resolve(label, name, source)
        for target, full in targets:
            result = _read_result(name, source, lambda a: a.read_symbol(target))
            if full is None:
                check(f"{label}: read_symbol('{target}') finds none", result, f"Target '{target}' not found")
            else:
                _exact(f"{label}: read_symbol('{target}')", result, full)

    # The keyword target works with the other tools; the name alone edits
    # the value.
    # (label, file name, source, edit, expected file text)
    edits = [
        ("c delete_symbol of the struct", "k.c", stat, lambda a: a.delete_symbol("struct stat"),
         "int stat(const char *path, struct stat *st);\n"),
        ("c delete_symbol of the function", "k.c", stat, lambda a: a.delete_symbol("stat"), "struct stat {\n    int size;\n};\n"),
        ("c add_field to the struct", "k.c", stat, lambda a: a.add_field("struct stat", "int mode;"),
         stat.replace("{\n", "{\n    int mode;\n", 1)),
        ("c add_method to the struct's fields", "k.c", stat, lambda a: a.add_method("struct stat", "int mode;"),
         stat.replace("int size;\n", "int size;\n\n    int mode;\n")),
        ("c replace_function of the struct", "k.c", stat,
         lambda a: a.replace_function("struct stat", "struct stat {\n    long size;\n};"), stat.replace("int size", "long size")),
        ("c edit_leading_comment on the struct", "k.c", stat,
         lambda a: a.edit_leading_comment("struct stat", "add", "// File status."), "// File status.\n" + stat),
        ("c insert_sibling after the struct", "k.c", stat, lambda a: a.insert_sibling("struct stat", "int n;", "after"),
         stat.replace("};\n", "};\n\nint n;\n\n")),
        ("c add_parameter to the function", "k.c", stat, lambda a: a.add_parameter("stat", "int flags"),
         stat.replace("struct stat *st)", "struct stat *st, int flags)")),
        ("ts delete_symbol of the type (reported)", "k.ts", zod, lambda a: a.delete_symbol("type User"),
         "import { z } from 'zod';\n\nexport const User = z.object({ name: z.string() });\n"),
        ("ts delete_symbol of the value", "k.ts", tsuser, lambda a: a.delete_symbol("User"), "type User = { a: number };\n"),
        ("tsx replace_function of the type", "k.tsx", zod,
         lambda a: a.replace_function("type User", "export type User = {};"), zod.replace("z.infer<typeof User>", "{}")),
        ("ts add_field to the interface", "k.ts", props, lambda a: a.add_field("interface Props", "b: string;"),
         props.replace("{\n  a", "{\n  b: string;\n  a")),
        ("ts edit_leading_comment on the type", "k.ts", tsuser,
         lambda a: a.edit_leading_comment("type User", "add", "// The shape."), tsuser.replace("type", "// The shape.\ntype")),
    ]
    for label, name, source, action, expected in edits:
        _exact(label, _edit_result(name, source, action), expected)
    for label, name, source, target in [("c struct", "k.c", stat, "struct stat"), ("ts type", "k.ts", zod, "type User"),
                                        ("ts interface", "k.ts", props, "interface Props")]:
        check(f"{label}: round trip of '{target}'", _round_trip(name, source, target), "<unchanged>")
    _exact("c struct: read_symbol('struct stat', 'signature')",
           _read_result("k.c", stat, lambda a: a.read_symbol("struct stat", "signature")), "struct stat")
    _exact("c struct: read_symbol('struct stat', 'interface')",
           _read_result("k.c", stat, lambda a: a.read_symbol("struct stat", "interface")), "struct stat {\n    int size;\n};")


def test_listed_targets_everywhere():
    print("\n═══ list_symbols: every listed name targets its own entry, in every language ═══")

    # A C++ definition outside its class is listed under its qualified
    # name (`A::A`, `A::B::f`, `A::n`), which targets it; its last name
    # alone, or a shorter qualified name (`B::f`), still finds it when no
    # symbol of the scope is named so. Alternative definitions in `#ifdef`
    # branches and repeated declarations are listed once, at the first,
    # which the name targets; so is a TS getter, whose setter no target
    # reaches.
    # (label, file name, source, list_symbols, [(target, read_symbol)])
    cases = [
        ("cpp out-of-line constructor (reported)", "k.cpp", "class A {\npublic:\n  A();\n};\nA::A() {}\n",
         "class A (line 1)\n  method A.A (line 3)\nfunction A::A (line 5)",
         [("A::A", "A::A() {}"), ("A.A", "A();"), ("A", "class A {\npublic:\n  A();\n};")]),
        ("cpp nested qualified name (reported)", "k.cpp", "int A::B::f() { return 1; }\n", "function A::B::f (line 1)",
         [("A::B::f", "int A::B::f() { return 1; }"), ("B::f", "int A::B::f() { return 1; }"),
          ("f", "int A::B::f() { return 1; }"), ("C::f", "REFUSED: Target 'C::f' not found")]),
        ("cpp out-of-line definitions beside a free function", "k.cpp",
         "class A {\n  int g();\n};\nint A::g() { return 1; }\nint g() { return 2; }\n",
         "class A (line 1)\n  method A.g (line 2)\nfunction A::g (line 4)\nfunction g (line 5)",
         [("g", "int g() { return 2; }"), ("A::g", "int A::g() { return 1; }"), ("A.g", "int g();")]),
        ("cpp static member definition", "k.cpp", "struct A {\n    static int n;\n};\nint A::n = 0;\n",
         "struct A (line 1)\n  field A.n (line 2)\nvariable A::n (line 4)",
         [("A::n", "int A::n = 0;"), ("n", "int A::n = 0;"), ("A.n", "static int n;")]),
        ("cpp destructor and conversion defined outside", "k.cpp",
         "struct A {\n    ~A();\n    operator bool() const;\n};\nA::~A() {}\nA::operator bool() const { return true; }\n",
         "struct A (line 1)\n  method A.~A (line 2)\n  method A.operator bool (line 3)\nfunction A::~A (line 5)\n"
         "function A::operator bool (line 6)",
         [("A::~A", "A::~A() {}"), ("~A", "A::~A() {}"), ("A::operator bool", "A::operator bool() const { return true; }"),
          ("A::operator bool()", "A::operator bool() const { return true; }")]),
        # A definition outside the conditionals is the one compiled, so it
        # is the target, not one in `#ifdef X` (or `#if 0`) before it.
        ("c definition in #ifdef and outside (reported)", "k.c",
         "#ifdef X\nint f(void) { return 1; }\n#endif\nint f(void) { return 2; }\n",
         "function f (line 4)", [("f", "int f(void) { return 2; }")]),
        ("c alternatives in #ifdef and #else", "k.c",
         "#ifdef X\nint f(void) { return 1; }\n#else\nint f(void) { return 2; }\n#endif\n",
         "function f (line 2)", [("f", "int f(void) { return 1; }")]),
        ("c repeated typedef", "k.c", "typedef int T;\ntypedef int T;\n", "type T (line 1)", [("T", "typedef int T;")]),
        ("cpp repeated prototype", "k.cpp", "void f(int);\nvoid f(int);\n", "function f (line 1)", [("f", "void f(int);")]),
        ("ts getter and setter", "k.ts", "class A {\n  get x() { return 1; }\n  set x(v) {}\n}\n",
         "class A (line 1)\n  method A.x (line 2)", [("A.x", "get x() { return 1; }")]),
    ]
    for label, name, source, listing, targets in cases:
        _exact(f"{label}: list_symbols", _read_result(name, source, lambda a: a.list_symbols()), listing)
        _listed_targets_resolve(label, name, source)
        for target, full in targets:
            result = _read_result(name, source, lambda a: a.read_symbol(target))
            if full.startswith("REFUSED"):
                check(f"{label}: read_symbol('{target}')", result, full)
            else:
                _exact(f"{label}: read_symbol('{target}')", result, full)

    # One file per language with the shapes above and the usual ones.
    corpus = [
        ("python", "k.py",
         "import typing\nfrom typing import overload\n\n\nclass A:\n    \"\"\"Doc.\"\"\"\n\n    @overload\n"
         "    def m(self, a: int) -> int: ...\n    @overload\n    def m(self, a: str) -> str: ...\n    def m(self, a):\n"
         "        return a\n\n    @property\n    def p(self):\n        return 1\n\n    class B:\n        def n(self):\n"
         "            pass\n\n\n@typing.overload\ndef f(a: int) -> int: ...\n@typing.overload\ndef f(a: str) -> str: ...\n"
         "def f(a):\n    return a\n\n\nasync def g():\n    pass\n"),
        ("javascript", "k.js",
         "class A {\n  constructor() {}\n  m() {\n    return 1;\n  }\n  static s() {}\n  get x() {\n    return 1;\n  }\n}\n\n"
         "function f() {}\n\nfunction* gen() {}\n\nconst h = () => 1;\n\nexport default class {}\n"),
        ("typescript", "k.ts",
         "export function f(a: string): void;\nexport function f(a: any) {\n  return a;\n}\n\n"
         "declare function g(x: number): void;\ndeclare function g(x: string): void;\n\n"
         "const User = { a: 1 };\ntype User = { a: number };\n\ninterface Props {\n  a: number;\n}\n"
         "const Props = (p: Props) => p.a;\n\nclass K {\n  m(a: string): void;\n  m(a: any) {}\n  get v() {\n    return 1;\n  }\n}\n\n"
         "abstract class B {\n  abstract n(): void;\n}\n\nnamespace N {\n  export const T = 1;\n  export type T = number;\n"
         "  export class C {}\n}\n\nenum E {\n  X,\n}\n\ntype Only = string;\n\ninterface I {}\n"),
        ("c", "k.c",
         "#include <stdio.h>\n#define M 1\n\nstruct stat {\n    int size;\n};\nint stat(const char *path, struct stat *st);\n\n"
         "typedef struct Node Node;\nstruct Node {\n    Node *next;\n};\n\ntypedef struct N {\n    int v;\n} N;\n\n"
         "union u {\n    int a;\n};\nint u;\n\nenum e { X };\nint e(void);\n\n"
         "#ifdef X\nint f(void) { return 1; }\n#endif\nint f(void) { return 2; }\n\n"
         "typedef int T;\ntypedef int T;\n\nint g(int);\nint g(int x) { return x; }\n\nextern int v;\nint v = 1;\n"),
        ("c header", "k.h",
         "#ifndef H\n#define H\nstruct stat {\n    int size;\n};\nint stat(const char *path);\nint h(int);\n"
         "typedef struct { int x; } P, *PP;\n#endif\n"),
        ("cpp", "k.cpp",
         "namespace ns {\nclass A {\npublic:\n    A();\n    A(int x);\n    ~A();\n    bool operator==(const A &o) const;\n"
         "    int &get(int i);\n    const int &get(int i) const;\n    template <class T>\n    T t(T x) { return x; }\n};\n}\n\n"
         "ns::A::A() {}\n\nns::A::A(int x) {}\n\nint A::B::f() { return 1; }\n\nstruct stat {\n    int size;\n};\n"
         "int stat(const char *p);\n\nclass C {};\nint C;\n\nvoid o(int) {}\nvoid o(double) {}\n\n"
         "struct S {\n    static int n;\n};\nint S::n = 0;\n"),
        ("ruby", "k.rb",
         "module M\n  class A\n    def m\n    end\n\n    private def p\n    end\n\n    class << self\n      def s\n      end\n"
         "    end\n  end\n\n  def self.f\n  end\nend\n"),
        ("go", "k.go",
         "package main\n\ntype A struct {\n\tx int\n}\n\nfunc (a *A) M() {}\n\ntype T = int\n\nvar v = 1\n\nconst C = 2\n\n"
         "func f() {}\n"),
        ("java", "K.java",
         "class A {\n    int x;\n\n    int x() {\n        return x;\n    }\n\n    int m(int a) {\n        return a;\n    }\n\n"
         "    int m(String s) {\n        return 0;\n    }\n\n    void v(String... a) {}\n\n    A() {}\n\n    A(int a) {}\n\n"
         "    enum E {\n        P;\n\n        void e() {}\n    }\n\n    interface I {\n        void i();\n    }\n}\n"),
    ]
    for label, name, source in corpus:
        _listed_targets_resolve(f"corpus {label}", name, source)
        check(f"corpus {label}: lists symbols", _read_result(name, source, lambda a: a.list_symbols()), " (line ")


def test_listed_data():
    print("\n═══ list_symbols: module data, class attributes and fields, Ruby constants ═══")

    # Data is listed with the kinds C, C++, Go and Java give it: a Python
    # module-level name is a `variable` and a class attribute a `field`, a
    # JS/TS `const` a `constant` and a `let` or `var` a `variable` (each
    # name of a declaration of several, one bound to a function being a
    # `function`), a JS/TS class field a `field`, a Ruby constant a
    # `constant` and a Ruby local a `variable`. A name assigned again is
    # listed once, at the first assignment, which the name targets; the
    # names a pattern binds (`a, b = 1, 2`, `const { p } = o`), which are
    # no targets, and fields named by a string key are not listed.
    # (label, file name, source, list_symbols)
    cases = [
        ("python module variables and class attributes (reported)", "d.py",
         "import os\n\nX = 1\nY: int = 2\na, b = 1, 2\n__all__ = [\"A\"]\n\n\nclass A:\n    \"\"\"Doc.\"\"\"\n\n"
         "    x = 1\n    y: int\n\n    def m(self):\n        z = 1\n        return z\n\n\nX = 3\n",
         "variable X (line 3)\nvariable Y (line 4)\nvariable __all__ (line 6)\nclass A (line 9)\n  field A.x (line 12)\n"
         "  field A.y (line 13)\n  method A.m (line 15)"),
        ("js module constants and variables (reported)", "d.js",
         "const n = 1;\nlet m;\nvar a = 1, b = () => 2;\nconst { p, q } = obj;\nexport const e = 3;\nfunction f() {}\n",
         "constant n (line 1)\nvariable m (line 2)\nvariable a (line 3)\nfunction b (line 3)\nconstant e (line 5)\n"
         "function f (line 6)"),
        ("js class fields", "d.js", "class A {\n  x = 1;\n  static #y = 2;\n  'q-r' = 3;\n  m() {}\n}\n",
         "class A (line 1)\n  field A.x (line 2)\n  field A.#y (line 3)\n  method A.m (line 5)"),
        ("ts declarations and class fields (reported)", "d.ts",
         "declare const d: number;\nexport let e = 1;\nnamespace N {\n  export const T = 1;\n}\nabstract class A {\n"
         "  @Input() x: number;\n  declare z: string;\n  abstract w: string;\n  private readonly r = 1;\n  m(): void {}\n}\n",
         "constant d (line 1)\nvariable e (line 2)\nnamespace N (line 3)\n  constant N.T (line 4)\nclass A (line 6)\n"
         "  field A.x (line 7)\n  field A.z (line 8)\n  field A.w (line 9)\n  field A.r (line 10)\n  method A.m (line 11)"),
        ("ts value and type of one name", "d.ts", "const User = { a: 1 };\ntype User = { a: number };\n",
         "constant User (line 1)\ntype type User (line 2)"),
        ("ruby constants and variables (reported)", "d.rb",
         "X = 1\ny = 2\n\nmodule M\n  LIMIT = 10\n\n  class A\n    NAME = <<~EOS\n      text\n    EOS\n\n    def f\n    end\n"
         "  end\nend\n",
         "constant X (line 1)\nvariable y (line 2)\nmodule M (line 4)\n  constant M.LIMIT (line 5)\n  class M.A (line 7)\n"
         "    constant M.A.NAME (line 8)\n    method M.A.f (line 12)"),
    ]
    for label, name, source, listing in cases:
        _exact(f"{label}: list_symbols", _read_result(name, source, lambda a: a.list_symbols()), listing)
        _listed_targets_resolve(label, name, source)
    tsx = "class A {\n  x: number = 1;\n  render() {\n    return <div />;\n  }\n}\n"
    _exact("tsx class field: list_symbols", _read_result("d.tsx", tsx, lambda a: a.list_symbols()),
           "class A (line 1)\n  field A.x (line 2)\n  method A.render (line 3)")
    _listed_targets_resolve("tsx class field", "d.tsx", tsx)

    # JS/TS class fields are targets for every whole-symbol tool: their
    # decorators and the `;` after them are part of them, a comment after
    # them on their line is not, and the other depths refuse them as fields.
    ts = "class A {\n  // The x.\n  @Input() x: number;\n  y = 1; // why\n  m() {}\n}\n"
    reads = [
        ("ts field with its decorator (reported)", "f.ts", ts, "A.x", "full", "@Input() x: number;"),
        ("ts field with a comment after it", "f.ts", ts, "A.y", "full", "y = 1;"),
        ("js private static field", "f.js", "class A {\n  static #y = 2;\n}\n", "A.#y", "full", "static #y = 2;"),
        ("js field without its ;", "f.js", "class A {\n  x = 1\n}\n", "A.x", "full", "x = 1"),
        ("ts field at depth signature", "f.ts", ts, "A.x", "signature",
         _depth_text("A.x", "a field", "signature")),
        ("js field at depth interface", "f.js", "class A {\n  x = 1;\n}\n", "A.x", "interface",
         _depth_text("A.x", "a field", "interface")),
        ("js constant at depth signature", "f.js", "const n = 1;\n", "n", "signature",
         _depth_text("n", "a constant", "signature")),
    ]
    for label, name, source, target, depth, expected in reads:
        _exact(f"read_symbol ({label})", _read_result(name, source, lambda a: a.read_symbol(target, depth)), expected)
    # (label, edit, expected file text)
    edits = [
        ("replace_function keeps the comment after it", lambda a: a.replace_function("A.y", "y = 2;"),
         ts.replace("y = 1;", "y = 2;")),
        ("replace_function with its decorator", lambda a: a.replace_function("A.x", "@Input() x: string;"),
         ts.replace("x: number", "x: string")),
        ("delete_symbol with its decorator and comment", lambda a: a.delete_symbol("A.x"),
         "class A {\n  y = 1; // why\n  m() {}\n}\n"),
        ("insert_sibling after", lambda a: a.insert_sibling("A.y", "z = 3;", "after"),
         "class A {\n  // The x.\n  @Input() x: number;\n  y = 1; // why\n  z = 3;\n\n  m() {}\n}\n"),
        ("insert_sibling before, above its comment", lambda a: a.insert_sibling("A.x", "w = 0;", "before"),
         "class A {\n  w = 0;\n  // The x.\n  @Input() x: number;\n  y = 1; // why\n  m() {}\n}\n"),
        ("edit_leading_comment replace", lambda a: a.edit_leading_comment("A.x", "replace", "// X."),
         ts.replace("// The x.", "// X.")),
        ("edit_leading_comment add", lambda a: a.edit_leading_comment("A.y", "add", "// Y."),
         ts.replace("  y = 1;", "  // Y.\n  y = 1;")),
    ]
    for label, action, expected in edits:
        _exact(f"ts class field: {label}", _edit_result("f.ts", ts, action), expected)
    _exact("js class field: delete_symbol",
           _edit_result("f.js", "class A {\n  x = 1;\n  m() {}\n}\n", lambda a: a.delete_symbol("A.x")),
           "class A {\n  m() {}\n}\n")


def test_depths_agree():
    print("\n═══ read_symbol: depth signature and interface start where depth full does ═══")

    # The signature and interface depths start where depth="full" starts,
    # at the code that wraps the symbol: the key of a closure, a Go `type`
    # (a type in a group is its spec alone), a TS `declare`, a C++ `extern
    # "C"`, a Ruby `private` and the C typedef or declaration a struct is
    # the type of; a typedef of a struct, union or enum without a tag
    # reads as the type it defines. A closure's interface is its signature,
    # as a function's is, and a Ruby endless method's signature ends before
    # its `=`. replace_signature takes the signature back as it is.
    # (label, file name, source, target, full, signature, interface)
    cases = [
        ("js closure (reported)", "c.js", "const app = {\n  handler: () => {\n    return 1;\n  },\n};\n", "app.handler",
         "handler: () => {\n    return 1;\n  }", "handler: () =>", "handler: () =>"),
        ("js closure with an expression body (reported)", "c.js", "const app = {\n  handler: () => 1,\n  other: 1,\n};\n",
         "app.handler", "handler: () => 1", "handler: () =>", "handler: () =>"),
        ("js closure function expression", "c.js",
         "const app = {\n  handler: function (a) {\n    return a;\n  },\n};\n", "app.handler",
         "handler: function (a) {\n    return a;\n  }", "handler: function (a)", "handler: function (a)"),
        ("go closure in a composite literal", "c.go",
         "package main\n\nvar cmd = &Command{\n\tRunE: func(c *Command) error {\n\t\treturn nil\n\t},\n}\n", "cmd.RunE",
         "RunE: func(c *Command) error {\n\t\treturn nil\n\t}", "RunE: func(c *Command) error", "RunE: func(c *Command) error"),
        ("go type in a group (reported)", "c.go", "package main\n\ntype (\n\tA struct{ x int }\n\tB int\n)\n", "A",
         "A struct{ x int }", "A struct", "A struct{ x int }"),
        ("go type in a group with a method", "c.go",
         "package main\n\ntype (\n\tA struct {\n\t\tx int\n\t}\n\tB int\n)\n\nfunc (a *A) M() int {\n\treturn a.x\n}\n", "A",
         "A struct {\n\t\tx int\n\t}", "A struct", "A struct {\n\t\tx int\n\t}\n\nfunc (a *A) M() int ..."),
        ("go type alone", "c.go", "package main\n\ntype A struct {\n\tx int\n}\n", "A",
         "type A struct {\n\tx int\n}", "type A struct", "type A struct {\n\tx int\n}"),
        ("ts declare function", "c.ts", "declare function f(a: number): void;\n", "f",
         "declare function f(a: number): void;", "declare function f(a: number): void", "declare function f(a: number): void"),
        ("ts exported declare function", "c.ts", "export declare function f(a: number): void;\n", "f",
         "export declare function f(a: number): void;", "declare function f(a: number): void",
         "declare function f(a: number): void"),
        ("ts declare class", "c.ts", "declare class A {\n  m(): void;\n}\n", "A",
         "declare class A {\n  m(): void;\n}", "declare class A", "declare class A {\n  m(): void;\n}"),
        ("rb private def (reported)", "c.rb", "class A\n  private def m(x)\n    x\n  end\nend\n", "A.m",
         "private def m(x)\n    x\n  end", "private def m(x)", "private def m(x)"),
        ("rb empty private def", "c.rb", "class A\n  private def m(x)\n  end\nend\n", "A.m",
         "private def m(x)\n  end", "private def m(x)", "private def m(x)"),
        ("rb endless method (reported)", "c.rb", "class A\n  def f = 1\nend\n", "A.f", "def f = 1", "def f", "def f"),
        ("rb endless method with parameters", "c.rb", "class A\n  def f(x) = x + 1\nend\n", "A.f",
         "def f(x) = x + 1", "def f(x)", "def f(x)"),
        ("c typedef struct (reported)", "c.c", "typedef struct N {\n    int a;\n} N;\n", "N",
         "typedef struct N {\n    int a;\n} N;", "typedef struct N", "typedef struct N {\n    int a;\n} N;"),
        ("c typedef struct by its keyword", "c.c", "typedef struct N {\n    int a;\n} N;\n", "struct N",
         "typedef struct N {\n    int a;\n} N;", "typedef struct N", "typedef struct N {\n    int a;\n} N;"),
        ("c typedef of a struct under another name", "c.c", "typedef struct node {\n    int v;\n} Node;\n", "Node",
         "typedef struct node {\n    int v;\n} Node;", "typedef struct node", "typedef struct node {\n    int v;\n} Node;"),
        ("c struct with a declarator", "c.c", "struct S {\n    int a;\n} s;\n", "S",
         "struct S {\n    int a;\n} s;", "struct S", "struct S {\n    int a;\n} s;"),
        ("c anonymous typedef struct (reported)", "c.c", "typedef struct {\n    int x;\n    int y;\n} P;\n", "P",
         "typedef struct {\n    int x;\n    int y;\n} P;", "typedef struct", "typedef struct {\n    int x;\n    int y;\n} P;"),
        ("c anonymous typedef enum", "c.c", "typedef enum {\n    A,\n    B\n} E;\n", "E",
         "typedef enum {\n    A,\n    B\n} E;", "typedef enum", "typedef enum {\n    A,\n    B\n} E;"),
        ("cpp extern \"C\" function", "c.cpp", "extern \"C\" int f(int a) {\n    return a;\n}\n", "f",
         "extern \"C\" int f(int a) {\n    return a;\n}", "extern \"C\" int f(int a)", "extern \"C\" int f(int a)"),
    ]
    for label, name, source, target, full, signature, interface in cases:
        for depth, expected in (("full", full), ("signature", signature), ("interface", interface)):
            _exact(f"{label}: depth={depth}", _read_result(name, source, lambda a: a.read_symbol(target, depth)), expected)
        _exact(f"{label}: replace_signature with the signature read",
               _edit_result(name, source, lambda a: a.replace_signature(target, a.read_symbol(target, "signature"))), source)
    _exact("go type B in a group: depth=interface",
           _read_result("c.go", "package main\n\ntype (\n\tA struct{ x int }\n\tB int\n)\n",
                        lambda a: a.read_symbol("B", "interface")), "B int")

    # A new signature with the wrapping code replaces it, one without keeps it.
    app = "const app = {\n  handler: (a) => {\n    return a;\n  },\n};\n"
    cmd = "package main\n\nvar cmd = &Command{\n\tRunE: func(c *Command) error {\n\t\treturn nil\n\t},\n}\n"
    rb = "class A\n  private def m(x)\n    x\n  end\nend\n"
    # (label, file name, source, target, new signature, expected file text)
    signatures = [
        ("js closure with its key", "c.js", app, "app.handler", "handler: (a, b) =>", app.replace("(a)", "(a, b)")),
        ("js closure, the function only", "c.js", app, "app.handler", "(a, b) =>", app.replace("(a)", "(a, b)")),
        ("js closure renamed", "c.js", app, "app.handler", "onClick: (a) =>", app.replace("handler", "onClick")),
        ("go closure, the function only", "c.go", cmd, "cmd.RunE", "func(c *Command, a []string) error",
         cmd.replace("(c *Command)", "(c *Command, a []string)")),
        ("go closure with its key", "c.go", cmd, "cmd.RunE", "RunE: func() error", cmd.replace("(c *Command)", "()")),
        ("go type keeps its `type`", "c.go", "package main\n\ntype A struct {\n\tx int\n}\n", "A", "B struct",
         "package main\n\ntype B struct {\n\tx int\n}\n"),
        ("ts declare kept", "c.ts", "declare function f(a: number): void;\n", "f", "function f(a: string): void",
         "declare function f(a: string): void;\n"),
        ("rb private kept", "c.rb", rb, "A.m", "def m(x, y)", rb.replace("m(x)", "m(x, y)")),
        ("rb private replaced", "c.rb", rb, "A.m", "protected def m(x)", rb.replace("private", "protected")),
        ("rb endless method", "c.rb", "class A\n  def f = 1\nend\n", "A.f", "def f(y)", "class A\n  def f(y) = 1\nend\n"),
        ("c typedef kept", "c.c", "typedef struct N {\n    int a;\n} N;\n", "N", "struct M",
         "typedef struct M {\n    int a;\n} N;\n"),
        ("c anonymous typedef named", "c.c", "typedef struct {\n    int x;\n} P;\n", "P", "typedef struct P",
         "typedef struct P {\n    int x;\n} P;\n"),
    ]
    for label, name, source, target, new, expected in signatures:
        _exact(f"replace_signature ({label})", _edit_result(name, source, lambda a: a.replace_signature(target, new)), expected)

    # In a Ruby class's interface every method is its signature and ` ...`:
    # an empty one, an endless one, a `private def` and those in `class <<
    # self`, which shows as a block of its own.
    rb_class = (
        "class A\n  X = 1\n  attr_reader :a\n\n  def f(a)\n    a\n  end\n\n  def g; end\n\n  def e\n  end\n\n  def h = 1\n\n"
        "  private def p(x)\n    x\n  end\n\n  class << self\n    def s\n      1\n    end\n  end\n\n  def self.t\n  end\nend\n"
    )
    _exact("rb class interface: empty, endless and private methods (reported)",
           _read_result("c.rb", rb_class, lambda a: a.read_symbol("A", "interface")),
           "class A\n  X = 1\n  attr_reader :a\n  def f(a) ...\n  def g ...\n  def e ...\n  def h ...\n  private def p(x) ...\n"
           "  class << self\n    def s ...\n  end\n  def self.t ...\nend")
    _exact("rb module interface: an empty singleton method",
           _read_result("c.rb", "module M\n  def self.f\n  end\nend\n", lambda a: a.read_symbol("M", "interface")),
           "module M\n  def self.f ...\nend")


def test_js_trailing_comments():
    print("\n═══ JS/TS: a comment after a symbol on its last line is not part of it ═══")

    # tree-sitter-javascript puts a comment that follows a function's `}`
    # on its line, or a class's, a namespace's or a declaration's that has
    # no `;`, inside that symbol. It is a comment after the symbol, as in
    # the other languages: read_symbol leaves it out, replace_function
    # keeps it after the new code (unless the content ends with a comment
    # of its own), and the body tools end at the `}`.
    # (label, source, target, read_symbol)
    cases = [
        ("function (reported)", "function b() {} // old\nfunction c() {}\n", "b", "function b() {}"),
        ("function over several lines", "function b() {\n  return 1;\n} // old\nfunction c() {}\n", "b",
         "function b() {\n  return 1;\n}"),
        ("two comments", "function b() {\n} /* x */ // y\n", "b", "function b() {\n}"),
        ("generator", "function* g() {} // g\n", "g", "function* g() {}"),
        ("exported function", "export function h() {} // h\n", "h", "export function h() {}"),
        ("arrow function", "const f = () => {} // f\n", "f", "const f = () => {}"),
        ("constant without its ;", "const x = 1 // x\n", "x", "const x = 1"),
        ("class", "class A {} // a\n", "A", "class A {}"),
    ]
    for ext in (".js", ".ts"):
        name = "t" + ext
        for label, source, target, full in cases + ([("namespace", "namespace N {} // n\n", "N", "namespace N {}")]
                                                     if ext == ".ts" else []):
            _exact(f"{ext} {label}: read_symbol", _read_result(name, source, lambda a: a.read_symbol(target)), full)
            check(f"{ext} {label}: round trip", _round_trip(name, source, target), "<unchanged>")
        src = "function b() {} // old\nfunction c() {}\n"
        lines = "function b() {\n  x();\n} // old\n"
        # (label, source, edit, expected file text)
        edits = [
            ("replace_function keeps the comment (reported)", src,
             lambda a: a.replace_function("b", "function b() { return 2; }"),
             "function b() { return 2; } // old\nfunction c() {}\n"),
            ("replace_function with a comment of its own", src,
             lambda a: a.replace_function("b", "function b() { return 2; } // new"),
             "function b() { return 2; } // new\nfunction c() {}\n"),
            ("delete_symbol takes its line", src, lambda a: a.delete_symbol("b"), "function c() {}\n"),
            ("replace_function_body", src, lambda a: a.replace_function_body("b", "x();"),
             "function b() {\n  x();\n} // old\nfunction c() {}\n"),
            ("insert_in_body at the bottom", lines, lambda a: a.insert_in_body("b", "y();", at="bottom"),
             "function b() {\n  x();\n  y();\n} // old\n"),
            ("insert_in_body at the top", lines, lambda a: a.insert_in_body("b", "y();", at="top"),
             "function b() {\n  y();\n  x();\n} // old\n"),
            ("insert_sibling after", src, lambda a: a.insert_sibling("b", "function z() {}", "after"),
             "function b() {} // old\n\nfunction z() {}\n\nfunction c() {}\n"),
            ("replace_function of a constant", "const x = 1 // x\n", lambda a: a.replace_function("x", "const x = 2"),
             "const x = 2 // x\n"),
            ("replace_function of a symbol after other code", "x(); function d() {} // d\n",
             lambda a: a.replace_function("d", "function d() { y(); }"), "x(); function d() { y(); } // d\n"),
            ("replace_function of a class", "class A {} // a\nclass B {}\n",
             lambda a: a.replace_function("A", "class A { m() {} }"), "class A { m() {} } // a\nclass B {}\n"),
        ]
        for label, source, action, expected in edits:
            _exact(f"{ext} {label}", _edit_result(name, source, action), expected)
        _refused(f"{ext} replace_in_body: the comment is not in the body",
                 _edit_result(name, src, lambda a: a.replace_in_body("b", "// old", "// new")),
                 "Snippet not found in body of 'b'")
        _exact(f"{ext} class interface without the comment",
               _read_result(name, "class A {\n  m() {}\n} // a\n", lambda a: a.read_symbol("A", "interface")),
               "class A {\n  m() ...\n}")


def test_find_references_line_order():
    print("\n═══ find_references: in line order ═══")

    # (label, file name, source, target, expected)
    cases = [
        ("python (reported)", "r.py", "def f():\n    return x\nx = 1\n", "x", "line 2: return x\nline 3: x = 1"),
        ("python, two on a line", "r.py", "def f():\n    return g(x, x)\nx = 1\n", "x",
         "line 2: return g(x, x)\nline 2: return g(x, x)\nline 3: x = 1"),
        ("js", "r.js", "function f() {\n  return g(x);\n}\nconst x = 1;\n", "x",
         "line 2: return g(x);\nline 4: const x = 1;"),
        ("ts", "r.ts", "class A {\n  m() {\n    return this.x;\n  }\n  x = 1;\n}\n", "x",
         "line 3: return this.x;\nline 5: x = 1;"),
        ("go", "r.go", "package main\n\nfunc f() int {\n\treturn x\n}\n\nvar x = 1\n", "x",
         "line 4: return x\nline 7: var x = 1"),
        ("ruby", "r.rb", "def f\n  g(y)\nend\ny = 1\n", "y", "line 2: g(y)\nline 4: y = 1"),
        ("java", "R.java", "class A {\n    int f() {\n        return x;\n    }\n    int x = 1;\n}\n", "x",
         "line 3: return x;\nline 5: int x = 1;"),
        ("c", "r.c", "int f(void) {\n    return x;\n}\nint x = 1;\n", "x", "line 2: return x;\nline 4: int x = 1;"),
        ("cpp destructor", "r.cpp", "struct A {\n    void f() { this->~A(); }\n    ~A();\n};\nA::~A() {}\n", "~A",
         "line 2: void f() { this->~A(); }\nline 3: ~A();\nline 5: A::~A() {}"),
    ]
    for label, name, source, target, expected in cases:
        _exact(f"find_references ({label})", _read_result(name, source, lambda a: a.find_references(target)), expected)


def test_config_whole_symbol_tools():
    print("\n═══ config files: replace_function, delete_symbol and insert_sibling point to the key tools ═══")

    # A config target is a key path, and its value is what read_symbol
    # reads; the tools that edit whole symbols of source files are refused
    # there, naming the key tool that makes the edit.
    files = [
        ("c.json", '{\n  "a": {\n    "b": 1\n  },\n  "c": 2\n}\n'),
        ("c.yaml", "a:\n  b: 1\nc: 2\n"),
        ("c.yml", "a:\n  b: 1\nc: 2\n"),
        ("c.toml", "[a]\nb = 1\n\n[t]\nc = 2\n"),
    ]
    for name, source in files:
        ext = os.path.splitext(name)[1]
        for target in ("a", "a.b", "missing"):
            _refused(f"{ext} replace_function('{target}') (reported)",
                     _edit_result(name, source, lambda a: a.replace_function(target, "5")),
                     f"replace_function is for symbols of source files, not the keys of a {ext} file: use "
                     f"replace_value to change the value of '{target}', add_key to add a key, or delete_key "
                     "to remove one")
            _refused(f"{ext} delete_symbol('{target}')", _edit_result(name, source, lambda a: a.delete_symbol(target)),
                     f"delete_symbol is for symbols of source files, not the keys of a {ext} file: use "
                     f"delete_key to remove '{target}' with its value")
            _refused(f"{ext} insert_sibling('{target}')",
                     _edit_result(name, source, lambda a: a.insert_sibling(target, "z = 1", "after")),
                     f"insert_sibling is for symbols of source files, not the keys of a {ext} file: use "
                     f"add_key to add a key next to '{target}', its parent's path being the parent_target")
        _exact(f"{ext} read_symbol still reads a value", _read_result(name, source, lambda a: a.read_symbol("a.b")), "1")
        _exact(f"{ext} replace_value makes the edit",
               _edit_result(name, source, lambda a: a.replace_value("a.b", "2")), source.replace("1", "2"))
    _exact("yaml edit_leading_comment still works",
           _edit_result("c.yaml", "a:\n  b: 1\n", lambda a: a.edit_leading_comment("a.b", "add", "# B.")),
           "a:\n  # B.\n  b: 1\n")


def test_replace_value_variables():
    print("\n═══ replace_value on variables, constants and fields: the value alone ═══")

    # The value of a variable, constant or field is what follows its `=`
    # (a C/C++ macro's, its replacement text); replace_value replaces that
    # and nothing else. A name declared without a value gets one where it
    # can have one.
    go = "package main\n\n"
    py_class = "class A:\n    x = 1\n    y: str\n"
    js_class = "class A {\n  x = 1;\n  static y;\n  #p = 1;\n}\n"
    ts_class = "class A {\n  x: number = 1;\n  y?: number;\n  @Input() z: string;\n}\n"
    cpp_struct = "struct S {\n    int a = 1, b;\n    int c{2};\n    int f : 3;\n};\n"
    java_class = "class A {\n    int x = 1, y;\n    int w[];\n}\n"
    # (label, file name, source, target, content, expected file text)
    cases = [
        ("py module variable (reported)", "v.py", "X = 1\nY = 2\n", "X", "2", "X = 2\nY = 2\n"),
        ("py annotated", "v.py", "X: int = 1\n", "X", "2", "X: int = 2\n"),
        ("py annotated without a value", "v.py", "X: int\n", "X", "2", "X: int = 2\n"),
        ("py class attribute", "v.py", py_class, "A.x", "2", "class A:\n    x = 2\n    y: str\n"),
        ("py class attribute without a value", "v.py", py_class, "A.y", '"s"',
         'class A:\n    x = 1\n    y: str = "s"\n'),
        ("py dict variable", "v.py", 'CONFIG = {"a": 1}\n', "CONFIG", '{"b": 2}', 'CONFIG = {"b": 2}\n'),
        ("py value over several lines", "v.py", "X = [\n    1,\n]\nY = 2\n", "X", "[2]", "X = [2]\nY = 2\n"),
        ("py comment after the value", "v.py", "X = 1  # one\n", "X", "2", "X = 2  # one\n"),
        ("py name assigned twice: the first", "v.py", "X = 1\nX = 2\n", "X", "3", "X = 3\nX = 2\n"),
        ("py dict key still works", "v.py", 'C = {"a": 1}\n', 'C."a"', "2", 'C = {"a": 2}\n'),
        ("js const (reported)", "v.js", "const X = 1;\n", "X", "2", "const X = 2;\n"),
        ("js first of two names", "v.js", "let a = 1, b = 2;\n", "a", "3", "let a = 3, b = 2;\n"),
        ("js second of two names", "v.js", "let a = 1, b = 2;\n", "b", "3", "let a = 1, b = 3;\n"),
        ("js let without a value", "v.js", "let x;\n", "x", "2", "let x = 2;\n"),
        ("js name without a value after one with", "v.js", "var a = 1, b;\n", "b", "2", "var a = 1, b = 2;\n"),
        ("js exported", "v.js", "export const X = 1;\n", "X", "2", "export const X = 2;\n"),
        ("js comment after a value with no semicolon", "v.js", "const X = 1 // one\n", "X", "2",
         "const X = 2 // one\n"),
        ("js bound function", "v.js", "const f = () => 1;\n", "f", "() => 2", "const f = () => 2;\n"),
        ("js class field", "v.js", js_class, "A.x", "2", js_class.replace("x = 1", "x = 2")),
        ("js class field without a value", "v.js", js_class, "A.y", "3",
         js_class.replace("static y;", "static y = 3;")),
        ("js private class field", "v.js", js_class, "A.#p", "2", js_class.replace("#p = 1", "#p = 2")),
        ("js object key still works", "v.js", "const C = { a: 1 };\n", "C.a", "2", "const C = { a: 2 };\n"),
        ("js closure key still works", "v.js", "const app = {\n  handler: () => 1,\n};\n", "app.handler",
         "() => 2", "const app = {\n  handler: () => 2,\n};\n"),
        ("ts annotated", "v.ts", "let X: number = 1;\n", "X", "2", "let X: number = 2;\n"),
        ("ts annotated without a value", "v.ts", "let x: number;\n", "x", "2", "let x: number = 2;\n"),
        ("ts class field", "v.ts", ts_class, "A.x", "2", ts_class.replace("x: number = 1", "x: number = 2")),
        ("ts optional field without a value", "v.ts", ts_class, "A.y", "2",
         ts_class.replace("y?: number;", "y?: number = 2;")),
        ("ts decorated field without a value", "v.ts", ts_class, "A.z", '"s"',
         ts_class.replace("z: string;", 'z: string = "s";')),
        ("ts namespace constant", "v.ts", "namespace N {\n  export const T = 1;\n}\n", "N.T", "2",
         "namespace N {\n  export const T = 2;\n}\n"),
        ("ts value sharing its name with a type", "v.ts", "const User = { a: 1 };\ntype User = { a: number };\n",
         "User", "{ a: 2 }", "const User = { a: 2 };\ntype User = { a: number };\n"),
        ("go var", "v.go", go + "var x = 1\n", "x", "2", go + "var x = 2\n"),
        ("go var with a type", "v.go", go + "var x int = 1\n", "x", "2", go + "var x int = 2\n"),
        ("go var without a value", "v.go", go + "var y int\n", "y", "2", go + "var y int = 2\n"),
        ("go second of two names", "v.go", go + "var a, b = 1, 2\n", "b", "3", go + "var a, b = 1, 3\n"),
        ("go const", "v.go", go + "const K = 1\n", "K", "2", go + "const K = 2\n"),
        ("go const in a group", "v.go", go + "const (\n\tA = iota\n\tB\n)\n", "B", "5",
         go + "const (\n\tA = iota\n\tB = 5\n)\n"),
        ("go func literal", "v.go", go + "var h = func() int { return 1 }\n", "h", "func() int { return 2 }",
         go + "var h = func() int { return 2 }\n"),
        ("c global", "v.c", "int g = 1;\n", "g", "2", "int g = 2;\n"),
        ("c global without a value", "v.c", "int g;\n", "g", "2", "int g = 2;\n"),
        ("c second of two names", "v.c", "int a = 1, b;\n", "b", "2", "int a = 1, b = 2;\n"),
        ("c pointer", "v.c", 'static const char *s = "a";\n', "s", '"b"', 'static const char *s = "b";\n'),
        ("c array without a value", "v.c", "int arr[3];\n", "arr", "{1, 2, 3}", "int arr[3] = {1, 2, 3};\n"),
        ("c initializer list", "v.c", "int arr[] = {1, 2};\n", "arr", "{3}", "int arr[] = {3};\n"),
        ("c definition after its extern declaration", "v.c", "extern int e;\nint e = 1;\n", "e", "2",
         "extern int e;\nint e = 2;\n"),
        ("c macro", "v.c", "#define N 3\nint x;\n", "N", "4", "#define N 4\nint x;\n"),
        ("c macro without a value", "v.c", "#define F\n", "F", "1", "#define F 1\n"),
        ("c macro with parameters", "v.c", "#define SQ(x) ((x) * (x))\n", "SQ", "((x) + (x))",
         "#define SQ(x) ((x) + (x))\n"),
        ("cpp direct initialization", "v.cpp", "int x(1);\n", "x", "2", "int x(2);\n"),
        ("cpp brace initialization", "v.cpp", "int y{1};\n", "y", "2", "int y{2};\n"),
        ("cpp member", "v.cpp", cpp_struct, "S.a", "3", cpp_struct.replace("a = 1", "a = 3")),
        ("cpp member without a value", "v.cpp", cpp_struct, "S.b", "4", cpp_struct.replace(" b;", " b = 4;")),
        ("cpp member with braces", "v.cpp", cpp_struct, "S.c", "5", cpp_struct.replace("c{2}", "c{5}")),
        ("cpp static member definition", "v.cpp", "struct A {\n    static int n;\n};\nint A::n = 1;\n", "A::n", "2",
         "struct A {\n    static int n;\n};\nint A::n = 2;\n"),
        ("java field", "V.java", java_class, "A.x", "2", java_class.replace("x = 1", "x = 2")),
        ("java field without a value", "V.java", java_class, "A.y", "3", java_class.replace(" y;", " y = 3;")),
        ("java array field without a value", "V.java", java_class, "A.w", "{1}",
         java_class.replace("w[];", "w[] = {1};")),
        ("java interface constant", "V.java", "interface I {\n    int K = 1;\n}\n", "I.K", "2",
         "interface I {\n    int K = 2;\n}\n"),
        ("rb constant", "v.rb", "X = 1\ny = 2\n", "X", "2", "X = 2\ny = 2\n"),
        ("rb local variable", "v.rb", "X = 1\ny = 2\n", "y", "3", "X = 1\ny = 3\n"),
        ("rb constant in a module", "v.rb", "module M\n  NAME = 'a'\nend\n", "M.NAME", "'b'",
         "module M\n  NAME = 'b'\nend\n"),
        # A heredoc's body is part of the value that opens it.
        ("rb heredoc", "v.rb", "X = <<~EOS\n  text\nEOS\nY = 2\n", "X", "1", "X = 1\nY = 2\n"),
        ("rb heredoc in a class", "v.rb", "class A\n  N = <<~EOS.strip\n    t\n  EOS\n  M = 1\nend\n", "A.N", "'x'",
         "class A\n  N = 'x'\n  M = 1\nend\n"),
        # A TS definite assignment `!` goes when the name gets a value.
        ("ts definite assignment", "v.ts", "let y!: number;\n", "y", "2", "let y: number = 2;\n"),
        ("ts definite field", "v.ts", "class A {\n  x!: number;\n}\n", "A.x", "1", "class A {\n  x: number = 1;\n}\n"),
        ("c function pointer without a value", "v.c", "int (*fp)(int);\n", "fp", "g", "int (*fp)(int) = g;\n"),
        ("c macro with a comment after it", "v.c", '#define URL "http://x" // the url\n', "URL", '"y"',
         '#define URL "y" // the url\n'),
        ("cpp spaces inside the braces", "v.cpp", "std::vector<int> v{ 1, 2 };\n", "v", "3",
         "std::vector<int> v{ 3 };\n"),
    ]
    for label, name, source, target, content, expected in cases:
        _exact(f"replace_value ({label})", _edit_result(name, source, lambda a: a.replace_value(target, content)),
               expected)
    _exact("replace_value (py module variable, crlf)",
           _edit_result("v.py", "X = 1\nY = 2\n", lambda a: a.replace_value("X", "2"), "\r\n"), "X = 2\r\nY = 2\r\n")

    shared = "gets its value together with other names, so it has none of its own to replace; rewrite the " \
             "declaration with replace_function"
    nothing = "has no value (replace_value is for keys and for the values of variables, constants and fields); " \
              "rewrite it with replace_function"
    # (label, file name, source, target, the refusal)
    refusals = [
        ("py chained assignment", "v.py", "a = b = 1\n", "a", f"'a' {shared}"),
        ("rb chained assignment", "v.rb", "A = B = 1\n", "A", f"'A' {shared}"),
        ("go one value for two names", "v.go", go + "var c, d = f()\n", "c", f"'c' {shared}"),
        ("cpp structured binding", "v.cpp", "auto [p, q] = r;\n", "p", f"'p' {shared}"),
        ("go two names without values", "v.go", go + "var e, g int\n", "e",
         "'e' is declared with other names and no values, and a value for it needs one for each of them; "
         "rewrite the declaration with replace_function"),
        ("c extern declaration", "v.c", "extern int e;\n", "e",
         "'e' has no value, and an `extern` declaration takes none: the variable's definition holds its value"),
        ("ts declare", "v.ts", "declare let y: number;\n", "y",
         "'y' has no value, and a `declare` declaration cannot have one"),
        ("ts in a declared namespace", "v.ts", "declare namespace N {\n  let y: number;\n}\n", "N.y",
         "'N.y' has no value, and a `declare` declaration cannot have one"),
        ("ts declare field", "v.ts", "class A {\n  declare w: string;\n}\n", "A.w",
         "'A.w' has no value, and a `declare` declaration cannot have one"),
        ("ts abstract field", "v.ts", "abstract class A {\n  abstract z: number;\n}\n", "A.z",
         "'A.z' has no value, and an abstract field cannot have one"),
        ("c struct field", "v.c", "struct S {\n    int x;\n};\n", "S.x",
         "'S.x' has no value, and a field of a C struct cannot have one"),
        ("py function", "v.py", "def f():\n    pass\n", "f", f"'f' is a function, which {nothing}"),
        ("py decorated class", "v.py", "@d\nclass A:\n    pass\n", "A", f"'A' is a class, which {nothing}"),
        ("js function", "v.js", "function f() {}\n", "f", f"'f' is a function, which {nothing}"),
        ("js method", "v.js", "class A {\n  m() {}\n}\n", "A.m", f"'A.m' is a function, which {nothing}"),
        ("ts type alias", "v.ts", "type T = string;\n", "T", f"'T' is a type alias, which {nothing}"),
        ("ts enum", "v.ts", "enum E { A }\n", "E", f"'E' is an enum, which {nothing}"),
        ("ts interface", "v.ts", "interface I {}\n", "I", f"'I' is an interface, which {nothing}"),
        ("ts namespace", "v.ts", "namespace N {}\n", "N", f"'N' is a namespace, which {nothing}"),
        ("c prototype", "v.c", "int f(void);\n", "f", f"'f' is a function, which {nothing}"),
        ("c struct", "v.c", "struct S {\n    int x;\n};\n", "S", f"'S' is a struct, which {nothing}"),
        ("c typedef", "v.c", "typedef int T;\n", "T", f"'T' is a type alias, which {nothing}"),
        ("cpp class", "v.cpp", "class K {};\n", "K", f"'K' is a class, which {nothing}"),
        ("go type", "v.go", go + "type T int\n", "T", f"'T' is a type definition, which {nothing}"),
        ("go function", "v.go", go + "func f() {}\n", "f", f"'f' is a function, which {nothing}"),
        ("java method", "V.java", "class A {\n    void m() {}\n}\n", "A.m", f"'A.m' is a function, which {nothing}"),
        ("rb method", "v.rb", "def f\nend\n", "f", f"'f' is a function, which {nothing}"),
        ("rb module", "v.rb", "module M\nend\n", "M", f"'M' is a module, which {nothing}"),
    ]
    for label, name, source, target, reason in refusals:
        _refused(f"replace_value ({label})", _edit_result(name, source, lambda a: a.replace_value(target, "2")),
                 f"REFUSED: {reason}")
    # A C++20 bit-field's value goes after its width, which the grammar does
    # not parse yet.
    _refused("replace_value (cpp bit-field without a value)",
             _edit_result("v.cpp", cpp_struct, lambda a: a.replace_value("S.f", "1")),
             "REFUSED: Edit refused: the result would have a syntax error at line 4, column 11 (cannot parse ': 3')")
    # A destructured name is no target, as for the other tools.
    _refused("replace_value (js destructured name)",
             _edit_result("v.js", "const { a, b } = o;\n", lambda a: a.replace_value("a", "2")),
             "REFUSED: Target 'a' not found")


def test_first_import_placement():
    print("\n═══ add_import: a first import after the file's preamble, a next one after the last ═══")

    go = "package main\n\n"
    java_import = "import java.util.List;"
    js_import = "import x from 'x';"
    # (label, file name, source, import text, expected file text)
    cases = [
        ("java after the package (reported)", "P.java", "package p;\n\nclass A {}\n", java_import,
         "package p;\n\nimport java.util.List;\n\nclass A {}\n"),
        ("java class right after the package", "P.java", "package p;\nclass A {}\n", java_import,
         "package p;\n\nimport java.util.List;\n\nclass A {}\n"),
        ("java comment above the package", "P.java", "// License.\npackage p;\n\nclass A {}\n", java_import,
         "// License.\npackage p;\n\nimport java.util.List;\n\nclass A {}\n"),
        ("java no package", "P.java", "class A {}\n", java_import, "import java.util.List;\n\nclass A {}\n"),
        ("go after the package (reported)", "i.go", go + "func f() {}\n", 'import "fmt"',
         go + 'import "fmt"\n\nfunc f() {}\n'),
        ("go only a package", "i.go", "package main\n", 'import "fmt"', go + 'import "fmt"\n'),
        ("go build constraint and package comment", "i.go",
         "//go:build linux\n\n// Package main runs.\npackage main\nfunc f() {}\n", 'import "fmt"',
         "//go:build linux\n\n// Package main runs.\npackage main\n\nimport \"fmt\"\n\nfunc f() {}\n"),
        ("py shebang and docstring (reported)", "i.py", '#!/usr/bin/env python\n"""Doc."""\ndef f():\n    pass\n',
         "import os", '#!/usr/bin/env python\n"""Doc."""\n\nimport os\n\n\ndef f():\n    pass\n'),
        ("py shebang and encoding", "i.py", "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\nx = 1\n", "import os",
         "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n\nimport os\n\nx = 1\n"),
        ("py docstring over lines, then a blank line", "i.py", '"""Doc.\n\nMore.\n"""\n\nx = 1\n', "import os",
         '"""Doc.\n\nMore.\n"""\n\nimport os\n\nx = 1\n'),
        ("py header comment", "i.py", "# Copyright A.\n\ndef f():\n    pass\n", "import os",
         "# Copyright A.\n\nimport os\n\n\ndef f():\n    pass\n"),
        ("py comment on the first def stays on it", "i.py", "# Helper.\ndef f():\n    pass\n", "import os",
         "import os\n\n\n# Helper.\ndef f():\n    pass\n"),
        ("py only the first block of comments is the header", "i.py", "# Copyright A.\n\n# Helpers.\n\nx = 1\n",
         "import os", "# Copyright A.\n\nimport os\n\n# Helpers.\n\nx = 1\n"),
        ("go comment after the package belongs to the code", "i.go",
         "// Copyright A.\n\npackage main\n\n// Notes.\n\n// F runs.\nfunc F() {}\n", 'import "fmt"',
         "// Copyright A.\n\npackage main\n\nimport \"fmt\"\n\n// Notes.\n\n// F runs.\nfunc F() {}\n"),
        ("ts pragma after the header", "i.ts", "// Copyright A.\n\n// @ts-nocheck\nexport const x = 1;\n", js_import,
         "// Copyright A.\n\n// @ts-nocheck\n\nimport x from 'x';\n\nexport const x = 1;\n"),
        ("py docstring, then a comment on the first def", "i.py", '"""Doc."""\n# Helper.\ndef f():\n    pass\n',
         "import os", '"""Doc."""\n\nimport os\n\n\n# Helper.\ndef f():\n    pass\n'),
        ("py nothing before", "i.py", "def f():\n    pass\n", "import os", "import os\n\n\ndef f():\n    pass\n"),
        ("py a statement after", "i.py", "x = 1\n", "import os", "import os\n\nx = 1\n"),
        ("py empty file", "i.py", "", "import os", "import os\n"),
        ("py only a docstring", "i.py", '"""Doc."""\n', "import os", '"""Doc."""\n\nimport os\n'),
        ("py after a __future__ import", "i.py", '"""Doc."""\nfrom __future__ import annotations\nx = 1\n',
         "import os", '"""Doc."""\nfrom __future__ import annotations\nimport os\nx = 1\n'),
        ("rb magic comment (reported)", "i.rb", "# frozen_string_literal: true\ndef f\nend\n", "require 'x'",
         "# frozen_string_literal: true\n\nrequire 'x'\n\ndef f\nend\n"),
        ("rb shebang and magic comment", "i.rb", "#!/usr/bin/env ruby\n# frozen_string_literal: true\n\nputs 1\n",
         "require 'x'", "#!/usr/bin/env ruby\n# frozen_string_literal: true\n\nrequire 'x'\n\nputs 1\n"),
        ("rb after a require", "i.rb", "require 'a'\nputs 1\n", "require 'x'", "require 'a'\nrequire 'x'\nputs 1\n"),
        ("js use strict", "i.js", "'use strict';\n\nfunction f() {}\n", js_import,
         "'use strict';\n\nimport x from 'x';\n\nfunction f() {}\n"),
        ("js shebang", "i.js", "#!/usr/bin/env node\nfunction f() {}\n", js_import,
         "#!/usr/bin/env node\n\nimport x from 'x';\n\nfunction f() {}\n"),
        ("js doc comment on the first function stays on it", "i.js", "/** Doc. */\nfunction f() {}\n", js_import,
         "import x from 'x';\n\n/** Doc. */\nfunction f() {}\n"),
        ("ts triple-slash directive", "i.ts", '/// <reference types="node" />\nfunction f() {}\n', js_import,
         '/// <reference types="node" />\n\nimport x from \'x\';\n\nfunction f() {}\n'),
        ("tsx use client", "i.tsx", '"use client";\nexport function f() {}\n', js_import,
         '"use client";\n\nimport x from \'x\';\n\nexport function f() {}\n'),
        ("c code right after the last include (reported)", "i.c", "#include <x.h>\nint f(void) { return 0; }\n",
         "#include <y.h>", "#include <x.h>\n#include <y.h>\nint f(void) { return 0; }\n"),
        ("c blank line after the last include", "i.c", "#include <x.h>\n\nint f(void);\n", "#include <y.h>",
         "#include <x.h>\n#include <y.h>\n\nint f(void);\n"),
        ("c include in a conditional", "i.c", "#include <x.h>\n#ifdef W\n#include <w.h>\n#endif\nint f(void);\n",
         "#include <y.h>", "#include <x.h>\n#ifdef W\n#include <w.h>\n#endif\n#include <y.h>\nint f(void);\n"),
        ("c no includes", "i.c", "int f(void) { return 0; }\n", "#include <y.h>",
         "#include <y.h>\n\nint f(void) { return 0; }\n"),
        ("h include guard", "i.h", "#ifndef X_H\n#define X_H\n\nint f(void);\n\n#endif\n", "#include <y.h>",
         "#ifndef X_H\n#define X_H\n\n#include <y.h>\n\nint f(void);\n\n#endif\n"),
        ("h include guard with includes", "i.h", "#ifndef X_H\n#define X_H\n#include <a.h>\nint f(void);\n#endif\n",
         "#include <y.h>", "#ifndef X_H\n#define X_H\n#include <a.h>\n#include <y.h>\nint f(void);\n#endif\n"),
        ("h license and include guard", "i.h",
         "/* License. */\n#ifndef X_H\n#define X_H\nint f(void);\n#endif /* X_H */\n", "#include <y.h>",
         "/* License. */\n#ifndef X_H\n#define X_H\n\n#include <y.h>\n\nint f(void);\n#endif /* X_H */\n"),
        ("hpp pragma once", "i.hpp", "#pragma once\nint f();\n", "#include <y>",
         "#pragma once\n\n#include <y>\n\nint f();\n"),
        ("h not an include guard", "i.h", "#ifdef W\nint f(void);\n#endif\n", "#include <y.h>",
         "#include <y.h>\n\n#ifdef W\nint f(void);\n#endif\n"),
    ]
    for label, name, source, text, expected in cases:
        _exact(f"add_import ({label})", _edit_result(name, source, lambda a: a.add_import(text)), expected)
    _exact("add_import (java after the package, crlf)",
           _edit_result("P.java", "package p;\n\nclass A {}\n", lambda a: a.add_import(java_import), "\r\n"),
           "package p;\r\n\r\nimport java.util.List;\r\n\r\nclass A {}\r\n")

    # add_top_level(position="top") goes after the same directives.
    top = [
        ("js use strict", "t.js", "'use strict';\nfunction f() {}\n", "const X = 1;",
         "'use strict';\n\nconst X = 1;\n\nfunction f() {}\n"),
        ("js shebang", "t.js", "#!/usr/bin/env node\nfunction f() {}\n", "const X = 1;",
         "#!/usr/bin/env node\n\nconst X = 1;\n\nfunction f() {}\n"),
        ("h include guard", "t.h", "#ifndef X_H\n#define X_H\n#include <a.h>\nint f(void);\n#endif\n",
         "int g(void);", "#ifndef X_H\n#define X_H\n#include <a.h>\n\nint g(void);\n\nint f(void);\n#endif\n"),
        ("hpp pragma once", "t.hpp", "#pragma once\nint f();\n", "int g();", "#pragma once\n\nint g();\n\nint f();\n"),
        ("py comment on the first code after the imports", "t.py", "import os\n\n# Doc.\ndef f():\n    pass\n",
         "X = 1", "import os\n\nX = 1\n\n\n# Doc.\ndef f():\n    pass\n"),
    ]
    for label, name, source, content, expected in top:
        _exact(f"add_top_level top ({label})",
               _edit_result(name, source, lambda a: a.add_top_level(content, "top")), expected)


def test_destructured_parameters():
    print("\n═══ remove_parameter: one name of a destructured parameter ═══")

    # A name bound by a destructuring pattern goes alone; the pattern's last
    # name takes the whole parameter. Positions in an array pattern (a hole)
    # and a Ruby one (`_`) are kept, so the names after it bind what they did.
    # (label, file name, source, target, name, expected file text)
    cases = [
        ("js renamed key (reported)", "p.js", "function f({a: x, b}) {}\n", "f", "x", "function f({b}) {}\n"),
        ("js first shorthand name", "p.js", "function f({a, b}) {}\n", "f", "a", "function f({b}) {}\n"),
        ("js last shorthand name", "p.js", "function f({a, b}) {}\n", "f", "b", "function f({a}) {}\n"),
        ("js spaces inside the braces", "p.js", "function f({ a, b }) {}\n", "f", "a", "function f({ b }) {}\n"),
        ("js the last name takes the parameter", "p.js", "function f({a}, c) {}\n", "f", "a", "function f(c) {}\n"),
        ("js name with a default", "p.js", "function f({a = 1, b}) {}\n", "f", "a", "function f({b}) {}\n"),
        ("js pattern with a default", "p.js", "function f({a, b} = {}) {}\n", "f", "a",
         "function f({b} = {}) {}\n"),
        ("js rest of a pattern", "p.js", "function f({a, ...rest}) {}\n", "f", "rest", "function f({a}) {}\n"),
        ("js nested pattern", "p.js", "function f({a: {b, c}, d}) {}\n", "f", "b", "function f({a: {c}, d}) {}\n"),
        ("js last name of a nested pattern", "p.js", "function f({a: {c}, d}) {}\n", "f", "c",
         "function f({d}) {}\n"),
        ("js last of an array", "p.js", "function f([a, b]) {}\n", "f", "b", "function f([a]) {}\n"),
        ("js first of an array keeps its position", "p.js", "function f([a, b]) {}\n", "f", "a",
         "function f([, b]) {}\n"),
        ("js array after a hole", "p.js", "function f([, b], c) {}\n", "f", "b", "function f(c) {}\n"),
        ("js last of an array after a hole", "p.js", "function f([a, , c]) {}\n", "f", "c", "function f([a]) {}\n"),
        ("js arrow function", "p.js", "const g = ({a, b}) => a;\n", "g", "b", "const g = ({a}) => a;\n"),
        ("js one name per line", "p.js", "function f({\n  a,\n  b,\n}) {}\n", "f", "a",
         "function f({\n  b,\n}) {}\n"),
        ("js method", "p.js", "class A {\n  m({a, b}) {}\n}\n", "A.m", "b", "class A {\n  m({a}) {}\n}\n"),
        ("ts typed pattern", "p.ts", "function f({a, b}: Props) {}\n", "f", "a", "function f({b}: Props) {}\n"),
        ("ts typed pattern, its last name", "p.ts", "function f({a}: Props, c: number) {}\n", "f", "a",
         "function f(c: number) {}\n"),
        ("ts array pattern", "p.ts", "function f([a, b]: number[]) {}\n", "f", "a",
         "function f([, b]: number[]) {}\n"),
        ("rb first keeps its position (reported)", "p.rb", "def f((a, b), c)\nend\n", "f", "a",
         "def f((_, b), c)\nend\n"),
        ("rb last", "p.rb", "def f((a, b), c)\nend\n", "f", "b", "def f((a), c)\nend\n"),
        ("rb the last name takes the parameter", "p.rb", "def f((a), c)\nend\n", "f", "a", "def f(c)\nend\n"),
        ("rb after a placeholder", "p.rb", "def f((_, b), c)\nend\n", "f", "b", "def f(c)\nend\n"),
        ("rb nested", "p.rb", "def f((a, (b, c)))\nend\n", "f", "c", "def f((a, (b)))\nend\n"),
        ("rb splat in a pattern", "p.rb", "def f((a, *r))\nend\n", "f", "r", "def f((a))\nend\n"),
    ]
    for label, name, source, target, parameter, expected in cases:
        _exact(f"remove_parameter ({label})",
               _edit_result(name, source, lambda a: a.remove_parameter(target, parameter)), expected)
    # A key is no name: `{a: x}` binds x.
    _refused("remove_parameter (js key of a renamed name)",
             _edit_result("p.js", "function f({a: x, b}) {}\n", lambda a: a.remove_parameter("f", "a")),
             "REFUSED: Parameter 'a' not found in 'f'")
    _refused("remove_parameter (rb placeholder)",
             _edit_result("p.rb", "def f((_, b))\nend\n", lambda a: a.remove_parameter("f", "_")),
             "REFUSED: Parameter '_' not found in 'f'")


def test_parameter_followups():
    print("\n═══ add_parameter and remove_parameter: duplicates, Go closures, empty lists, comments ═══")

    go = "package main\n\n"
    # add_parameter refuses a name the function already has, wherever the
    # name is (a Go group, a destructuring pattern) and whatever the new
    # parameter's text around it (a type, a default, `*`, `&`).
    # (label, file name, source, target, parameter, name it repeats)
    duplicates = [
        ("py (reported)", "d.py", "def f(a):\n    pass\n", "f", "a", "a"),
        ("py typed", "d.py", "def f(a: int):\n    pass\n", "f", "a: str", "a"),
        ("py default", "d.py", "def f(a=1):\n    pass\n", "f", "a=2", "a"),
        ("py star", "d.py", "def f(*args):\n    pass\n", "f", "args", "args"),
        ("py keywords", "d.py", "def f(**kw):\n    pass\n", "f", "kw=None", "kw"),
        ("py one per line", "d.py", "def f(\n    a,\n):\n    pass\n", "f", "a", "a"),
        ("js", "d.js", "function f(a) {}\n", "f", "a = 1", "a"),
        ("js destructured", "d.js", "function f({a, b}) {}\n", "f", "b", "b"),
        ("js new pattern", "d.js", "function f(a) {}\n", "f", "{a, c}", "a"),
        ("js rest", "d.js", "function f(a) {}\n", "f", "...a", "a"),
        ("js bare arrow parameter", "d.js", "const g = x => x;\n", "g", "x", "x"),
        ("ts", "d.ts", "function f(a: number) {}\n", "f", "a?: string", "a"),
        ("go group", "d.go", go + "func f(a, b int) {}\n", "f", "b string", "b"),
        ("go new group", "d.go", go + "func f(a int) {}\n", "f", "b, a string", "a"),
        ("c", "d.c", "int f(int a) { return a; }\n", "f", "int a", "a"),
        ("cpp pointer", "d.cpp", "int f(char *s) { return 0; }\n", "f", "const char *s", "s"),
        ("java", "D.java", "class A {\n    void m(int a) {}\n}\n", "A.m", "String a", "a"),
        ("rb", "d.rb", "def f(a)\nend\n", "f", "a = 1", "a"),
        ("rb block", "d.rb", "def f(a)\nend\n", "f", "&a", "a"),
        ("rb destructured", "d.rb", "def f((a, b))\nend\n", "f", "b", "b"),
    ]
    for label, name, source, target, parameter, repeated in duplicates:
        for position in ("end", "start"):
            _refused(f"add_parameter duplicate ({label}, {position})",
                     _edit_result(name, source, lambda a: a.add_parameter(target, parameter, position)),
                     f"REFUSED: Parameter '{repeated}' already exists in '{target}'")
    # Names that do not repeat, and those the language lets repeat.
    for label, name, source, target, parameter, expected in [
        ("py another name", "d.py", "def f(a):\n    pass\n", "f", "b", "def f(a, b):\n    pass\n"),
        ("py a type that names a parameter", "d.py", "def f(a):\n    pass\n", "f", "b: a",
         "def f(a, b: a):\n    pass\n"),
        ("go blank names", "d.go", go + "func f(_ int) {}\n", "f", "_ string", go + "func f(_ int, _ string) {}\n"),
        ("c unnamed parameters", "d.c", "int f(int);\n", "f", "int", "int f(int, int);\n"),
        ("rb placeholders", "d.rb", "def f(_)\nend\n", "f", "_", "def f(_, _)\nend\n"),
    ]:
        _exact(f"add_parameter ({label})", _edit_result(name, source, lambda a: a.add_parameter(target, parameter)),
               expected)

    # A Go func literal bound to a var is a function for the parameter and
    # body tools.
    closure = go + "var x = func(a, b int) {\n\treturn\n}\n"
    for label, action, expected in [
        ("remove_parameter (reported)", lambda a: a.remove_parameter("x", "a"),
         go + "var x = func(b int) {\n\treturn\n}\n"),
        ("add_parameter", lambda a: a.add_parameter("x", "c string"),
         go + "var x = func(a, b int, c string) {\n\treturn\n}\n"),
        ("replace_function_body", lambda a: a.replace_function_body("x", "println()"),
         go + "var x = func(a, b int) {\n\tprintln()\n}\n"),
        ("insert_in_body top", lambda a: a.insert_in_body("x", "println()", at="top"),
         go + "var x = func(a, b int) {\n\tprintln()\n\treturn\n}\n"),
        ("replace_in_body", lambda a: a.replace_in_body("x", "return", "println()"),
         go + "var x = func(a, b int) {\n\tprintln()\n}\n"),
        ("delete_in_body", lambda a: a.delete_in_body("x", "\treturn\n"), go + "var x = func(a, b int) {\n}\n"),
        ("replace_signature of the function", lambda a: a.replace_signature("x", "func(c int)"),
         go + "var x = func(c int) {\n\treturn\n}\n"),
        ("replace_signature from the var", lambda a: a.replace_signature("x", "var y = func()"),
         go + "var y = func() {\n\treturn\n}\n"),
    ]:
        _exact(f"go var func literal: {label}", _edit_result("c.go", closure, action), expected)
    for depth in ("signature", "interface"):
        _exact(f"go var func literal: depth {depth}",
               _read_result("c.go", closure, lambda a: a.read_symbol("x", depth)), "var x = func(a, b int)")
    _exact("go var func literal: replace_signature with its signature",
           _edit_result("c.go", closure, lambda a: a.replace_signature("x", a.read_symbol("x", "signature"))), closure)
    for label, source, target, name, expected in [
        ("in a var group", go + "var (\n\tx = func(a int) {}\n\ty = 1\n)\n", "x", "a",
         go + "var (\n\tx = func() {}\n\ty = 1\n)\n"),
        ("second of two names", go + "var p, q = func(a int) {}, func(b int) {}\n", "q", "b",
         go + "var p, q = func(a int) {}, func() {}\n"),
    ]:
        _exact(f"go var func literal: remove_parameter ({label})",
               _edit_result("c.go", source, lambda a: a.remove_parameter(target, name)), expected)
    _refused("go var that is no func literal",
             _edit_result("c.go", go + "var n = 1\n", lambda a: a.remove_parameter("n", "a")),
             "REFUSED: Could not find parameter list for 'n'")

    # An empty list whose `)` is on a line below its `(` gets the parameter
    # on a line of its own, one level deeper than the function's line, with
    # a trailing comma where the language takes one and the file's other
    # lists written one parameter per line do not go without it (Go needs it).
    # (label, file name, source, target, parameter, expected file text)
    empty = [
        ("py (reported)", "e.py", "def f(\n):\n    pass\n", "f", "c", "def f(\n    c,\n):\n    pass\n"),
        ("py file without trailing commas", "e.py", "def g(\n    a\n):\n    pass\n\n\ndef f(\n):\n    pass\n",
         "f", "c", "def g(\n    a\n):\n    pass\n\n\ndef f(\n    c\n):\n    pass\n"),
        ("py file with trailing commas", "e.py", "def g(\n    a,\n):\n    pass\n\n\ndef f(\n):\n    pass\n",
         "f", "c", "def g(\n    a,\n):\n    pass\n\n\ndef f(\n    c,\n):\n    pass\n"),
        ("py method", "e.py", "class A:\n    def f(\n        self,\n    ):\n        pass\n\n    @staticmethod\n"
         "    def g(\n    ):\n        pass\n", "A.g", "c",
         "class A:\n    def f(\n        self,\n    ):\n        pass\n\n    @staticmethod\n"
         "    def g(\n        c,\n    ):\n        pass\n"),
        ("py at the start", "e.py", "def f(\n):\n    pass\n", "f", "c", "def f(\n    c,\n):\n    pass\n"),
        ("js", "e.js", "function f(\n) {}\n", "f", "c", "function f(\n  c,\n) {}\n"),
        ("ts", "e.ts", "function f(\n): void {}\n", "f", "c: number", "function f(\n  c: number,\n): void {}\n"),
        ("go needs the comma", "e.go", go + "func f(\n) {}\n", "f", "c int", go + "func f(\n\tc int,\n) {}\n"),
        ("go comment after the (", "e.go", go + "func f( // none yet\n) {}\n", "f", "c int",
         go + "func f( // none yet\n\tc int,\n) {}\n"),
        ("c takes no comma", "e.c", "int f(\n) { return 0; }\n", "f", "int c", "int f(\n  int c\n) { return 0; }\n"),
        ("java takes no comma", "E.java", "class A {\n    void m(\n    ) {}\n}\n", "A.m", "int c",
         "class A {\n    void m(\n        int c\n    ) {}\n}\n"),
        ("rb takes no comma", "e.rb", "def f(\n)\nend\n", "f", "c", "def f(\n  c\n)\nend\n"),
        ("py blank line inside", "e.py", "def f(\n\n):\n    pass\n", "f", "c", "def f(\n    c,\n):\n    pass\n"),
        ("py on one line stays there", "e.py", "def f():\n    pass\n", "f", "c", "def f(c):\n    pass\n"),
    ]
    for label, name, source, target, parameter, expected in empty:
        position = "start" if "start" in label else "end"
        _exact(f"add_parameter empty list over lines ({label})",
               _edit_result(name, source, lambda a: a.add_parameter(target, parameter, position)), expected)
    _exact("add_parameter empty list over lines (crlf)",
           _edit_result("e.go", go + "func f(\n) {}\n", lambda a: a.add_parameter("f", "c int"), "\r\n"),
           (go + "func f(\n\tc int,\n) {}\n").replace("\n", "\r\n"))

    # A comment between the names of a Go group stays when the last one goes.
    # (label, source, parameter, expected)
    comments = [
        ("line comment after the comma (reported)", "func f(a, // x\n\tb int) {}\n", "b",
         "func f(a int, // x\n) {}\n"),
        ("line comment, another parameter after", "func f(a, // x\n\tb int, c string) {}\n", "b",
         "func f(a int, // x\n\tc string) {}\n"),
        ("block comment after the comma", "func f(a, /* x */ b int) {}\n", "b", "func f(a /* x */ int) {}\n"),
        ("method", "type T struct{}\n\nfunc (t T) m(a, // x\n\tb int) {}\n", "b",
         "type T struct{}\n\nfunc (t T) m(a int, // x\n) {}\n"),
    ]
    for label, source, parameter, expected in comments:
        target = "T.m" if "method" in label else "f"
        _exact(f"go remove_parameter ({label})",
               _edit_result("g.go", go + source, lambda a: a.remove_parameter(target, parameter)), go + expected)


# ──────────────────────────────────────────────
# Final line breaks, encodings, layout, YAML empty sequences, Ruby
# documents and signatures, comments that end the code above
# ──────────────────────────────────────────────


def test_final_newline_state():
    print("\n═══ a file whose last line has no line break keeps it so, and new code starts a line ═══")

    bom = chr(0xFEFF)
    two_defs = "def f():\n    pass\n\n\ndef g():\n    pass"
    # (label, file name, source without a final line break, action, expected file text)
    cases = [
        ("cpp replace_function (reported)", "n.cpp", "int y;\nint f() { return 1; }",
         lambda a: a.replace_function("f", "int f() { return 2; }"), "int y;\nint f() { return 2; }"),
        ("py replace_function_body", "n.py", "def f():\n    return 1",
         lambda a: a.replace_function_body("f", "return 2"), "def f():\n    return 2"),
        ("py add_top_level at the bottom", "n.py", "def f():\n    pass",
         lambda a: a.add_top_level("def g():\n    pass"), "def f():\n    pass\n\n\ndef g():\n    pass"),
        ("c add_top_level at the bottom", "n.c", "int y;",
         lambda a: a.add_top_level("int g(void);"), "int y;\n\nint g(void);"),
        ("py add_top_level at the top", "n.py", "def f():\n    pass",
         lambda a: a.add_top_level("X = 1", "top"), "X = 1\n\n\ndef f():\n    pass"),
        ("py add_import after the last", "n.py", "import os",
         lambda a: a.add_import("import sys"), "import os\nimport sys"),
        ("c add_import after the last", "n.c", "#include <x.h>",
         lambda a: a.add_import("#include <y.h>"), "#include <x.h>\n#include <y.h>"),
        ("go first add_import", "n.go", "package main",
         lambda a: a.add_import('import "fmt"'), 'package main\n\nimport "fmt"'),
        ("js insert_sibling after the last", "n.js", "function f() {}",
         lambda a: a.insert_sibling("f", "function g() {}", "after"), "function f() {}\n\nfunction g() {}"),
        ("py insert_sibling after the last", "n.py", "def f():\n    pass",
         lambda a: a.insert_sibling("f", "def g():\n    pass", "after"), "def f():\n    pass\n\n\ndef g():\n    pass"),
        ("py add_method", "n.py", "class A:\n    def f(self):\n        pass",
         lambda a: a.add_method("A", "def g(self):\n    pass"),
         "class A:\n    def f(self):\n        pass\n\n    def g(self):\n        pass"),
        ("rb add_method", "n.rb", "class A\n  def f\n  end\nend",
         lambda a: a.add_method("A", "def g\nend"), "class A\n  def f\n  end\n\n  def g\n  end\nend"),
        ("py insert_in_body at the bottom", "n.py", "def f():\n    pass",
         lambda a: a.insert_in_body("f", "x = 1", at="bottom"), "def f():\n    pass\n    x = 1"),
        ("java remove_parameter", "N.java", "class A {\n    void f(int a, int b) {}\n}",
         lambda a: a.remove_parameter("A.f", "b"), "class A {\n    void f(int a) {}\n}"),
        ("py edit_leading_comment", "n.py", "def f():\n    pass",
         lambda a: a.edit_leading_comment("f", "add", "# Doc."), "# Doc.\ndef f():\n    pass"),
        ("py delete_symbol of the last", "n.py", two_defs, lambda a: a.delete_symbol("g"), "def f():\n    pass"),
        ("py delete_symbol of the only one", "n.py", "def g():\n    pass", lambda a: a.delete_symbol("g"), ""),
        ("yaml add_key at the root", "n.yaml", "a: 1", lambda a: a.add_key("", "b", "2"), "a: 1\nb: 2"),
        ("yaml append_to_array", "n.yaml", "a:\n  - 1", lambda a: a.append_to_array("a", "2"), "a:\n  - 1\n  - 2"),
        ("yaml delete_key of the last", "n.yaml", "a: 1\nb: 2", lambda a: a.delete_key("b"), "a: 1"),
        ("toml add_key", "n.toml", "[t]\na = 1", lambda a: a.add_key("t", "b", "2"), "[t]\na = 1\nb = 2"),
        ("json add_key", "n.json", '{"a": 1}', lambda a: a.add_key("", "b", "2"), '{"a": 1, "b": 2}'),
        ("json replace_value", "n.json", '{"a": 1}', lambda a: a.replace_value("a", "2"), '{"a": 2}'),
        ("rb heredoc on the last line", "n.rb", "X = <<~EOS\n  a\nEOS",
         lambda a: a.add_top_level("Y = 1"), "X = <<~EOS\n  a\nEOS\n\nY = 1"),
        ("c macro on the last line", "n.c", "#define X 1",
         lambda a: a.add_top_level("int y;"), "#define X 1\n\nint y;"),
        ("py comment on the last line", "n.py", "def f():\n    pass\n# end",
         lambda a: a.add_top_level("def g():\n    pass"), "def f():\n    pass\n# end\n\n\ndef g():\n    pass"),
        ("two edits in a row", "n.py", "def f():\n    pass",
         lambda a: (a.add_top_level("X = 1"), a.add_top_level("Y = 2")), "def f():\n    pass\n\n\nX = 1\n\nY = 2"),
        ("byte order mark", "n.py", bom + "def f():\n    pass",
         lambda a: a.replace_function("f", "def f():\n    return 1"), bom + "def f():\n    return 1"),
        # A file that ends with its line break keeps it, and an empty file
        # gets one with its first line.
        ("a final line break stays", "n.cpp", "int f() { return 1; }\n",
         lambda a: a.replace_function("f", "int f() { return 2; }"), "int f() { return 2; }\n"),
        ("an empty file", "n.py", "", lambda a: a.add_top_level("X = 1"), "X = 1\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"no final line break ({label})", _edit_result(name, source, action), expected)
    _exact("no final line break (crlf)",
           _edit_result("n.py", "def f():\n    pass", lambda a: a.replace_function("f", "def f():\n    return 1"), "\r\n"),
           "def f():\r\n    return 1")
    _exact("no final line break (crlf add_top_level)",
           _edit_result("n.py", "X = 1\nY = 2", lambda a: a.add_top_level("Z = 3"), "\r\n"), "X = 1\r\nY = 2\r\nZ = 3")
    # The syntax check still guards such files, and a refused edit leaves
    # them as they were.
    _refused("no final line break (syntax error refused)",
             _edit_result("n.py", "def f():\n    pass", lambda a: a.replace_function("f", "def f(:\n    pass")),
             "syntax error at line 1")
    # Reading is unchanged.
    _exact("no final line break (read_symbol)",
           _read_result("n.py", "def f():\n    pass", lambda a: a.read_symbol("f")), "def f():\n    pass")
    _exact("no final line break (list_symbols)",
           _read_result("n.py", "X = 1\ndef f():\n    pass", lambda a: a.list_symbols()),
           "variable X (line 1)\nfunction f (line 2)")


def test_text_encodings():
    print("\n═══ files that are not UTF-8 text are refused, also without a byte order mark ═══")

    source = "def f():\n    pass\n"
    advice = "; ast-editor reads and writes UTF-8 files only. Convert it to UTF-8, or make this edit with your normal edit tool."
    # (label, raw bytes, what the refusal says the file is)
    cases = [
        ("utf-16 le without a mark (reported)", source.encode("utf-16-le"), "looks like UTF-16 text without a byte order mark"),
        ("utf-16 be without a mark", source.encode("utf-16-be"), "looks like UTF-16 text without a byte order mark"),
        ("utf-32 le without a mark", source.encode("utf-32-le"), "looks like UTF-32 text without a byte order mark"),
        ("utf-32 be without a mark", source.encode("utf-32-be"), "looks like UTF-32 text without a byte order mark"),
        ("utf-16 without a mark, mostly not ascii",
         "def f():\n    return '\u4e2d\u6587\u4e2d\u6587\u4e2d'\n".encode("utf-16-le"),
         "looks like UTF-16 text without a byte order mark"),
        ("utf-16 without a mark, astral characters", "x = '\U0001F600'\n".encode("utf-16-le"),
         "looks like UTF-16 text without a byte order mark"),
        ("utf-32 without a mark, astral characters", "x = '\U0001F600'\n".encode("utf-32-le"),
         "looks like UTF-32 text without a byte order mark"),
        ("utf-16 after a utf-8 mark", b"\xef\xbb\xbf" + source.encode("utf-16-le"),
         "looks like UTF-16 text without a byte order mark"),
        ("utf-16 with a mark", source.encode("utf-16"), "is UTF-16 text (it starts with a UTF-16 byte order mark)"),
        ("a NUL byte in utf-8 text", b"x = 1\ny = '\x00'\n", "is not text (it has a NUL byte on line 2)"),
        ("binary", bytes(range(256)), "is not text (it has a NUL byte on line 1)"),
    ]
    tools = [
        ("list_symbols", lambda a: a.list_symbols()),
        ("read_symbol", lambda a: a.read_symbol("f")),
        ("replace_function", lambda a: a.replace_function("f", "def f():\n    return 1")),
        ("add_top_level", lambda a: a.add_top_level("X = 1")),
    ]
    for label, data, what in cases:
        path = os.path.join(TESTS_DIR, "k.py")
        for tool, action in tools:
            with open(path, "wb") as f:
                f.write(data)
            result = _refusal(lambda: action(Applier(path)))
            _exact(f"encodings: {label} ({tool})", result, f"{path} {what}{advice}")
            check(f"encodings: {label} ({tool}) file unchanged",
                  "<unchanged>" if _read_bytes(path) == data else "CHANGED", "<unchanged>")
        os.remove(path)
    # Other languages and config files too.
    for name in ("k.js", "k.c", "k.yaml", "k.json"):
        path = os.path.join(TESTS_DIR, name)
        with open(path, "wb") as f:
            f.write("a = 1\n".encode("utf-16-le"))
        _exact(f"encodings: utf-16 without a mark ({name})", _refusal(lambda: Applier(path).list_symbols()),
               f"{path} looks like UTF-16 text without a byte order mark{advice}")
        os.remove(path)
    # UTF-8 text without NUL bytes still reads.
    _exact("encodings: utf-8 text reads", _read_result("k.py", "x = '\u4e2d'\n", lambda a: a.list_symbols()),
           "variable x (line 1)")


def test_layout_followups():
    print("\n═══ layout: empty bodies, access labels, tabs, PEP 8 top-level spacing, member templates ═══")

    # replace_function_body on an empty body over two lines indents the
    # content one level deeper than the function.
    body = [
        ("cpp method (reported)", "b.cpp", "class A {\n    void f() {\n    }\n};\n", "A.f", "free(p);",
         "class A {\n    void f() {\n        free(p);\n    }\n};\n"),
        ("cpp blank line inside", "b.cpp", "class A {\n    void f() {\n\n    }\n};\n", "A.f", "free(p);",
         "class A {\n    void f() {\n        free(p);\n    }\n};\n"),
        ("cpp function, file without indentation", "b.cpp", "void f() {\n}\n", "f", "free(p);",
         "void f() {\n  free(p);\n}\n"),
        ("cpp allman braces", "b.cpp", "class A\n{\n    void f()\n    {\n    }\n};\n", "A.f", "free(p);",
         "class A\n{\n    void f()\n    {\n        free(p);\n    }\n};\n"),
        ("cpp tabs", "b.cpp", "class A {\n\tvoid f() {\n\t}\n};\n", "A.f", "free(p);",
         "class A {\n\tvoid f() {\n\t\tfree(p);\n\t}\n};\n"),
        ("java method", "B.java", "class A {\n    void f() {\n    }\n}\n", "A.f", "g();\nh();",
         "class A {\n    void f() {\n        g();\n        h();\n    }\n}\n"),
        ("js method", "b.js", "class A {\n  f() {\n  }\n}\n", "A.f", "g();", "class A {\n  f() {\n    g();\n  }\n}\n"),
        ("js function", "b.js", "function f() {\n}\n", "f", "g();", "function f() {\n  g();\n}\n"),
        ("ts method", "b.ts", "class A {\n    f(): void {\n    }\n}\n", "A.f", "g();",
         "class A {\n    f(): void {\n        g();\n    }\n}\n"),
        ("go function", "b.go", "package main\n\nfunc f() {\n}\n", "f", "g()", "package main\n\nfunc f() {\n\tg()\n}\n"),
        ("go method", "b.go", "package main\n\ntype T struct{}\n\nfunc (t T) f() {\n}\n", "T.f", "g()",
         "package main\n\ntype T struct{}\n\nfunc (t T) f() {\n\tg()\n}\n"),
        ("c function", "b.c", "int g(void) {\n    return 1;\n}\n\nvoid f(void) {\n}\n", "f", "g();",
         "int g(void) {\n    return 1;\n}\n\nvoid f(void) {\n    g();\n}\n"),
        # A body with code or a comment keeps the indentation of its first one.
        ("cpp comment only", "b.cpp", "class A {\n    void f() {\n        // todo\n    }\n};\n", "A.f", "free(p);",
         "class A {\n    void f() {\n        free(p);\n    }\n};\n"),
        ("js blank line before the code", "b.js", "function f() {\n\n    x();\n}\n", "f", "g();",
         "function f() {\n    g();\n}\n"),
    ]
    for label, name, source, target, content, expected in body:
        _exact(f"replace_function_body on an empty body ({label})",
               _edit_result(name, source, lambda a: a.replace_function_body(target, content)), expected)
    _exact("replace_function_body on an empty body (cpp crlf)",
           _edit_result("b.cpp", "class A {\n    void f() {\n    }\n};\n",
                        lambda a: a.replace_function_body("A.f", "free(p);"), "\r\n"),
           "class A {\r\n    void f() {\r\n        free(p);\r\n    }\r\n};\r\n")

    # add_field into a C++ class whose body opens with an access label goes
    # below the label, among the members it gives that access to.
    box = "class Box {\npublic:\n    int get() { return v; }\nprivate:\n    int v;\n};\n"
    fields = [
        ("first section (reported)", box, "Box",
         "class Box {\npublic:\n    int n;\n\n    int get() { return v; }\nprivate:\n    int v;\n};\n"),
        ("field below", "class Box {\nprivate:\n    int v;\n};\n", "Box", "class Box {\nprivate:\n    int n;\n    int v;\n};\n"),
        ("blank line below the label", "class Box {\npublic:\n\n    int get() { return v; }\n};\n", "Box",
         "class Box {\npublic:\n    int n;\n\n    int get() { return v; }\n};\n"),
        ("comment after the label", "class Box {\npublic:  // API\n    int get() { return v; }\n};\n", "Box",
         "class Box {\npublic:  // API\n    int n;\n\n    int get() { return v; }\n};\n"),
        ("comment above the label", "class Box {\n    // c\npublic:\n    int v;\n};\n", "Box",
         "class Box {\n    // c\npublic:\n    int n;\n    int v;\n};\n"),
        ("indented label", "class Box {\n  public:\n    int get() { return v; }\n};\n", "Box",
         "class Box {\n  public:\n    int n;\n\n    int get() { return v; }\n};\n"),
        ("only a label", "class Box {\npublic:\n};\n", "Box", "class Box {\npublic:\n  int n;\n};\n"),
        ("the brace after the label", "class Box {\npublic: };\n", "Box", "class Box {\npublic:\n  int n;\n};\n"),
        ("a member after the label", "class Box {\npublic: int v;\n};\n", "Box",
         "class Box {\npublic:\n  int n;\n  int v;\n};\n"),
        ("body on one line", "class C { public: int x; };\n", "C", "class C {\npublic:\n  int n;\n  int x;\n};\n"),
        ("body on one line, empty section", "class C { public: };\n", "C", "class C {\npublic:\n  int n;\n};\n"),
        ("struct", "struct S {\nprivate:\n    int v;\n};\n", "S", "struct S {\nprivate:\n    int n;\n    int v;\n};\n"),
        ("nested class", "namespace N {\nclass Box {\n public:\n  int v;\n};\n}\n", "N.Box",
         "namespace N {\nclass Box {\n public:\n  int n;\n  int v;\n};\n}\n"),
        ("member template below", "class Box {\npublic:\n    template <typename U>\n    U get() { return U(); }\n};\n", "Box",
         "class Box {\npublic:\n    int n;\n\n    template <typename U>\n    U get() { return U(); }\n};\n"),
        # A class that opens with a member keeps the field first.
        ("no label first", "class Box {\n    int v;\npublic:\n    int get();\n};\n", "Box",
         "class Box {\n    int n;\n    int v;\npublic:\n    int get();\n};\n"),
    ]
    for label, source, target, expected in fields:
        _exact(f"add_field below an access label ({label})",
               _edit_result("f.cpp", source, lambda a: a.add_field(target, "int n;")), expected)
    _exact("add_field below an access label (crlf)",
           _edit_result("f.cpp", "class Box {\npublic:\n    int v;\n};\n", lambda a: a.add_field("Box", "int n;"), "\r\n"),
           "class Box {\r\npublic:\r\n    int n;\r\n    int v;\r\n};\r\n")
    # add_method goes after the last method, in its section.
    _exact("add_method after an access label section",
           _edit_result("f.cpp", box, lambda a: a.add_method("Box", "void f() {}")),
           "class Box {\npublic:\n    int get() { return v; }\n\n    void f() {}\nprivate:\n    int v;\n};\n")

    # insert_sibling next to a member indented with tabs writes the content's
    # indentation in tabs, as add_method does.
    tabs = [
        ("py after (reported)", "t.py", "class A:\n\tdef a(self):\n\t\tpass\n", "A.a", "def c(self):\n    return 1", "after",
         "class A:\n\tdef a(self):\n\t\tpass\n\n\tdef c(self):\n\t\treturn 1\n"),
        ("py before", "t.py", "class A:\n\tdef a(self):\n\t\tpass\n", "A.a", "def c(self):\n    return 1", "before",
         "class A:\n\tdef c(self):\n\t\treturn 1\n\n\tdef a(self):\n\t\tpass\n"),
        ("py two levels", "t.py", "class A:\n\tdef a(self):\n\t\tpass\n", "A.a",
         "def c(self):\n    if x:\n        return 1", "after",
         "class A:\n\tdef a(self):\n\t\tpass\n\n\tdef c(self):\n\t\tif x:\n\t\t\treturn 1\n"),
        ("js", "t.js", "class A {\n\tm() {\n\t\treturn 1;\n\t}\n}\n", "A.m", "k() {\n  return 2;\n}", "after",
         "class A {\n\tm() {\n\t\treturn 1;\n\t}\n\n\tk() {\n\t\treturn 2;\n\t}\n}\n"),
        ("java", "T.java", "class A {\n\tvoid m() {\n\t}\n}\n", "A.m", "void k() {\n    x();\n}", "after",
         "class A {\n\tvoid m() {\n\t}\n\n\tvoid k() {\n\t\tx();\n\t}\n}\n"),
        ("go struct field", "t.go", "package main\n\ntype T struct {\n\tA int\n}\n", "T", "type U struct {\n    B int\n}", "after",
         "package main\n\ntype T struct {\n\tA int\n}\n\ntype U struct {\n\tB int\n}\n"),
        ("rb", "t.rb", "class A\n\tdef m\n\t\t1\n\tend\nend\n", "A.m", "def k\n  2\nend", "before",
         "class A\n\tdef k\n\t\t2\n\tend\n\n\tdef m\n\t\t1\n\tend\nend\n"),
        # Content already in tabs, and members indented with spaces, are
        # left as they are.
        ("py content in tabs", "t.py", "class A:\n\tdef a(self):\n\t\tpass\n", "A.a", "def c(self):\n\treturn 1", "after",
         "class A:\n\tdef a(self):\n\t\tpass\n\n\tdef c(self):\n\t\treturn 1\n"),
        ("py spaces", "t.py", "class A:\n    def a(self):\n        pass\n", "A.a", "def c(self):\n  return 1", "after",
         "class A:\n    def a(self):\n        pass\n\n    def c(self):\n      return 1\n"),
    ]
    for label, name, source, target, content, position, expected in tabs:
        _exact(f"insert_sibling into tab indentation ({label})",
               _edit_result(name, source, lambda a: a.insert_sibling(target, content, position)), expected)

    # add_top_level separates a new top-level Python def or class by two
    # blank lines (PEP 8), at the bottom and at the top, as insert_sibling does.
    top_level = [
        ("def after a def (reported)", "def f():\n    pass\n", "def g():\n    pass", "bottom",
         "def f():\n    pass\n\n\ndef g():\n    pass\n"),
        ("variable after a def", "def f():\n    pass\n", "X = 1", "bottom", "def f():\n    pass\n\n\nX = 1\n"),
        ("def after a variable", "X = 1\n", "def g():\n    pass", "bottom", "X = 1\n\n\ndef g():\n    pass\n"),
        ("variable after a variable", "X = 1\n", "Y = 2", "bottom", "X = 1\n\nY = 2\n"),
        ("decorated def", "X = 1\n", "@dec\ndef g():\n    pass", "bottom", "X = 1\n\n\n@dec\ndef g():\n    pass\n"),
        ("def with a comment", "X = 1\n", "# Doc.\ndef g():\n    pass", "bottom", "X = 1\n\n\n# Doc.\ndef g():\n    pass\n"),
        ("class after blank lines", "def f():\n    pass\n\n\n\n", "class A:\n    pass", "bottom",
         "def f():\n    pass\n\n\nclass A:\n    pass\n"),
        ("top: def before a def (reported)", "def f():\n    pass\n", "def g():\n    pass", "top",
         "def g():\n    pass\n\n\ndef f():\n    pass\n"),
        ("top: variable before a def", "def f():\n    pass\n", "X = 1", "top", "X = 1\n\n\ndef f():\n    pass\n"),
        ("top: def after an import", "import os\n\ndef f():\n    pass\n", "def g():\n    pass", "top",
         "import os\n\n\ndef g():\n    pass\n\n\ndef f():\n    pass\n"),
        ("top: variable between an import and a variable", "import os\n\nX = 1\n", "Y = 2", "top",
         "import os\n\nY = 2\n\nX = 1\n"),
        ("top: def after a docstring", '"""Doc."""\ndef f():\n    pass\n', "def g():\n    pass", "top",
         '"""Doc."""\n\n\ndef g():\n    pass\n\n\ndef f():\n    pass\n'),
        ("top: more blank lines below kept", "import os\n\n\n\nX = 1\n", "Y = 2", "top",
         "import os\n\nY = 2\n\n\n\nX = 1\n"),
        ("top: only imports", "import os\n", "def g():\n    pass", "top", "import os\n\n\ndef g():\n    pass\n"),
        ("top: empty file", "", "def g():\n    pass", "top", "def g():\n    pass\n"),
    ]
    for label, source, content, position, expected in top_level:
        _exact(f"py add_top_level spacing ({label})",
               _edit_result("s.py", source, lambda a: a.add_top_level(content, position)), expected)
    # Other languages get one blank line on each side, also below the new
    # code when the file had none after its preamble.
    _exact("add_top_level spacing (js top)",
           _edit_result("s.js", "import x from 'x';\nfunction f() {}\n", lambda a: a.add_top_level("function g() {}", "top")),
           "import x from 'x';\n\nfunction g() {}\n\nfunction f() {}\n")
    _exact("add_top_level spacing (js bottom)",
           _edit_result("s.js", "function f() {}\n", lambda a: a.add_top_level("function g() {}")),
           "function f() {}\n\nfunction g() {}\n")

    # add_method counts C++ member templates as methods when it decides on
    # the blank line before the new method.
    templates = [
        ("no blank lines (reported)", "class A {\n    int a() { return 1; }\n    template <typename U>\n    U b() { return U(); }\n};\n",
         "class A {\n    int a() { return 1; }\n    template <typename U>\n    U b() { return U(); }\n    int c() { return 3; }\n};\n"),
        ("blank lines", "class A {\n    int a() { return 1; }\n\n    template <typename U>\n    U b() { return U(); }\n};\n",
         "class A {\n    int a() { return 1; }\n\n    template <typename U>\n    U b() { return U(); }\n\n    int c() { return 3; }\n};\n"),
        ("template first", "class A {\n    template <typename U>\n    U b() { return U(); }\n    int a() { return 1; }\n};\n",
         "class A {\n    template <typename U>\n    U b() { return U(); }\n    int a() { return 1; }\n    int c() { return 3; }\n};\n"),
        ("only templates", "class A {\n    template <typename U>\n    U a() { return U(); }\n    template <typename U>\n    U b() { return U(); }\n};\n",
         "class A {\n    template <typename U>\n    U a() { return U(); }\n    template <typename U>\n    U b() { return U(); }\n    int c() { return 3; }\n};\n"),
        # A member class template is no method.
        ("class template", "class A {\n    int a() { return 1; }\n    template <typename U>\n    struct S {};\n};\n",
         "class A {\n    int a() { return 1; }\n    template <typename U>\n    struct S {};\n\n    int c() { return 3; }\n};\n"),
    ]
    for label, source, expected in templates:
        _exact(f"add_method spacing with member templates ({label})",
               _edit_result("m.cpp", source, lambda a: a.add_method("A", "int c() { return 3; }")), expected)
    _exact("add_field above a member template",
           _edit_result("m.cpp", "class A {\n    template <typename U>\n    U b() { return U(); }\n};\n",
                        lambda a: a.add_field("A", "int n;")),
           "class A {\n    int n;\n\n    template <typename U>\n    U b() { return U(); }\n};\n")


def test_yaml_only_item():
    print("\n═══ remove_from_array on the only item of a YAML block sequence leaves [] ═══")

    # (label, source, target, value, expected file text)
    cases = [
        ("reported", "a:\n  - 1\nb: 2\n", "a", "1", "a: []\nb: 2\n"),
        ("not indented", "a:\n- 1\nb: 2\n", "a", "1", "a: []\nb: 2\n"),
        ("anchor, tag and comment", "a: &x !!seq # c\n  - 1\nb: 2\n", "a", "1", "a: &x !!seq [] # c\nb: 2\n"),
        ("comment after the colon", "a:   # list\n  - 1\n", "a", "1", "a: []   # list\n"),
        ("comment line above the item", "c:\n  # lead\n  - 3  # three\nd: 1\n", "c", "3", "c: []\n  # lead\nd: 1\n"),
        ("mapping item", "d:\n  - e: 1\n    f: 2\nz: 1\n", "d", "e: 1\n    f: 2", "d: []\nz: 1\n"),
        ("mapping item at the end of the file", "d:\n  - e: 1\n    f: 2\n", "d", "e: 1\n    f: 2", "d: []\n"),
        ("nested", "a:\n  b:\n    - 1\n  c: 2\n", "a.b", "1", "a:\n  b: []\n  c: 2\n"),
        ("quoted key", '"a b":\n  - 1\n', '"a b"', "1", '"a b": []\n'),
        ("not ascii", "\u00e9:\n  - 1\n", "\u00e9", "1", "\u00e9: []\n"),
        # Other items leave a block sequence.
        ("one of two", "a:\n  - 1\n  - 2\nb: 2\n", "a", "1", "a:\n  - 2\nb: 2\n"),
        ("a mapping item before the next key", "d:\n  - e: 1\n    f: 2\n  - 3\nz: 1\n", "d", "e: 1\n    f: 2",
         "d:\n  - 3\nz: 1\n"),
    ]
    for label, source, target, value, expected in cases:
        _exact(f"yaml remove_from_array ({label})",
               _edit_result("y.yaml", source, lambda a: a.remove_from_array(target, value)), expected)
    _exact("yaml remove_from_array (crlf)",
           _edit_result("y.yaml", "a:\n  - 1\nb: 2\n", lambda a: a.remove_from_array("a", "1"), "\r\n"), "a: []\r\nb: 2\r\n")
    _exact("yaml remove_from_array (then append_to_array)",
           _edit_result("y.yaml", "a:\n  - 1\nb: 2\n",
                        lambda a: (a.remove_from_array("a", "1"), a.append_to_array("a", "5"))), "a: [5]\nb: 2\n")
    _exact("yaml remove_from_array (read back)",
           _read_result("y.yaml", "a:\n  - 1\nb: 2\n",
                        lambda a: (a.remove_from_array("a", "1"), a.read_symbol("a"))[1]), "[]")


def test_ruby_attached_lines():
    print("\n═══ Ruby: a =begin document above a method is its comment, a Sorbet sig part of it ═══")

    doc = "class A\n=begin\nOld doc.\n=end\n  def f\n    1\n  end\nend\n"
    # (label, source, action, expected file text)
    documents = [
        ("remove (reported)", doc, lambda a: a.edit_leading_comment("A.f", "remove"), "class A\n  def f\n    1\n  end\nend\n"),
        ("replace", doc, lambda a: a.edit_leading_comment("A.f", "replace", "# New doc."),
         "class A\n  # New doc.\n  def f\n    1\n  end\nend\n"),
        ("replace with a document", doc, lambda a: a.edit_leading_comment("A.f", "replace", "=begin\nNew.\n=end"),
         "class A\n=begin\nNew.\n=end\n  def f\n    1\n  end\nend\n"),
        ("delete_symbol", doc, lambda a: a.delete_symbol("A.f"), "class A\nend\n"),
        ("delete_symbol keeping the comment", doc, lambda a: a.delete_symbol("A.f", include_leading_comments=False),
         "class A\n=begin\nOld doc.\n=end\nend\n"),
        ("insert_sibling before", doc, lambda a: a.insert_sibling("A.f", "def g\nend", "before"),
         "class A\n  def g\n  end\n\n=begin\nOld doc.\n=end\n  def f\n    1\n  end\nend\n"),
        ("top level", "=begin\nDoc.\n=end\ndef f\nend\n", lambda a: a.edit_leading_comment("f", "remove"), "def f\nend\n"),
        ("with line comments around it", "# a\n=begin\nDoc.\n=end\n# b\ndef f\nend\n",
         lambda a: a.edit_leading_comment("f", "remove"), "def f\nend\n"),
    ]
    for label, source, action, expected in documents:
        _exact(f"rb embedded document as the leading comment ({label})", _edit_result("d.rb", source, action), expected)
    _refused("rb embedded document as the leading comment (add)",
             _edit_result("d.rb", doc, lambda a: a.edit_leading_comment("A.f", "add", "# New doc.")),
             "REFUSED: 'A.f' already has a leading comment (lines 2-4):\n=begin\nOld doc.\n=end\n")
    # A blank line ends it, and an `=end` inside a heredoc is text.
    _refused("rb embedded document as the leading comment (blank line between)",
             _edit_result("d.rb", "x = 1\n=begin\nDoc.\n=end\n\ndef f\nend\n", lambda a: a.edit_leading_comment("f", "remove")),
             "REFUSED: No leading comment found above 'f'")
    _exact("rb embedded document as the leading comment (=end in a heredoc)",
           _edit_result("d.rb", "def g\n  x = <<~EOS\n=end\n  EOS\nend\ndef f\nend\n",
                        lambda a: a.edit_leading_comment("f", "add", "# c")),
           "def g\n  x = <<~EOS\n=end\n  EOS\nend\n# c\ndef f\nend\n")

    # A Sorbet signature directly above a method is part of it.
    sig = "class A\n  sig { void }\n  def f; end\nend\n"
    block = "class A\n  # Doc.\n  sig do\n    params(x: Integer).void\n  end\n  def f(x)\n    x\n  end\n\n  def g; end\nend\n"
    private = "class A\n  sig { void }\n  private def m(x)\n    x\n  end\nend\n"
    reads = [
        ("full", sig, "A.f", "full", "sig { void }\n  def f; end"),
        ("signature", sig, "A.f", "signature", "def f"),
        ("interface", sig, "A.f", "interface", "def f"),
        ("do block", block, "A.f", "full", "sig do\n    params(x: Integer).void\n  end\n  def f(x)\n    x\n  end"),
        ("private def", private, "A.m", "full", "sig { void }\n  private def m(x)\n    x\n  end"),
        ("private def signature", private, "A.m", "signature", "private def m(x)"),
        ("singleton method", "class A\n  sig { void }\n  def self.f; end\nend\n", "A.f", "full", "sig { void }\n  def self.f; end"),
        ("final sig", "class A\n  sig(:final) { void }\n  def f; end\nend\n", "A.f", "full", "sig(:final) { void }\n  def f; end"),
        ("comment between", "class A\n  sig { void }\n  # rubocop:disable X\n  def f; end\nend\n", "A.f", "full",
         "sig { void }\n  # rubocop:disable X\n  def f; end"),
        ("top level", "sig { void }\ndef f\nend\n", "f", "full", "sig { void }\ndef f\nend"),
        # A blank line between them, a sig with a receiver or without a block,
        # is no part of the method.
        ("blank line between", "class A\n  sig { void }\n\n  def f; end\nend\n", "A.f", "full", "def f; end"),
        ("receiver", "class A\n  T.sig { void }\n  def f; end\nend\n", "A.f", "full", "def f; end"),
        ("no block", "class A\n  sig\n  def f; end\nend\n", "A.f", "full", "def f; end"),
    ]
    for label, source, target, depth, expected in reads:
        _exact(f"rb sorbet signature read_symbol ({label})",
               _read_result("s.rb", source, lambda a: a.read_symbol(target, depth)), expected)
    _exact("rb sorbet signature list_symbols (at the sig's line, as decorators)",
           _read_result("s.rb", block, lambda a: a.list_symbols()), "class A (line 1)\n  method A.f (line 3)\n  method A.g (line 10)")
    _listed_targets_resolve("rb sorbet signatures", "s.rb", block)
    _listed_targets_resolve("rb sorbet signature on a private def", "s.rb", private)
    edits = [
        ("insert_sibling before (reported)", sig, lambda a: a.insert_sibling("A.f", "def g; end", "before"),
         "class A\n  def g; end\n\n  sig { void }\n  def f; end\nend\n"),
        ("insert_sibling before, with a comment", block, lambda a: a.insert_sibling("A.f", "def h; end", "before"),
         "class A\n  def h; end\n\n  # Doc.\n  sig do\n    params(x: Integer).void\n  end\n  def f(x)\n    x\n  end\n\n  def g; end\nend\n"),
        ("delete_symbol", sig, lambda a: a.delete_symbol("A.f"), "class A\nend\n"),
        ("delete_symbol with its comment", block, lambda a: a.delete_symbol("A.f"), "class A\n  def g; end\nend\n"),
        ("delete_symbol of a private def", private, lambda a: a.delete_symbol("A.m"), "class A\nend\n"),
        ("replace_function", sig, lambda a: a.replace_function("A.f", "sig { returns(Integer) }\ndef f; 1; end"),
         "class A\n  sig { returns(Integer) }\n  def f; 1; end\nend\n"),
        ("edit_leading_comment add", sig, lambda a: a.edit_leading_comment("A.f", "add", "# Doc."),
         "class A\n  # Doc.\n  sig { void }\n  def f; end\nend\n"),
        ("edit_leading_comment remove", block, lambda a: a.edit_leading_comment("A.f", "remove"),
         "class A\n  sig do\n    params(x: Integer).void\n  end\n  def f(x)\n    x\n  end\n\n  def g; end\nend\n"),
        ("replace_signature keeps it", block, lambda a: a.replace_signature("A.f", "def f(y)"),
         "class A\n  # Doc.\n  sig do\n    params(x: Integer).void\n  end\n  def f(y)\n    x\n  end\n\n  def g; end\nend\n"),
        ("replace_signature with its own", sig, lambda a: a.replace_signature("A.f", "sig { params(x: Integer).void }\ndef f(x)"),
         "class A\n  sig { params(x: Integer).void }\n  def f(x); end\nend\n"),
        ("replace_signature of a private def", private, lambda a: a.replace_signature("A.m", "protected def m(y)"),
         "class A\n  sig { void }\n  protected def m(y)\n    x\n  end\nend\n"),
        ("replace_signature of a private def with its own", private,
         lambda a: a.replace_signature("A.m", "sig { params(y: Integer).void }\nprivate def m(y)"),
         "class A\n  sig { params(y: Integer).void }\n  private def m(y)\n    x\n  end\nend\n"),
        ("add_parameter", block, lambda a: a.add_parameter("A.f", "y"),
         "class A\n  # Doc.\n  sig do\n    params(x: Integer).void\n  end\n  def f(x, y)\n    x\n  end\n\n  def g; end\nend\n"),
        # A sig counts as a decorator does in member spacing.
        ("add_method after signed methods",
         "class A\n  sig { void }\n  def a; end\n\n  sig { void }\n  def b; end\nend\n", lambda a: a.add_method("A", "def c; end"),
         "class A\n  sig { void }\n  def a; end\n\n  sig { void }\n  def b; end\n\n  def c; end\nend\n"),
        ("add_field above a signed method", sig, lambda a: a.add_field("A", "X = 1"),
         "class A\n  X = 1\n\n  sig { void }\n  def f; end\nend\n"),
    ]
    for label, source, action, expected in edits:
        _exact(f"rb sorbet signature ({label})", _edit_result("s.rb", source, action), expected)
    for label, source, target in (("braces", sig, "A.f"), ("do block", block, "A.f"), ("private def", private, "A.m")):
        _exact(f"rb sorbet signature round trip ({label})", _round_trip("s.rb", source, target), "<unchanged>")


def test_comments_ending_code():
    print("\n═══ comment lines below a symbol, indented deeper, end it; block comments over lines ═══")

    js = "class A {\n  m() {}\n    // deep\n  n() {}\n}\n"
    c = "int f(void) {\n    return 1;\n}\n    /* end of f */\n    // more\nint g(void);\n"
    go = "package main\n\nfunc f() {\n}\n\t// end of f\n\nfunc g() {}\n"
    java = "class A {\n    void m() {\n    }\n        // deep\n    /* block\n       more */\n    void n() {}\n}\n"
    rb = "class A\n  def m\n  end\n    # deep\n  def n\n  end\nend\n"
    # (label, file name, source, action, expected file text)
    cases = [
        ("js insert_sibling after (reported)", "c.js", js, lambda a: a.insert_sibling("A.m", "k() {}", "after"),
         "class A {\n  m() {}\n    // deep\n\n  k() {}\n\n  n() {}\n}\n"),
        ("js delete_symbol", "c.js", js, lambda a: a.delete_symbol("A.m"), "class A {\n  n() {}\n}\n"),
        ("js delete_symbol of the method below", "c.js", js, lambda a: a.delete_symbol("A.n"),
         "class A {\n  m() {}\n    // deep\n}\n"),
        ("js leading comment of the method below", "c.js", js, lambda a: a.edit_leading_comment("A.n", "add", "// n"),
         "class A {\n  m() {}\n    // deep\n  // n\n  n() {}\n}\n"),
        ("c two comments", "c.c", c, lambda a: a.insert_sibling("f", "int h(void);", "after"),
         "int f(void) {\n    return 1;\n}\n    /* end of f */\n    // more\n\nint h(void);\n\nint g(void);\n"),
        ("c delete_symbol", "c.c", c, lambda a: a.delete_symbol("f"), "int g(void);\n"),
        ("go insert_sibling after", "c.go", go, lambda a: a.insert_sibling("f", "func h() {}", "after"),
         "package main\n\nfunc f() {\n}\n\t// end of f\n\nfunc h() {}\n\nfunc g() {}\n"),
        ("go delete_symbol", "c.go", go, lambda a: a.delete_symbol("f"), "package main\n\nfunc g() {}\n"),
        # A comment at the symbol's indentation is the next one's.
        ("java insert_sibling after", "C.java", java, lambda a: a.insert_sibling("A.m", "void k() {}", "after"),
         "class A {\n    void m() {\n    }\n        // deep\n\n    void k() {}\n\n    /* block\n       more */\n    void n() {}\n}\n"),
        ("java delete_symbol", "C.java", java, lambda a: a.delete_symbol("A.m"),
         "class A {\n    /* block\n       more */\n    void n() {}\n}\n"),
        ("block comment over lines", "c.js", "class A {\n  m() {}\n      /* deep\n  more */\n  n() {}\n}\n",
         lambda a: a.insert_sibling("A.m", "k() {}", "after"),
         "class A {\n  m() {}\n      /* deep\n  more */\n\n  k() {}\n\n  n() {}\n}\n"),
        ("rb insert_sibling after", "c.rb", rb, lambda a: a.insert_sibling("A.m", "def k\nend", "after"),
         "class A\n  def m\n  end\n    # deep\n\n  def k\n  end\n\n  def n\n  end\nend\n"),
        ("rb delete_symbol", "c.rb", rb, lambda a: a.delete_symbol("A.m"), "class A\n  def n\n  end\nend\n"),
        # A blank line, or code after the comment on its line, ends them.
        ("blank line", "c.js", "class A {\n  m() {}\n\n    // deep\n  n() {}\n}\n",
         lambda a: a.insert_sibling("A.m", "k() {}", "after"), "class A {\n  m() {}\n\n  k() {}\n\n    // deep\n  n() {}\n}\n"),
        ("code after the comment", "c.c", "int f(void);\n    /* x */ int g(void);\n",
         lambda a: a.insert_sibling("f", "int h(void);", "after"), "int f(void);\nint h(void);\n    /* x */ int g(void);\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"comments ending the code above ({label})", _edit_result(name, source, action), expected)
    # read_symbol and replace_function leave the comment out, as before.
    _exact("comments ending the code above (read_symbol)", _read_result("c.js", js, lambda a: a.read_symbol("A.m")), "m() {}")
    _exact("comments ending the code above (round trip)", _round_trip("c.js", js, "A.m"), "<unchanged>")
    _exact("comments ending the code above (replace_function)",
           _edit_result("c.js", js, lambda a: a.replace_function("A.m", "m() { return 1; }")),
           "class A {\n  m() { return 1; }\n    // deep\n  n() {}\n}\n")

    # A block comment after a symbol that goes on over lines, with code
    # after it: the code on both sides shares those lines.
    shared = "int x; /* a\n b */ int y;\n"
    for target in ("x", "y"):
        _exact(f"block comment over lines between symbols (round trip of {target}, reported)",
               _round_trip("b.c", shared, target), "<unchanged>")
    for name, source, target in (
        ("b.js", "function f() {} /* a\n b */ function g() {}\n", "f"),
        ("b.js", "function f() {} /* a\n b */ function g() {}\n", "g"),
        ("b.cpp", "class A {\n  int x; /* a\n   b */ int y;\n};\n", "A.x"),
        ("b.cpp", "class A {\n  int x; /* a\n   b */ int y;\n};\n", "A.y"),
    ):
        _exact(f"block comment over lines between symbols (round trip of {target} in {name})",
               _round_trip(name, source, target), "<unchanged>")
    edits = [
        ("replace_function", shared, lambda a: a.replace_function("x", "int x = 1;"), "int x = 1; /* a\n b */ int y;\n"),
        ("delete_symbol of the first", shared, lambda a: a.delete_symbol("x"), "/* a\n b */ int y;\n"),
        ("delete_symbol of the second", shared, lambda a: a.delete_symbol("y"), "int x; /* a\n b */\n"),
        ("a line break after the comment", "int x; /* a\n b */\nint y;\n", lambda a: a.insert_sibling("x", "int z;", "after"),
         "int x; /* a\n b */\nint z;\nint y;\n"),
        ("delete_symbol, a line break after the comment", "int x; /* a\n b */\nint y;\n", lambda a: a.delete_symbol("x"),
         "int y;\n"),
    ]
    for label, source, action, expected in edits:
        _exact(f"block comment over lines between symbols ({label})", _edit_result("b.c", source, action), expected)
    _refused("block comment over lines between symbols (insert_sibling after)",
             _edit_result("b.c", shared, lambda a: a.insert_sibling("x", "int z;", "after")),
             "REFUSED: 'x' shares its last line with other code")
    _refused("block comment over lines between symbols (insert_sibling before)",
             _edit_result("b.c", shared, lambda a: a.insert_sibling("y", "int z;", "before")),
             "REFUSED: 'y' shares its first line with other code")
    _refused("block comment over lines between symbols (edit_leading_comment)",
             _edit_result("b.c", shared, lambda a: a.edit_leading_comment("y", "add", "// y")),
             "REFUSED: 'y' does not start its line")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def test_target_resolution_followups():
    print("\n═══ containers, namespaces, qualified names, overload spellings, JS fields and methods ═══")

    # add_method and add_field add to the container a name targets among the
    # containers of its scope: the struct a function shares its name with,
    # the struct a typedef declared apart names. A function is refused.
    stat = "struct stat {\n    int size;\n};\nint stat(const char *p) {\n    return 0;\n}\n"
    sigaction = "struct sigaction {\n    int sa_flags;\n};\nint sigaction(int sig) {\n    return 0;\n}\n"
    props = "export interface Props {\n  a: number;\n}\nexport function Props(p: Props) {\n  return p.a;\n}\n"
    node = "typedef struct Node Node;\n\nstruct Node {\n    Node *next;\n};\n"
    # (label, file name, source, action, expected file text)
    cases = [
        ("c add_field to a struct a function shares its name with (reported)", "k.c", stat,
         lambda a: a.add_field("stat", "int mode;"),
         "struct stat {\n    int mode;\n    int size;\n};\nint stat(const char *p) {\n    return 0;\n}\n"),
        ("cpp add_method", "k.cpp", sigaction, lambda a: a.add_method("sigaction", "void reset();"),
         "struct sigaction {\n    int sa_flags;\n\n    void reset();\n};\nint sigaction(int sig) {\n    return 0;\n}\n"),
        ("cpp add_field", "k.cpp", sigaction, lambda a: a.add_field("sigaction", "int sa_mask;"),
         "struct sigaction {\n    int sa_mask;\n    int sa_flags;\n};\nint sigaction(int sig) {\n    return 0;\n}\n"),
        ("ts add_field to an interface a function shares its name with", "k.ts", props,
         lambda a: a.add_field("Props", "b: string;"),
         "export interface Props {\n  b: string;\n  a: number;\n}\nexport function Props(p: Props) {\n  return p.a;\n}\n"),
        ("c add_field through a typedef declared apart", "k.c", node, lambda a: a.add_field("Node", "int v;"),
         "typedef struct Node Node;\n\nstruct Node {\n    int v;\n    Node *next;\n};\n"),
        ("c add_field to the struct by its keyword", "k.c", stat, lambda a: a.add_field("struct stat", "int mode;"),
         "struct stat {\n    int mode;\n    int size;\n};\nint stat(const char *p) {\n    return 0;\n}\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"container targets ({label})", _edit_result(name, source, action), expected)
    for label, name, source, target in [
        ("cpp", "k.cpp", "void f() {\n  return;\n}\n", "f"),
        ("java", "K.java", "class A {\n  void f() {\n    return;\n  }\n}\n", "A.f"),
        ("rb", "k.rb", "def f\n  1\nend\n", "f"),
        ("ts", "k.ts", "function f() {\n  return;\n}\n", "f"),
        ("js const function", "k.js", "const f = () => {\n  return;\n};\n", "f"),
        ("py", "k.py", "def f():\n    return 1\n", "f"),
        ("c prototype", "k.h", "int f(void);\n", "f"),
    ]:
        for tool in ("add_field", "add_method"):
            _refused(f"container targets ({tool} on a function, {label})",
                     _edit_result(name, source, lambda a: getattr(a, tool)(target, "int x;")),
                     f"'{target}' is a function, not a class, so add_method and add_field cannot add to it; "
                     "add to its body with insert_in_body")

    # In a namespace opened again, a name declared in one of its blocks is
    # found before a member of a class in another.
    ns = "namespace ns {\nstruct A {\n    int count;\n};\n}\n\nnamespace ns {\nint count() { return 1; }\n}\n"
    tsns = "namespace N {\n  export class A {\n    reset = 1;\n  }\n}\n\nnamespace N {\n  export function reset() {}\n}\n"
    outside = ("namespace ns {\nclass A {\npublic:\n    void f(int);\n    void f(double);\n    template <typename T> T g(T);\n};\n}\n\n"
               "namespace ns {\nvoid A::f(int) {}\nvoid A::f(double) {}\ntemplate <typename T> T A::g(T t) { return t; }\n}\n")
    cases = [
        ("cpp read_symbol (reported)", "k.cpp", ns, lambda a: a.read_symbol("ns.count"), "int count() { return 1; }"),
        ("ts read_symbol", "k.ts", tsns, lambda a: a.read_symbol("N.reset"), "export function reset() {}"),
        ("cpp out-of-line definition in another block", "k.cpp", outside, lambda a: a.read_symbol("ns.g"),
         "template <typename T> T A::g(T t) { return t; }"),
        ("cpp overloads defined in another block", "k.cpp", outside, lambda a: a.read_symbol("ns.f"),
         "REFUSED: 'ns.f' is overloaded: ns.A::f(int) (line 11), ns.A::f(double) (line 12); add the parameter types."),
        ("cpp the class member by its path", "k.cpp", ns, lambda a: a.read_symbol("ns.A.count"), "int count;"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"reopened namespaces ({label})", _read_result(name, source, action), expected)
    _exact("reopened namespaces (cpp delete_symbol)", _edit_result("k.cpp", ns, lambda a: a.delete_symbol("ns.count")),
           "namespace ns {\nstruct A {\n    int count;\n};\n}\n\nnamespace ns {\n}\n")
    _exact("reopened namespaces (ts delete_symbol)", _edit_result("k.ts", tsns, lambda a: a.delete_symbol("N.reset")),
           "namespace N {\n  export class A {\n    reset = 1;\n  }\n}\n\nnamespace N {\n}\n")
    for label, name, source in [("cpp", "k.cpp", ns), ("ts", "k.ts", tsns), ("cpp out-of-line", "k.cpp", outside)]:
        _listed_targets_resolve(f"reopened namespaces ({label})", name, source)

    # A class or namespace declared with its scope, and a partial
    # specialization whose template arguments hold a `::`.
    pimpl = "struct A {\n    struct B;\n};\nstruct A::B {\n    int x;\n};\n"
    nested = "namespace a::b {\nvoid f();\n}\n"
    special = ("#include <vector>\ntemplate <typename T>\nstruct S {\n    int a;\n};\n\n"
               "template <typename U>\nstruct S<std::vector<U>> {\n    int b;\n};\n")
    cases = [
        ("read_symbol of a class defined with its scope (reported)", "k.cpp", pimpl, lambda a: a.read_symbol("A::B"),
         "struct A::B {\n    int x;\n};"),
        ("its last name", "k.cpp", pimpl, lambda a: a.read_symbol("B"), "struct A::B {\n    int x;\n};"),
        ("its field", "k.cpp", pimpl, lambda a: a.read_symbol("A::B.x"), "int x;"),
        ("the declaration in its class", "k.cpp", pimpl, lambda a: a.read_symbol("A.B"), "struct B;"),
        ("a nested namespace definition", "k.cpp", nested, lambda a: a.read_symbol("a::b"), "namespace a::b {\nvoid f();\n}"),
        ("a partial specialization", "k.cpp", special, lambda a: a.read_symbol("S<std::vector<U>>"),
         "template <typename U>\nstruct S<std::vector<U>> {\n    int b;\n};"),
        ("the template it specializes", "k.cpp", special, lambda a: a.read_symbol("S"),
         "template <typename T>\nstruct S {\n    int a;\n};"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"qualified names ({label})", _read_result(name, source, action), expected)
    cases = [
        ("delete_symbol of a nested namespace", "k.cpp", nested, lambda a: a.delete_symbol("a::b"), "\n"),
        ("edit_leading_comment of a nested namespace", "k.cpp", nested,
         lambda a: a.edit_leading_comment("a::b", "add", "// ns"), "// ns\nnamespace a::b {\nvoid f();\n}\n"),
        ("add_field to a class defined with its scope", "k.cpp", pimpl, lambda a: a.add_field("A::B", "int y;"),
         "struct A {\n    struct B;\n};\nstruct A::B {\n    int y;\n    int x;\n};\n"),
        ("delete_symbol of a partial specialization", "k.cpp", special, lambda a: a.delete_symbol("S<std::vector<U>>"),
         "#include <vector>\ntemplate <typename T>\nstruct S {\n    int a;\n};\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"qualified names ({label})", _edit_result(name, source, action), expected)
    for label, source in [("class defined with its scope", pimpl), ("nested namespace", nested), ("partial specialization", special)]:
        _listed_targets_resolve(f"qualified names ({label})", "k.cpp", source)

    # A definition outside the preprocessor conditionals is the target, not
    # one in `#if 0` before it.
    dead = "#if 0\nint f(void) {\n    return 0; /* old */\n}\n#endif\n\nint f(void) {\n    return 1;\n}\n"
    _exact("#if 0 (list_symbols, reported)", _read_result("k.c", dead, lambda a: a.list_symbols()), "function f (line 7)")
    _exact("#if 0 (read_symbol)", _read_result("k.c", dead, lambda a: a.read_symbol("f")), "int f(void) {\n    return 1;\n}")
    _exact("#if 0 (replace_in_body)", _edit_result("k.c", dead, lambda a: a.replace_in_body("f", "return 1;", "return 2;")),
           dead.replace("return 1;", "return 2;"))
    _listed_targets_resolve("#if 0", "k.c", dead)

    # Spellings of one C/C++ type are one type: a prototype and a definition
    # that spell their parameters differently declare one function.
    same = [
        ("a const parameter (reported)", "void f(int a);\nvoid f(const int a) {}\n", "void f(const int a) {}"),
        ("unsigned", "void f(unsigned);\nvoid f(unsigned int x) {}\n", "void f(unsigned int x) {}"),
        ("const after the type", "void f(const char*);\nvoid f(char const *s) {}\n", "void f(char const *s) {}"),
        ("long long int", "void f(long long);\nvoid f(long long int v) {}\n", "void f(long long int v) {}"),
        ("struct keyword", "struct S;\nvoid f(struct S *);\nvoid f(S *s) {}\n", "void f(S *s) {}"),
        ("array and pointer", "void f(int a[]);\nvoid f(int *a) {}\n", "void f(int *a) {}"),
        ("const pointer", "void f(char *const p);\nvoid f(char *p) {}\n", "void f(char *p) {}"),
        ("names in a function pointer", "void f(int (*cb)(int x));\nvoid f(int (*cb)(int y)) {}\n",
         "void f(int (*cb)(int y)) {}"),
    ]
    for label, source, definition in same:
        _exact(f"type spellings ({label})", _read_result("k.cpp", source, lambda a: a.read_symbol("f")), definition)
        _listed_targets_resolve(f"type spellings ({label})", "k.cpp", source)
    _exact("type spellings (list_symbols)", _read_result("k.cpp", same[0][1], lambda a: a.list_symbols()), "function f (line 2)")
    overloads = "void f(int a);\nvoid f(double a);\nvoid f(const int a) {}\n"
    _exact("type spellings (overloads, list_symbols)", _read_result("k.cpp", overloads, lambda a: a.list_symbols()),
           "function f(double) (line 2)\nfunction f(const int) (line 3)")
    for written in ("f(int)", "f(const int)", "f(int const)"):
        _exact(f"type spellings (overloads, read_symbol('{written}'))",
               _read_result("k.cpp", overloads, lambda a: a.read_symbol(written)), "void f(const int a) {}")
    _exact("type spellings (overloads, read_symbol('f(double)'))",
           _read_result("k.cpp", overloads, lambda a: a.read_symbol("f(double)")), "void f(double a);")
    # Parameter types are shown and matched without the names of a function
    # pointer's parameters, and without attributes.
    pointer = "void f(int (*cb)(int x)) {}\nvoid f(double d) {}\n"
    _exact("parameter names in a function pointer (list_symbols)", _read_result("k.cpp", pointer, lambda a: a.list_symbols()),
           "function f(int (*)(int)) (line 1)\nfunction f(double) (line 2)")
    _exact("parameter names in a function pointer (read_symbol)",
           _read_result("k.cpp", pointer, lambda a: a.read_symbol("f(int (*)(int))")), "void f(int (*cb)(int x)) {}")
    attribute = "class A {\n  void m([[maybe_unused]] int x);\n  void m(long double);\n};\n"
    _exact("parameter attribute (list_symbols)", _read_result("k.cpp", attribute, lambda a: a.list_symbols()),
           "class A (line 1)\n  method A.m(int) (line 2)\n  method A.m(long double) (line 3)")
    _exact("parameter attribute (read_symbol)", _read_result("k.cpp", attribute, lambda a: a.read_symbol("A.m(int)")),
           "void m([[maybe_unused]] int x);")
    for label, source in [("pointer", pointer), ("attribute", attribute)]:
        _listed_targets_resolve(f"parameter {label}", "k.cpp", source)
    # A struct has no parameters.
    tag = "struct A {\n    void m(int);\n    void m(double);\n};\nint A(int);\n"
    _exact("keyword target with parameter types", _read_result("k.cpp", tag, lambda a: a.read_symbol("struct A(int)")),
           "REFUSED: Target 'struct A(int)' not found in " + os.path.join(TESTS_DIR, "k.cpp"))
    _exact("keyword target with parameter types (the function)", _read_result("k.cpp", tag, lambda a: a.read_symbol("A(int)")),
           "int A(int);")

    # A typedef of a struct declared apart points to the struct's target.
    for depth, reason in [("signature", "which has no signature (depth='signature' is for functions and class headers)"),
                          ("interface", "which has no interface (depth='interface' is for classes and functions)")]:
        _exact(f"typedef of a struct declared apart (depth {depth})", _read_result("k.c", node, lambda a: a.read_symbol("Node", depth)),
               f"REFUSED: 'Node' is a type alias, {reason}; read it with depth='full', and the struct it names with 'struct Node'")
    _exact("typedef of a struct defined in it (depth interface)",
           _read_result("k.c", "typedef struct N {\n    int v;\n} N;\n", lambda a: a.read_symbol("N", "interface")),
           "typedef struct N {\n    int v;\n} N;")

    # replace_value on a C variable that its struct's tag name shares.
    for label, source, target, expected in [
        ("with a value (reported)", "struct S { int x; } S = {0};\n", "S", "struct S { int x; } S = {1};\n"),
        ("without one", "struct S { int x; } S;\n", "S", "struct S { int x; } S = {1};\n"),
        ("union", "union u { int i; } u;\n", "u", "union u { int i; } u = {1};\n"),
    ]:
        _exact(f"replace_value on a variable of its struct's name ({label})",
               _edit_result("k.c", source, lambda a: a.replace_value(target, "{1}")), expected)
    _refused("replace_value on a struct by its keyword",
             _edit_result("k.c", "struct S { int x; } S;\n", lambda a: a.replace_value("struct S", "{1}")),
             "'struct S' is a struct, which has no value")

    # A Go constant without a value repeats the expression before it, as do
    # those after it without one: a value for it would change them.
    iota = "package p\n\nconst (\n\tA = iota\n\tB\n\tC\n)\n"
    _refused("go constant repeated by the next (reported)", _edit_result("k.go", iota, lambda a: a.replace_value("B", "5")),
             "'B' has no value of its own: it repeats the expression of the constant above it, and so does 'C' below "
             "it, which a value for 'B' would change too; give 'C' its own value first")
    _refused("go constant repeated by several",
             _edit_result("k.go", "package p\n\nconst (\n\tA = iota\n\tB\n\t// c\n\tC\n\tD\n\tE = 9\n)\n",
                          lambda a: a.replace_value("B", "5")),
             "and so do 'C', 'D' below it, which a value for 'B' would change too; give 'C', 'D' their own values first")
    _exact("go last constant of the group", _edit_result("k.go", iota, lambda a: a.replace_value("C", "5")),
           "package p\n\nconst (\n\tA = iota\n\tB\n\tC = 5\n)\n")
    _exact("go constant before one with a value",
           _edit_result("k.go", "package p\n\nconst (\n\tA = iota\n\tB\n\tC = 7\n)\n", lambda a: a.replace_value("B", "5")),
           "package p\n\nconst (\n\tA = iota\n\tB = 5\n\tC = 7\n)\n")

    # JS/TS: a name a method shares with a class field (a static one, as a
    # flag) or a `var` targets the method or function.
    run = "class A {\n  static run = false;\n\n  run() {\n    return 1;\n  }\n}\n"
    cases = [
        ("list_symbols (reported)", "k.js", run, lambda a: a.list_symbols(), "class A (line 1)\n  method A.run (line 4)"),
        ("read_symbol", "k.js", run, lambda a: a.read_symbol("A.run"), "run() {\n    return 1;\n  }"),
        ("getter", "k.js", "class A {\n  static name = null;\n  get name() {\n    return 1;\n  }\n}\n",
         lambda a: a.list_symbols(), "class A (line 1)\n  method A.name (line 3)"),
        ("var and function", "k.js", "var f = 1;\n\nfunction f() {\n  return 2;\n}\n", lambda a: a.list_symbols(),
         "function f (line 3)"),
        ("var and function (read_symbol)", "k.js", "var f = 1;\n\nfunction f() {\n  return 2;\n}\n",
         lambda a: a.read_symbol("f"), "function f() {\n  return 2;\n}"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"method and field of one name ({label})", _read_result(name, source, action), expected)
    cases = [
        ("replace_function", "k.js", run, lambda a: a.replace_function("A.run", "run() {\n  return 2;\n}"),
         "class A {\n  static run = false;\n\n  run() {\n    return 2;\n  }\n}\n"),
        ("delete_symbol", "k.js", run, lambda a: a.delete_symbol("A.run"), "class A {\n  static run = false;\n}\n"),
        ("replace_function_body", "k.js", run, lambda a: a.replace_function_body("A.run", "return 2;"),
         "class A {\n  static run = false;\n\n  run() {\n    return 2;\n  }\n}\n"),
        ("ts add_parameter", "k.ts", "class A {\n  static run: boolean = false;\n\n  run(): number {\n    return 1;\n  }\n}\n",
         lambda a: a.add_parameter("A.run", "x: number"),
         "class A {\n  static run: boolean = false;\n\n  run(x: number): number {\n    return 1;\n  }\n}\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"method and field of one name ({label})", _edit_result(name, source, action), expected)
    _listed_targets_resolve("method and field of one name", "k.js", run)

    # replace_function of a JS/TS class field with a method drops the `;`
    # that read_symbol shows as the field's.
    cases = [
        ("js (reported)", "k.js", "class A {\n  x = 1;\n  m() {}\n}\n", "k() {\n  return 1;\n}",
         "class A {\n  k() {\n    return 1;\n  }\n  m() {}\n}\n"),
        ("ts", "k.ts", "class A {\n  x: number = 1;\n  m() {}\n}\n", "k(): number {\n  return 1;\n}",
         "class A {\n  k(): number {\n    return 1;\n  }\n  m() {}\n}\n"),
        ("a field keeps it", "k.js", "class A {\n  x = 1;\n  m() {}\n}\n", "y = 2", "class A {\n  y = 2;\n  m() {}\n}\n"),
        ("on one line", "k.js", "class A { x = 1; m() {} }\n", "k() {}", "class A { k() {} m() {} }\n"),
        ("a field on one line", "k.js", "class A { x = 1; m() {} }\n", "y = 2", "class A { y = 2; m() {} }\n"),
    ]
    for label, name, source, content, expected in cases:
        _exact(f"field replaced by a method ({label})",
               _edit_result(name, source, lambda a: a.replace_function("A.x", content)), expected)

    # TS overload signatures are one symbol with a decorated implementation
    # (decorators go on the implementation), and with a #private or quoted
    # name.
    decorated = "class K {\n  // m lead\n  m(a: string): void;\n  m(a: number): void;\n  @dec()\n  m(a: any) {}\n\n  n() {}\n}\n"
    cases = [
        ("list_symbols (reported)", lambda a: a.list_symbols(), "class K (line 1)\n  method K.m (line 3)\n  method K.n (line 8)"),
        ("read_symbol", lambda a: a.read_symbol("K.m"), "m(a: string): void;\n  m(a: number): void;\n  @dec()\n  m(a: any) {}"),
        ("signature", lambda a: a.read_symbol("K.m", "signature"), "m(a: any)"),
    ]
    for label, action, expected in cases:
        _exact(f"overloads of a decorated method ({label})", _read_result("k.ts", decorated, action), expected)
    cases = [
        ("delete_symbol", lambda a: a.delete_symbol("K.m"), "class K {\n  n() {}\n}\n"),
        ("insert_sibling before", lambda a: a.insert_sibling("K.m", "q() {}", "before"),
         "class K {\n  q() {}\n\n  // m lead\n  m(a: string): void;\n  m(a: number): void;\n  @dec()\n  m(a: any) {}\n\n  n() {}\n}\n"),
        ("edit_leading_comment remove", lambda a: a.edit_leading_comment("K.m", "remove"),
         "class K {\n  m(a: string): void;\n  m(a: number): void;\n  @dec()\n  m(a: any) {}\n\n  n() {}\n}\n"),
        ("add_parameter", lambda a: a.add_parameter("K.m", "b: any"), decorated.replace("m(a: any) {}", "m(a: any, b: any) {}")),
    ]
    for label, action, expected in cases:
        _exact(f"overloads of a decorated method ({label})", _edit_result("k.ts", decorated, action), expected)
    _exact("overloads of a decorated method (round trip)", _round_trip("k.ts", decorated, "K.m"), "<unchanged>")
    _exact("overloads of a decorated method (replace_signature round trip)",
           _edit_result("k.ts", decorated, lambda a: a.replace_signature("K.m", a.read_symbol("K.m", "signature"))), decorated)
    _listed_targets_resolve("overloads of a decorated method", "k.ts", decorated)
    for label, source, target in [
        ("#private (reported)", "class E {\n  #m(a: true): number;\n  #m(a: boolean): number {\n    return 1;\n  }\n}\n", "E.#m"),
        ("quoted", "class E {\n  'm'(a: true): number;\n  'm'(a: boolean): number {\n    return 1;\n  }\n}\n", "E.'m'"),
        ("double-quoted", 'class E {\n  "m"(a: true): number;\n  "m"(a: boolean): number {\n    return 1;\n  }\n}\n', 'E."m"'),
    ]:
        _exact(f"overloads of a {label} method (round trip)", _round_trip("k.ts", source, target), "<unchanged>")
        _exact(f"overloads of a {label} method (crlf round trip)", _round_trip("k.ts", source, target, "\r\n"), "<unchanged>")

    # Computed and quoted method names with dots in them are targets.
    computed = "class E {\n  [Symbol.iterator]() {\n    return 1;\n  }\n  'a.b'() {}\n  m() {}\n}\n"
    _exact("computed method name (read_symbol)", _read_result("k.ts", computed, lambda a: a.read_symbol("E.[Symbol.iterator]")),
           "[Symbol.iterator]() {\n    return 1;\n  }")
    _exact("quoted method name with a dot (read_symbol)", _read_result("k.ts", computed, lambda a: a.read_symbol("E.'a.b'")),
           "'a.b'() {}")
    _exact("computed method name (replace_function_body)",
           _edit_result("k.ts", computed, lambda a: a.replace_function_body("E.[Symbol.iterator]", "return 2;")),
           computed.replace("return 1;", "return 2;"))
    _listed_targets_resolve("computed and quoted method names", "k.ts", computed)
    _listed_targets_resolve("computed and quoted method names (js)", "k.js", computed)

    # Members are listed once, under the first of the merged declarations.
    merged = "class C {\n  m() {}\n}\nnamespace C {\n  export const k = 1;\n}\ninterface C {\n  n(): void;\n}\n"
    _exact("class, namespace and interface merged (list_symbols)", _read_result("k.ts", merged, lambda a: a.list_symbols()),
           "class C (line 1)\n  method C.m (line 2)\n  constant C.k (line 5)\ninterface interface C (line 7)")
    _listed_targets_resolve("class, namespace and interface merged", "k.ts", merged)
    # A Java class that a field's name takes: its members are listed, as
    # they are found through it.
    java = "class A {\n  int B;\n  class B {\n    void m() {}\n  }\n  void B() {}\n  enum C { X }\n  int C;\n}\n"
    _exact("java class sharing a field's name (list_symbols)", _read_result("A.java", java, lambda a: a.list_symbols()),
           "class A (line 1)\n  field A.B (line 2)\n  method A.B.m (line 4)\n  method A.B() (line 6)\n  enum A.C (line 7)")
    _listed_targets_resolve("java class sharing a field's name", "A.java", java)

    # TS namespace interface with a comment after its `}`.
    for label, source, expected in [
        ("namespace (reported)", "namespace N {\n  export const k = 1;\n} // n\n", "namespace N {\n  export const k = 1;\n}"),
        ("empty namespace", "namespace N {} // n\n", "namespace N {\n}"),
        ("exported", "export namespace N {\n  export function g() {}\n} // N\n", "export namespace N {\n  export function g() ...\n}"),
        ("declared", "declare namespace N {\n  function g(): void;\n} // N\n", "declare namespace N {\n  function g(): void;\n}"),
        ("module", "module M {\n  export const k = 1;\n} // n\n", "module M {\n  export const k = 1;\n}"),
    ]:
        target = "M" if label == "module" else "N"
        _exact(f"interface of a {label} with a comment after it",
               _read_result("k.ts", source, lambda a: a.read_symbol(target, "interface")), expected)

    # Go: a func literal that is one value of several has a signature of
    # its own.
    pq = "package main\n\nvar p, q = func(x int) {\n\tprintln(x)\n}, func(y int) {\n\tprintln(y)\n}\n"
    for target, signature in [("q", "func(y int)"), ("p", "func(x int)")]:
        for depth in ("signature", "interface"):
            _exact(f"go func literal of several values ({target}, {depth})",
                   _read_result("k.go", pq, lambda a: a.read_symbol(target, depth)), signature)
        _exact(f"go func literal of several values ({target}, replace_signature round trip)",
               _edit_result("k.go", pq, lambda a: a.replace_signature(target, a.read_symbol(target, "signature"))), pq)
    _exact("go func literal of several values (replace_signature)",
           _edit_result("k.go", pq, lambda a: a.replace_signature("q", "func(z int)")), pq.replace("func(y int)", "func(z int)"))

    # A second TS `this` parameter is a repeated name.
    _refused("add_parameter of a second this", _edit_result("k.ts", "function f(this: Window, a: number) {}\n",
                                                               lambda a: a.add_parameter("f", "this: Foo")),
             "Parameter 'this' already exists in 'f'")

    # CommonJS requires are imports: a new import goes with them (a
    # require at its sorted place among sorted requires).
    cjs = "const fs = require('fs');\nconst path = require('path');\n\nfunction f() {}\n"
    for label, text, expected in [
        ("require (reported)", "const os = require('os');",
         "const fs = require('fs');\nconst os = require('os');\nconst path = require('path');\n\nfunction f() {}\n"),
        ("es import", "import os from 'os';",
         "const fs = require('fs');\nconst path = require('path');\nimport os from 'os';\n\nfunction f() {}\n"),
    ]:
        _exact(f"add_import after requires ({label})", _edit_result("k.js", cjs, lambda a: a.add_import(text)), expected)
    _exact("add_import after requires (destructured and bare)",
           _edit_result("k.js", "const { a } = require('b').c;\nrequire('x');\n\nf();\n", lambda a: a.add_import("const y = require('y');")),
           "const { a } = require('b').c;\nrequire('x');\nconst y = require('y');\n\nf();\n")
    _exact("add_import after requires (a call is no require)",
           _edit_result("k.js", "const v = load('x');\n", lambda a: a.add_import("const y = require('y');")),
           "const y = require('y');\n\nconst v = load('x');\n")
    _exact("add_top_level top after requires",
           _edit_result("k.js", "'use strict';\nconst fs = require('fs');\n\nfunction f() {}\n",
                        lambda a: a.add_top_level("const X = 1;", position="top")),
           "'use strict';\nconst fs = require('fs');\n\nconst X = 1;\n\nfunction f() {}\n")

    # add_top_level at the bottom of a header goes inside its include guard.
    for label, source, expected in [
        ("reported", "/* license */\n#ifndef X_H\n#define X_H\n\nint f(void);\n\n#endif /* X_H */\n",
         "/* license */\n#ifndef X_H\n#define X_H\n\nint f(void);\n\nint g(void);\n\n#endif /* X_H */\n"),
        ("no blank lines", "#ifndef X_H\n#define X_H\nint f(void);\n#endif\n",
         "#ifndef X_H\n#define X_H\nint f(void);\n\nint g(void);\n#endif\n"),
        ("empty guard", "#ifndef X_H\n#define X_H\n#endif\n", "#ifndef X_H\n#define X_H\n\nint g(void);\n#endif\n"),
        ("code after the guard", "#ifndef X_H\n#define X_H\n#endif\nint f(void);\n",
         "#ifndef X_H\n#define X_H\n#endif\nint f(void);\n\nint g(void);\n"),
    ]:
        _exact(f"add_top_level bottom in a header ({label})",
               _edit_result("k.h", source, lambda a: a.add_top_level("int g(void);")), expected)
        _exact(f"add_top_level bottom in a header ({label}, crlf)",
               _edit_result("k.h", source, lambda a: a.add_top_level("int g(void);"), "\r\n"), expected.replace("\n", "\r\n"))


# ──────────────────────────────────────────────
# Body snippets and anchors: token boundaries, whole lines, shifted indentation
# ──────────────────────────────────────────────


def test_body_snippets():
    print("\n═══ body snippets and anchors: tokens, whole lines, shifted indentation ═══")

    # A snippet or anchor matches where it neither starts nor ends inside a
    # token (an identifier, number, keyword or operator). Inside a string or
    # a comment the text is words, and a match may not split one of those.
    maxed = "def f():\n    max = 10\n    return max\n"
    dollar = "function f() {\n  const $el = 1;\n  return $el;\n}\n"
    asks = "def f\n  foo?\nend\n"
    equals = "function f() {\n  return a == 1;\n}\n"
    # (label, file name, source, action, expected file text)
    cases = [
        ("one no longer ambiguous", "k.py", "def f():\n    max = 1\n    x = 1\n",
         lambda a: a.replace_in_body("f", "x = 1", "x = 2"), "def f():\n    max = 1\n    x = 2\n"),
        ("a word of a string", "k.py", 'def f():\n    print("hello world")\n',
         lambda a: a.replace_in_body("f", "world", "there"), 'def f():\n    print("hello there")\n'),
        ("a word of a comment", "k.js", "function f() {\n  // max retries\n  return 1;\n}\n",
         lambda a: a.replace_in_body("f", "retries", "attempts"), "function f() {\n  // max attempts\n  return 1;\n}\n"),
        ("a whole js identifier", "k.js", dollar, lambda a: a.replace_in_body("f", "$el = 1", "$el = 2"),
         dollar.replace("$el = 1", "$el = 2")),
        ("a whole ruby method name", "k.rb", asks, lambda a: a.replace_in_body("f", "foo?", "bar?"), "def f\n  bar?\nend\n"),
        ("a whole operator", "k.js", equals, lambda a: a.replace_in_body("f", "== 1", "=== 1"),
         equals.replace("==", "===")),
        ("an anchor in the middle of a line", "k.py", "def f():\n    g(b)\n",
         lambda a: a.insert_in_body("f", "a, ", after="g("), "def f():\n    g(a, b)\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"token boundaries ({label})", _edit_result(name, source, action), expected)
    # (label, file name, source, action, reason)
    refusals = [
        ("delete_in_body (reported)", "k.py", maxed, lambda a: a.delete_in_body("f", "x = 1"),
         "Snippet not found in body of 'f' as whole tokens: it occurs only inside longer tokens, on line 2."),
        ("replace_in_body (reported)", "k.py", maxed, lambda a: a.replace_in_body("f", "x = 1", "x = 2"),
         "Snippet not found in body of 'f' as whole tokens: it occurs only inside longer tokens, on line 2."),
        ("insert_in_body", "k.py", maxed, lambda a: a.insert_in_body("f", "y = 0", after="ax"),
         "Anchor snippet not found in body of 'f' as whole tokens: it occurs only inside longer tokens, on lines 2, 3."),
        ("a word of a string split", "k.py", 'def f():\n    print("max = 10")\n',
         lambda a: a.replace_in_body("f", "x = 1", "y"), "Snippet not found in body of 'f' as whole tokens"),
        ("part of a js identifier", "k.js", dollar, lambda a: a.replace_in_body("f", "el = 1", "el = 2"),
         "Snippet not found in body of 'f' as whole tokens"),
        ("part of a ruby method name", "k.rb", asks, lambda a: a.replace_in_body("f", "foo", "bar"),
         "Snippet not found in body of 'f' as whole tokens"),
        ("part of an operator", "k.js", equals, lambda a: a.replace_in_body("f", "= 1", "= 2"),
         "Snippet not found in body of 'f' as whole tokens"),
        ("part of a go number", "k.go", "package main\n\nfunc f() int {\n\treturn 100\n}\n",
         lambda a: a.replace_in_body("f", "10", "20"), "Snippet not found in body of 'f' as whole tokens"),
        ("part of a java identifier", "K.java", "class K {\n    void f() {\n        counter++;\n    }\n}\n",
         lambda a: a.delete_in_body("K.f", "count"), "Snippet not found in body of 'K.f' as whole tokens"),
        ("part of a word of a comment", "k.cpp", "int f() {\n    // retries\n    return 0;\n}\n",
         lambda a: a.replace_in_body("f", "tries", "x"), "Snippet not found in body of 'f' as whole tokens"),
        ("part of the code in an f-string", "k.py", 'def f(maxval):\n    return f"{maxval}"\n',
         lambda a: a.replace_in_body("f", "val", "v"), "Snippet not found in body of 'f' as whole tokens"),
        ("ambiguous, with the lines", "k.py", "def f():\n    a = 1\n    b = 1\n",
         lambda a: a.replace_in_body("f", "1", "2"),
         "Snippet matches 2 places in body of 'f' (lines 2, 3). Include more surrounding context"),
    ]
    for label, name, source, action, reason in refusals:
        _refused(f"token boundaries ({label})", _edit_result(name, source, action), reason)

    # A deletion that leaves its lines without code takes them whole, with
    # their indentation and line break; a comment after it stays, at the
    # line's indentation. A Python body keeps a statement.
    body = "class A:\n    def f(self):\n        x = 1\n        if x:\n            return 2\n"
    no_x = "class A:\n    def f(self):\n        if x:\n            return 2\n"
    cases = [
        ("a line without its indentation (reported)", "k.py", body, lambda a: a.delete_in_body("A.f", "x = 1"), no_x),
        ("a line with its indentation", "k.py", body, lambda a: a.delete_in_body("A.f", "        x = 1"), no_x),
        ("a line and its break", "k.py", body, lambda a: a.delete_in_body("A.f", "x = 1\n"), no_x),
        ("a whole line", "k.py", body, lambda a: a.delete_in_body("A.f", "        x = 1\n"), no_x),
        ("replace_in_body with nothing", "k.py", body, lambda a: a.replace_in_body("A.f", "x = 1", ""), no_x),
        ("several lines", "k.py", body, lambda a: a.delete_in_body("A.f", "if x:\n            return 2"),
         "class A:\n    def f(self):\n        x = 1\n"),
        ("code before it on its line stays", "k.py", "def f():\n    x = 1; y = 2\n",
         lambda a: a.delete_in_body("f", "; y = 2"), "def f():\n    x = 1\n"),
        ("code after it on its line stays", "k.py", "def f():\n    x = 1; y = 2\n",
         lambda a: a.delete_in_body("f", "x = 1; "), "def f():\n    y = 2\n"),
        ("a comment after it stays", "k.py", "def f():\n    x = 1  # c\n    y = 2\n",
         lambda a: a.delete_in_body("f", "x = 1"), "def f():\n    # c\n    y = 2\n"),
        ("js", "k.js", "function f() {\n  a();\n  b();\n}\n", lambda a: a.delete_in_body("f", "a();"),
         "function f() {\n  b();\n}\n"),
        ("go, the only statement", "k.go", "package main\n\nfunc f() {\n\tx()\n}\n",
         lambda a: a.delete_in_body("f", "x()"), "package main\n\nfunc f() {\n}\n"),
        ("ruby, the body's last line and its break", "k.rb", "def f\n  x = 1\n  x\nend\n",
         lambda a: a.delete_in_body("f", "  x\n"), "def f\n  x = 1\nend\n"),
        ("python, the body's last line and its break", "k.py", "def f():\n    x = 1\n    return x\n\n\ndef g():\n    pass\n",
         lambda a: a.delete_in_body("f", "    return x\n"), "def f():\n    x = 1\n\n\ndef g():\n    pass\n"),
        ("the last line of a file without a final line break", "k.py", "def f():\n    x = 1\n    y = 2",
         lambda a: a.delete_in_body("f", "y = 2"), "def f():\n    x = 1"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"whole-line deletion ({label})", _edit_result(name, source, action), expected)
    _exact("whole-line deletion (CRLF)", _edit_result("k.py", body, lambda a: a.delete_in_body("A.f", "x = 1"), "\r\n"),
           no_x.replace("\n", "\r\n"))
    empty = "would leave the body of 'f' without a statement, which Python does not allow"
    for label, source, action in [
        ("the only statement", "def f():\n    x = 1\n", lambda a: a.delete_in_body("f", "x = 1")),
        ("all but a comment", "def f():\n    # note\n    x = 1\n", lambda a: a.delete_in_body("f", "x = 1")),
        ("replace_in_body with nothing", "def f():\n    x = 1\n", lambda a: a.replace_in_body("f", "x = 1", "")),
    ]:
        _refused(f"whole-line deletion ({label})", _edit_result("k.py", source, action), empty)

    # Without an exact match, a snippet or anchor matches whole lines of the
    # body with one indentation added to or removed from each of its lines,
    # and new_snippet moves the same way, keeping its relative indentation,
    # unless it is at the file's indentation there already.
    three = body.replace("return 2", "return 3")
    go = "package main\n\nfunc f(x int) int {\n\tif x > 0 {\n\t\treturn 1\n\t}\n\treturn 0\n}\n"
    js = "function f(x) {\n  if (x) {\n    return 1;\n  }\n  return 0;\n}\n"
    rb = "class A\n  def f(x)\n    if x\n      1\n    end\n  end\nend\n"
    java = "class K {\n    int f(int x) {\n        if (x > 0) {\n            return 1;\n        }\n        return 0;\n    }\n}\n"
    cpp = "int f(int x) {\n    if (x > 0) {\n        return 1;\n    }\n    return 0;\n}\n"
    sloppy = "function f() {\n  if (a) {\n    b();\n  }\n  if (a) {\n  b();\n  }\n}\n"
    cases = [
        ("4 columns short (reported)", "k.py", body,
         lambda a: a.replace_in_body("A.f", "    if x:\n        return 2", "    if x:\n        return 3"), three),
        ("at column 0 (reported)", "k.py", body,
         lambda a: a.replace_in_body("A.f", "if x:\n    return 2", "if x:\n    return 3"), three),
        ("indented too deep", "k.py", body, lambda a: a.replace_in_body("A.f", "            x = 1", "            x = 5"),
         body.replace("x = 1", "x = 5")),
        ("new lines keep their relative indentation", "k.py", body,
         lambda a: a.replace_in_body("A.f", "if x:\n    return 2", "if x:\n    if x > 1:\n        return 3\n    return 2"),
         body.replace("            return 2", "            if x > 1:\n                return 3\n            return 2")),
        ("new content at the file's indentation goes in as written", "k.py", body,
         lambda a: a.replace_in_body("A.f", "if x:\n    return 2", "        if x:\n            return 3"), three),
        ("a multi-line string keeps its text", "k.py", body,
         lambda a: a.replace_in_body("A.f", "if x:\n    return 2", 'if x:\n    return """a\nb"""'),
         body.replace("return 2", 'return """a\nb"""')),
        ("delete_in_body", "k.py", body, lambda a: a.delete_in_body("A.f", "if x:\n    return 2\n"),
         "class A:\n    def f(self):\n        x = 1\n"),
        ("blank lines match blank lines", "k.py", "def f():\n    x = 1\n\n    y = 2\n",
         lambda a: a.replace_in_body("f", "x = 1\n\ny = 2", "x = 1\ny = 2"), "def f():\n    x = 1\n    y = 2\n"),
        ("spaces at the end of a line aside", "k.py", "def f():\n    x = 1   \n    y = 2\n",
         lambda a: a.replace_in_body("f", "x = 1\ny = 2", "z = 3"), "def f():\n    z = 3\n"),
        ("go, tabs", "k.go", go, lambda a: a.replace_in_body("f", "if x > 0 {\n\treturn 1\n}", "if x > 1 {\n\treturn 2\n}"),
         go.replace("x > 0", "x > 1").replace("return 1", "return 2")),
        ("js", "k.js", js, lambda a: a.replace_in_body("f", "if (x) {\n  return 1;\n}", "if (x) {\n  return 2;\n}"),
         js.replace("return 1", "return 2")),
        ("ruby", "k.rb", rb, lambda a: a.replace_in_body("A.f", "if x\n  1\nend", "if x\n  2\nend"), rb.replace("1", "2")),
        ("ruby, an embedded document stays at column 0", "k.rb", rb,
         lambda a: a.replace_in_body("A.f", "if x\n  1\nend", "=begin\nx\n=end\nif x\n  2\nend"),
         "class A\n  def f(x)\n=begin\nx\n=end\n    if x\n      2\n    end\n  end\nend\n"),
        ("java, delete_in_body", "K.java", java, lambda a: a.delete_in_body("K.f", "if (x > 0) {\n    return 1;\n}\n"),
         "class K {\n    int f(int x) {\n        return 0;\n    }\n}\n"),
        ("cpp, insert_in_body after", "k.cpp", cpp, lambda a: a.insert_in_body("f", "x++;", after="if (x > 0) {\n    return 1;\n}"),
         cpp.replace("    }\n", "    }\n    x++;\n")),
        ("an exact match wins", "k.js", sloppy, lambda a: a.replace_in_body("f", "if (a) {\n  b();", "if (a) {\n  c();"),
         sloppy.replace("  if (a) {\n  b();", "  if (a) {\n  c();")),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"shifted indentation ({label})", _edit_result(name, source, action), expected)
    _exact("shifted indentation (js, a CRLF file)",
           _edit_result("k.js", js, lambda a: a.replace_in_body("f", "if (x) {\r\n  return 1;\r\n}", "if (x) {\r\n  return 2;\r\n}"), "\r\n"),
           js.replace("return 1", "return 2").replace("\n", "\r\n"))
    refusals = [
        ("ambiguous", "k.py", "def f(x):\n    if x:\n        y = 1\n    if x:\n        y = 1\n",
         lambda a: a.replace_in_body("f", "if x:\n    y = 1", "z = 1"),
         "Snippet matches 2 places in body of 'f' with its indentation shifted (lines 2, 4). Include more"),
        ("not one shift", "k.py", body, lambda a: a.replace_in_body("A.f", "if x:\n   return 2", "pass"),
         "Snippet not found in body of 'A.f'. Check whitespace and indentation: "),
        ("tabs and spaces differ", "k.go", go, lambda a: a.replace_in_body("f", "if x > 0 {\n    return 1\n}", "x"),
         "(tabs and spaces differ)"),
        ("an anchor", "k.py", body, lambda a: a.insert_in_body("A.f", "y = 2", after="if x:\n   return 2"),
         "Anchor snippet not found in body of 'A.f'. Check whitespace and indentation: "),
    ]
    for label, name, source, action, reason in refusals:
        _refused(f"shifted indentation ({label})", _edit_result(name, source, action), reason)

    # An anchor that starts its line (before) or ends it (after, also before
    # a comment) has new_snippet go on lines of its own, indented as the
    # anchor is; one in the middle of a line has it placed byte for byte.
    with_y = body.replace("        x = 1\n", "        x = 1\n        y = 2\n")
    validate = "def f(x):\n    validate(x)\n"
    cases = [
        ("after a line at column 0 (reported)", "k.py", body, lambda a: a.insert_in_body("A.f", "y = 2", after="x = 1"), with_y),
        ("before a line at column 0", "k.py", body, lambda a: a.insert_in_body("A.f", "y = 2", before="x = 1"),
         body.replace("        x = 1\n", "        y = 2\n        x = 1\n")),
        ("content at the file's indentation", "k.py", body,
         lambda a: a.insert_in_body("A.f", "        y = 2\n", after="x = 1"), with_y),
        ("the anchor's line break given", "k.py", body, lambda a: a.insert_in_body("A.f", "y = 2\n", after="x = 1\n"), with_y),
        ("a leading line break", "k.py", body, lambda a: a.insert_in_body("A.f", "\n        y = 2", after="x = 1"), with_y),
        ("a blank line", "k.py", body, lambda a: a.insert_in_body("A.f", "\n\ny = 2", after="x = 1"),
         body.replace("        x = 1\n", "        x = 1\n\n        y = 2\n")),
        ("before, with the anchor's indentation after it", "k.py", validate,
         lambda a: a.insert_in_body("f", "auth(x)\n    ", before="validate(x)"), "def f(x):\n    auth(x)\n    validate(x)\n"),
        ("after a block at column 0", "k.py", body, lambda a: a.insert_in_body("A.f", "y = 3", after="if x:\n    return 2"),
         body + "        y = 3\n"),
        ("after a line that ends with a comment", "k.py", "def f():\n    x = 1  # c\n",
         lambda a: a.insert_in_body("f", "y = 2", after="x = 1"), "def f():\n    x = 1  # c\n    y = 2\n"),
        ("after the last line of a file without a final line break", "k.py", "def f():\n    x = 1",
         lambda a: a.insert_in_body("f", "y = 2", after="x = 1"), "def f():\n    x = 1\n    y = 2"),
        ("ruby, an embedded document stays at column 0", "k.rb", "class A\n  def f\n    1\n  end\nend\n",
         lambda a: a.insert_in_body("A.f", "=begin\nx\n=end\n2", after="1"),
         "class A\n  def f\n    1\n=begin\nx\n=end\n    2\n  end\nend\n"),
        ("go, tabs", "k.go", go, lambda a: a.insert_in_body("f", "x--", before="return 0"),
         go.replace("\treturn 0\n", "\tx--\n\treturn 0\n")),
        ("before the closing brace", "k.js", "function f() {\n  a();\n}\n",
         lambda a: a.insert_in_body("f", "  b();", before="}"), "function f() {\n  a();\n  b();\n}\n"),
        ("after a body on its signature's line, byte for byte", "k.py", "def f(): return 1\n",
         lambda a: a.insert_in_body("f", "; y = 2", after="return 1"), "def f(): return 1; y = 2\n"),
        ("java, a text block moves with the code", "K.java",
         'class K {\n    String f() {\n        String s = "x";\n        return s;\n    }\n}\n',
         lambda a: a.insert_in_body("K.f", 'String t = """\n    yo\n    """;', before="return s;"),
         'class K {\n    String f() {\n        String s = "x";\n        String t = """\n            yo\n'
         '            """;\n        return s;\n    }\n}\n'),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"anchored lines ({label})", _edit_result(name, source, action), expected)
    _exact("anchored lines (CRLF)", _edit_result("k.py", body, lambda a: a.insert_in_body("A.f", "y = 2", after="x = 1"), "\r\n"),
           with_y.replace("\n", "\r\n"))
    # Code after the closing brace of the body would be outside it.
    _refused("anchored lines (after the closing brace)",
             _edit_result("k.js", "function f() {\n  a();\n}\n", lambda a: a.insert_in_body("f", "b();", after="a();\n}")),
             "The anchor ends with the closing brace of 'f', so code after it would be outside the body.")

    # An exact one-line snippet written without (all of) its indentation
    # gives the later lines of new_snippet that indentation too, unless they
    # are at the file's indentation already.
    cases = [
        ("relative lines", body, lambda a: a.replace_in_body("A.f", "x = 1", "x = 1\nif x > 1:\n    x = 0"),
         body.replace("        x = 1\n", "        x = 1\n        if x > 1:\n            x = 0\n")),
        ("lines at the file's indentation", body, lambda a: a.replace_in_body("A.f", "x = 1", "x = 1\n        y = 2"), with_y),
        ("a snippet in the middle of a line", "def f():\n    x = g(a)\n",
         lambda a: a.replace_in_body("f", "g(a)", "g(\n    a,\n)"), "def f():\n    x = g(\n        a,\n    )\n"),
    ]
    for label, source, action, expected in cases:
        _exact(f"one-line snippets ({label})", _edit_result("k.py", source, action), expected)


# ──────────────────────────────────────────────
# Content layout: several members in read_symbol's shape, tabs, mixed line
# endings, stacked siblings
# ──────────────────────────────────────────────


def test_content_layout():
    print("\n═══ content layout: several members, tabs, mixed line endings, stacked siblings ═══")

    # Content in read_symbol's shape (its first line at column 0, the later
    # lines at their file indentation) may hold several members: a line at
    # the symbol's own indentation that starts another member after the one
    # before it ended counts as one of the symbol's own lines.
    cls = "class A:\n    def f(self):\n        return 1\n\n    def z(self):\n        return 9\n"
    two = "class A:\n    def f(self):\n        return 1\n\n    def g(self):\n        return 2\n\n    def z(self):\n        return 9\n"
    js = "class A {\n  f() {\n    return 1;\n  }\n}\n"
    cases = [
        ("python replace_function (reported)", "k.py", cls,
         lambda a: a.replace_function("A.f", "def f(self):\n        return 1\n\n    def g(self):\n        return 2"), two),
        ("python insert_sibling before (reported)", "k.py", cls,
         lambda a: a.insert_sibling("A.z", "def g(self):\n        return 2\n\n    def h(self):\n        return 3", "before"),
         cls.replace("    def z", "    def g(self):\n        return 2\n\n    def h(self):\n        return 3\n\n    def z")),
        ("python, the second member decorated (reported)", "k.py", cls,
         lambda a: a.replace_function("A.f", "def f(self):\n        return 1\n\n    @property\n    def g(self):\n        return 2"),
         two.replace("    def g", "    @property\n    def g")),
        ("js replace_function (reported)", "k.js", js,
         lambda a: a.replace_function("A.f", "f() {\n    return 1;\n  }\n\n  g() {\n    return 2;\n  }"),
         "class A {\n  f() {\n    return 1;\n  }\n\n  g() {\n    return 2;\n  }\n}\n"),
        ("python add_method", "k.py", cls,
         lambda a: a.add_method("A", "def g(self):\n        return 2\n\n    def h(self):\n        return 3"),
         cls + "\n    def g(self):\n        return 2\n\n    def h(self):\n        return 3\n"),
        ("python fields", "k.py", "class C:\n    kind: str\n",
         lambda a: a.replace_function("C.kind", 'kind: str\n    label: str = ""'), 'class C:\n    kind: str\n    label: str = ""\n'),
        ("java, the second member annotated", "K.java", "class K {\n    void f() {\n    }\n}\n",
         lambda a: a.replace_function("K.f", 'void f() {\n    }\n\n    @Override\n    public String toString() {\n        return "K";\n    }'),
         'class K {\n    void f() {\n    }\n\n    @Override\n    public String toString() {\n        return "K";\n    }\n}\n'),
        ("ruby", "k.rb", "class A\n  def f\n    1\n  end\nend\n",
         lambda a: a.replace_function("A.f", "def f\n    1\n  end\n\n  def g\n    2\n  end"),
         "class A\n  def f\n    1\n  end\n\n  def g\n    2\n  end\nend\n"),
        ("cpp fields", "k.cpp", "struct S {\n    int a;\n};\n",
         lambda a: a.replace_function("S.a", "int a;\n    int b;"), "struct S {\n    int a;\n    int b;\n};\n"),
        ("go, a var group", "k.go", "package main\n\nvar (\n\ta = 1\n\tb = 2\n)\n",
         lambda a: a.replace_function("a", "a = 1\n\tc = 3"), "package main\n\nvar (\n\ta = 1\n\tc = 3\n\tb = 2\n)\n"),
        ("python, read at another depth", "k.py", cls,
         lambda a: a.replace_function("A.f", "def f(self):\n            return 1\n\n        def g(self):\n            return 2"), two),
        # Relative and absolute content is re-indented as before.
        ("python relative, a nested def", "k.py", cls,
         lambda a: a.replace_function("A.f", "def f(self):\n    def g():\n        return 1\n    return g"),
         cls.replace("        return 1\n", "        def g():\n            return 1\n        return g\n")),
        ("python relative, a class of methods", "k.py", cls,
         lambda a: a.insert_sibling("A.z", "class B:\n    def m(self):\n        pass\n\n    def n(self):\n        pass", "before"),
         cls.replace("    def z", "    class B:\n        def m(self):\n            pass\n\n        def n(self):\n            pass\n\n    def z")),
        ("python relative, two methods", "k.py", cls,
         lambda a: a.replace_function("A.f", "def f(self):\n    return 1\n\ndef g(self):\n    return 2"), two),
        ("python absolute, two methods", "k.py", cls,
         lambda a: a.replace_function("A.f", "    def f(self):\n        return 1\n\n    def g(self):\n        return 2"), two),
        ("python relative, a call continued at the member level", "k.py", "class A:\n    x = 1\n",
         lambda a: a.replace_function("A.x", "x = f(\n    1,\n    2)"), "class A:\n    x = f(\n        1,\n        2)\n"),
        ("js relative", "k.js", js,
         lambda a: a.replace_function("A.f", "f() {\n  if (a) {\n    b();\n  }\n  return 1;\n}"),
         "class A {\n  f() {\n    if (a) {\n      b();\n    }\n    return 1;\n  }\n}\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"several members ({label})", _edit_result(name, source, action), expected)

    # Content for a file or block indented with tabs gets its indentation
    # steps in tabs, and Go content always does. The text of multi-line
    # strings, a Ruby embedded document, and the spaces that align a block
    # comment or a continued line stay as written.
    go_type = "package main\n\ntype T struct {\n\ta int\n}\n"
    go_f = "package main\n\nfunc f() {\n\tx := 1\n\t_ = x\n}\n"
    go_if = "package main\n\nfunc f(x int) int {\n\tif x > 0 {\n\t\treturn 1\n\t}\n\treturn 0\n}\n"
    tab_cls = "class A:\n\tdef a(self):\n\t\tpass\n"
    cases = [
        ("go add_method (reported)", "k.go", go_type, lambda a: a.add_method("T", "func (t T) f() {\n    return\n}"),
         go_type + "\nfunc (t T) f() {\n\treturn\n}\n"),
        ("go add_method, code right after the type", "k.go", go_type + "func g() {}\n",
         lambda a: a.add_method("T", "func (t T) f() {\n    return\n}"),
         go_type + "\nfunc (t T) f() {\n\treturn\n}\n\nfunc g() {}\n"),
        ("python replace_function (reported)", "k.py", tab_cls, lambda a: a.replace_function("A.a", "def a(self):\n    return 1"),
         "class A:\n\tdef a(self):\n\t\treturn 1\n"),
        ("go insert_in_body at the bottom (reported)", "k.go", go_f,
         lambda a: a.insert_in_body("f", "if x > 0 {\n    x = 2\n}", at="bottom"),
         go_f.replace("\t_ = x\n", "\t_ = x\n\tif x > 0 {\n\t\tx = 2\n\t}\n")),
        ("go insert_in_body at the top", "k.go", go_f,
         lambda a: a.insert_in_body("f", "if true {\n    return\n}", at="top"),
         go_f.replace("{\n\tx := 1", "{\n\tif true {\n\t\treturn\n\t}\n\tx := 1")),
        ("go replace_function_body", "k.go", go_f, lambda a: a.replace_function_body("f", "if true {\n    return\n}"),
         "package main\n\nfunc f() {\n\tif true {\n\t\treturn\n\t}\n}\n"),
        ("go replace_function_body of a one-line body", "k.go", "package main\n\nfunc f() { return }\n",
         lambda a: a.replace_function_body("f", "if true {\n    return\n}"),
         "package main\n\nfunc f() {\n\tif true {\n\t\treturn\n\t}\n}\n"),
        ("go replace_function at the top level", "k.go", go_f,
         lambda a: a.replace_function("f", "func f() {\n    if true {\n        return\n    }\n}"),
         "package main\n\nfunc f() {\n\tif true {\n\t\treturn\n\t}\n}\n"),
        ("go add_top_level", "k.go", "package main\n", lambda a: a.add_top_level("func g() {\n    return\n}"),
         "package main\n\nfunc g() {\n\treturn\n}\n"),
        ("go insert_sibling", "k.go", go_f, lambda a: a.insert_sibling("f", "func g() {\n    return\n}", "after"),
         go_f + "\nfunc g() {\n\treturn\n}\n"),
        ("go replace_in_body", "k.go", go_if,
         lambda a: a.replace_in_body("f", "return 0", "if x < 0 {\n    return -1\n}\nreturn 0"),
         go_if.replace("\treturn 0\n", "\tif x < 0 {\n\t\treturn -1\n\t}\n\treturn 0\n")),
        ("go insert_in_body before an anchor", "k.go", go_if,
         lambda a: a.insert_in_body("f", "if x > 5 {\n    return 5\n}", before="return 0"),
         go_if.replace("\treturn 0\n", "\tif x > 5 {\n\t\treturn 5\n\t}\n\treturn 0\n")),
        ("python, a tab file's top level", "k.py", "def a():\n\tpass\n\n\ndef b():\n\tpass\n",
         lambda a: a.replace_function("b", "def b():\n    if x:\n        return 1"),
         "def a():\n\tpass\n\n\ndef b():\n\tif x:\n\t\treturn 1\n"),
        ("python, a multi-line string keeps its text", "k.py", tab_cls,
         lambda a: a.replace_function("A.a", 'def a(self):\n    s = """x\n    y"""\n    return s'),
         'class A:\n\tdef a(self):\n\t\ts = """x\n    y"""\n\t\treturn s\n'),
        ("python, a docstring moves with the code", "k.py", tab_cls,
         lambda a: a.replace_function("A.a", 'def a(self):\n    """Doc.\n\n    More.\n    """\n    return 1'),
         'class A:\n\tdef a(self):\n\t\t"""Doc.\n\n\t\tMore.\n\t\t"""\n\t\treturn 1\n'),
        ("python, a continued line aligned with spaces", "k.py", tab_cls,
         lambda a: a.replace_function("A.a", "def a(self, x,\n      y):\n    return x"),
         "class A:\n\tdef a(self, x,\n\t      y):\n\t\treturn x\n"),
        ("ruby, an embedded document stays at column 0", "k.rb", "class A\n\tdef f\n\t\t1\n\tend\nend\n",
         lambda a: a.replace_function("A.f", "def f\n=begin\nx\n=end\n  2\nend"),
         "class A\n\tdef f\n=begin\nx\n=end\n\t\t2\n\tend\nend\n"),
        ("go, a block comment keeps its alignment", "k.go", "package main\n",
         lambda a: a.add_top_level("func g() {\n    /*\n     * x\n     */\n    return\n}"),
         "package main\n\nfunc g() {\n\t/*\n\t * x\n\t */\n\treturn\n}\n"),
        ("java, a javadoc in a tab class", "K.java", "class K {\n\tint a;\n}\n",
         lambda a: a.add_method("K", "/**\n * Doc.\n */\nvoid f() {\n    g();\n}"),
         "class K {\n\tint a;\n\n\t/**\n\t * Doc.\n\t */\n\tvoid f() {\n\t\tg();\n\t}\n}\n"),
        ("content in tabs goes in as written", "k.go", go_f,
         lambda a: a.insert_in_body("f", "if x > 0 {\n\tx = 2\n}", at="bottom"),
         go_f.replace("\t_ = x\n", "\t_ = x\n\tif x > 0 {\n\t\tx = 2\n\t}\n")),
        ("a file indented with spaces keeps them", "k.py", cls,
         lambda a: a.replace_function("A.z", "def z(self):\n  if x:\n    return 9"),
         cls.replace("        return 9\n", "      if x:\n        return 9\n")),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"tabs ({label})", _edit_result(name, source, action), expected)
    # read_symbol's text given back leaves a tab file as it was, also
    # where spaces align a continued line.
    for label, name, source, target in [
        ("go", "k.go", go_if, "f"),
        ("python", "k.py", tab_cls, "A.a"),
        ("c, a prototype continued with spaces", "k.c", "int f(int a,\n      int b);\n\nint g(void)\n{\n\treturn 0;\n}\n", "f"),
        ("c, a function continued with spaces", "k.c", "int f(int a,\n      int b)\n{\n\treturn a;\n}\n", "f"),
    ]:
        _exact(f"tabs round trip ({label})", _round_trip(name, source, target), "<unchanged>")

    # A file that mixes CRLF and LF line breaks keeps them on the lines an
    # edit leaves alone. The lines it writes take the break of the lines
    # they replace, else of the lines around them, else the file's most
    # common one.
    mixed = "/*!\n x\n*/\nfunction f() {\r\n}\r\nfunction g() {\r\n}\r\n"
    lf_f = "def f():\n    x = 1\n    y = 2\n\r\n\r\ndef g():\r\n    a = 1\r\n    b = 2\r\n    pass\r\n"
    cases = [
        ("replace_function (reported)", "k.js", mixed, lambda a: a.replace_function("g", "function g() {\n  return 1;\n}"),
         "/*!\n x\n*/\nfunction f() {\r\n}\r\nfunction g() {\r\n  return 1;\r\n}\r\n"),
        ("a changed line keeps its break", "k.py", "a = 1\nb = 2\r\nc = 3\r\n", lambda a: a.replace_value("a", "5"),
         "a = 5\nb = 2\r\nc = 3\r\n"),
        ("new lines between lines with LF", "k.py", lf_f, lambda a: a.insert_in_body("f", "z = 3", after="x = 1"),
         lf_f.replace("    x = 1\n", "    x = 1\n    z = 3\n")),
        ("lines around that differ, the most common", "k.py", lf_f, lambda a: a.insert_in_body("f", "z = 3", at="bottom"),
         lf_f.replace("    y = 2\n", "    y = 2\n    z = 3\r\n")),
        ("delete_symbol", "k.js", mixed, lambda a: a.delete_symbol("f", include_leading_comments=False),
         "/*!\n x\n*/\nfunction g() {\r\n}\r\n"),
        ("a file without a final line break", "k.py", "a = 1\r\nb = 2\r\nc = 3\nd = 4",
         lambda a: a.replace_value("b", "5"), "a = 1\r\nb = 5\r\nc = 3\nd = 4"),
        ("the end of the file", "k.py", "a = 1\r\nb = 2\r\nc = 3\n", lambda a: a.add_top_level("d = 4"),
         "a = 1\r\nb = 2\r\nc = 3\nd = 4\n"),
        ("a byte order mark", "k.py", "\ufeffa = 1\r\nb = 2\n", lambda a: a.replace_value("a", "3"), "\ufeffa = 3\r\nb = 2\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"mixed line endings ({label})", _edit_result(name, source, action), expected)

    # New code gets the gap that separates the target from its neighbour on
    # that side, or, when there is none, at most the usual one from its
    # other side; code over several lines, a Python def or class, keeps at
    # least the usual blank line (two around a top-level Python def/class).
    cell = 'from dataclasses import dataclass\n\n\n@dataclass\nclass Cell:\n    kind: str\n    label: str = ""\n    source: str = ""\n'
    protos = "int f(void);\nint g(void);\n"
    stacked = "int f(void);\nint h(void);\nint g(void);\n"
    fields = "class A {\n  a = 1;\n  b = 2;\n}\n"
    cases = [
        ("after a stacked field (reported)", "k.py", cell,
         lambda a: a.insert_sibling("Cell.label", 'fence: str = "```"', "after"),
         cell.replace("    source", '    fence: str = "```"\n    source')),
        ("after a stacked prototype (reported)", "k.c", protos, lambda a: a.insert_sibling("f", "int h(void);", "after"), stacked),
        ("before a stacked prototype", "k.c", protos, lambda a: a.insert_sibling("g", "int h(void);", "before"), stacked),
        ("after the last stacked field", "k.py", cell, lambda a: a.insert_sibling("Cell.source", "fence: str", "after"),
         cell + "    fence: str\n"),
        ("before the first stacked field", "k.py", cell, lambda a: a.insert_sibling("Cell.kind", "x: int", "before"),
         cell.replace("    kind", "    x: int\n    kind")),
        ("a commented prototype", "k.c", protos, lambda a: a.insert_sibling("f", "// h\nint h(void);", "after"),
         "int f(void);\n// h\nint h(void);\nint g(void);\n"),
        ("a wider gap", "k.c", "int f(void);\n\n\nint g(void);\n", lambda a: a.insert_sibling("f", "int h(void);", "after"),
         "int f(void);\n\n\nint h(void);\n\n\nint g(void);\n"),
        ("stacked with the target, apart from the code above", "k.c", "int a;\n\nint b;\nint c;\n",
         lambda a: a.insert_sibling("b", "int n;", "before"), "int a;\n\nint n;\nint b;\nint c;\n"),
        ("below imports, above stacked constants", "k.py", "import os\n\n\nX = 1\nY = 2\n",
         lambda a: a.insert_sibling("X", "W = 0", "before"), "import os\n\n\nW = 0\nX = 1\nY = 2\n"),
        ("a constant after a def", "k.py", "def f():\n    pass\n\n\nX = 1\n", lambda a: a.insert_sibling("f", "W = 0", "after"),
         "def f():\n    pass\n\n\nW = 0\n\nX = 1\n"),
        ("a function between prototypes", "k.c", protos,
         lambda a: a.insert_sibling("f", "int h(void) {\n    return 0;\n}", "after"),
         "int f(void);\n\nint h(void) {\n    return 0;\n}\n\nint g(void);\n"),
        ("a constant after stacked constants, before a def", "k.py", "X = 1\nY = 2\n\n\ndef f():\n    pass\n",
         lambda a: a.insert_sibling("Y", "Z = 3", "after"), "X = 1\nY = 2\nZ = 3\n\n\ndef f():\n    pass\n"),
        ("a field before a method", "k.py", "class C:\n    a: int\n    b: int\n\n    def m(self):\n        pass\n",
         lambda a: a.insert_sibling("C.b", "c: int", "after"),
         "class C:\n    a: int\n    b: int\n    c: int\n\n    def m(self):\n        pass\n"),
        ("a method between stacked fields", "k.py", "class C:\n    a: int\n    b: int\n",
         lambda a: a.insert_sibling("C.a", "def m(self):\n    pass", "after"),
         "class C:\n    a: int\n\n    def m(self):\n        pass\n\n    b: int\n"),
        ("a lone field", "k.py", "class C:\n    a: int\n", lambda a: a.insert_sibling("C.a", "b: int", "after"),
         "class C:\n    a: int\n\n    b: int\n"),
        ("functions keep their blank line", "k.js", "function a() {\n}\n\nfunction b() {\n}\n",
         lambda a: a.insert_sibling("a", "const x = 1;", "after"), "function a() {\n}\n\nconst x = 1;\n\nfunction b() {\n}\n"),
        # add_top_level and add_method put data after stacked data the same way.
        ("add_top_level after stacked prototypes", "k.c", protos, lambda a: a.add_top_level("int h(void);"),
         protos + "int h(void);\n"),
        ("add_top_level after a function", "k.c", "int f(void) {\n    return 0;\n}\n", lambda a: a.add_top_level("int h(void);"),
         "int f(void) {\n    return 0;\n}\n\nint h(void);\n"),
        ("add_top_level in an include guard", "k.h", "#ifndef K_H\n#define K_H\n\nint f(void);\nint g(void);\n\n#endif\n",
         lambda a: a.add_top_level("int h(void);"), "#ifndef K_H\n#define K_H\n\nint f(void);\nint g(void);\nint h(void);\n\n#endif\n"),
        ("add_method, a python field", "k.py", "class C:\n    a: int\n    b: int\n", lambda a: a.add_method("C", "c: int"),
         "class C:\n    a: int\n    b: int\n    c: int\n"),
        ("add_method, a js field", "k.js", fields, lambda a: a.add_method("A", "c = 3;"), fields.replace("  b = 2;\n", "  b = 2;\n  c = 3;\n")),
        ("add_method, a method after fields", "k.js", fields, lambda a: a.add_method("A", "m() {\n  return 1;\n}"),
         fields.replace("  b = 2;\n", "  b = 2;\n\n  m() {\n    return 1;\n  }\n")),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"stacked siblings ({label})", _edit_result(name, source, action), expected)


# ──────────────────────────────────────────────
# Import lists by line, module docstrings, C void lists, Python parameter
# markers, comments before a symbol, one-line and empty bodies
# ──────────────────────────────────────────────


def test_lists_docstrings_bodies():
    print("\n═══ import lists, module docstrings, (void), parameter markers, comments on a symbol's line, bodies ═══")

    # add_import_name follows the layout of the name list, as add_key and
    # append_to_array do: names one per line get a new line at their
    # indentation, with the list's trailing-comma style, and an inline list
    # stays inline. remove_import_name takes a name on a line of its own
    # with that line, the comment at its end included.
    # (label, file name, source, edit, expected file text)
    one = 'import {\n  a,\n  b,\n} from "m";\n'
    commented = "from m import (\n    a,  # A\n    b,  # B\n)\n"
    cases = [
        ("py add_import_name, one name per line (reported)", "m.py", "from .parser import (\n    _A,\n    _B,\n)\n\nx = 1\n",
         lambda a: a.add_import_name(".parser", "_C"), "from .parser import (\n    _A,\n    _B,\n    _C,\n)\n\nx = 1\n"),
        ("py add_import_name without a trailing comma", "m.py", "from m import (\n    a,\n    b\n)\n",
         lambda a: a.add_import_name("m", "c"), "from m import (\n    a,\n    b,\n    c\n)\n"),
        ("py add_import_name after a comment on the last line", "m.py", commented,
         lambda a: a.add_import_name("m", "c"), "from m import (\n    a,  # A\n    b,  # B\n    c,\n)\n"),
        ("py add_import_name to one name on its own line", "m.py", "from m import (\n    a,\n)\n",
         lambda a: a.add_import_name("m", "c"), "from m import (\n    a,\n    c,\n)\n"),
        ("py add_import_name with an alias", "m.py", "from m import (\n    a as x,\n    b,\n)\n",
         lambda a: a.add_import_name("m", "c as d"), "from m import (\n    a as x,\n    b,\n    c as d,\n)\n"),
        ("py add_import_name above a comment line before the )", "m.py", "from m import (\n    a,\n    b,\n    # c later\n)\n",
         lambda a: a.add_import_name("m", "c"), "from m import (\n    a,\n    b,\n    c,\n    # c later\n)\n"),
        ("py add_import_name to names aligned under the (", "m.py", "from m import (a,\n               b)\n",
         lambda a: a.add_import_name("m", "c"), "from m import (a,\n               b,\n               c)\n"),
        ("py add_import_name inline in parentheses", "m.py", "from m import (a, b)\n",
         lambda a: a.add_import_name("m", "c"), "from m import (a, b, c)\n"),
        ("py add_import_name inline", "m.py", "from m import a, b\n",
         lambda a: a.add_import_name("m", "c"), "from m import a, b, c\n"),
        ("py add_import_name after a backslash continuation", "m.py", "from m import a, \\\n    b\n",
         lambda a: a.add_import_name("m", "c"), "from m import a, \\\n    b, c\n"),
        ("js add_import_name, one name per line (reported)", "m.js", one,
         lambda a: a.add_import_name("m", "c"), 'import {\n  a,\n  b,\n  c,\n} from "m";\n'),
        ("js add_import_name without a trailing comma", "m.js", 'import {\n  a,\n  b\n} from "m";\n',
         lambda a: a.add_import_name("m", "c"), 'import {\n  a,\n  b,\n  c\n} from "m";\n'),
        ("js add_import_name with a default import", "m.js", 'import D, {\n  a,\n  b,\n} from "m";\n',
         lambda a: a.add_import_name("m", "c"), 'import D, {\n  a,\n  b,\n  c,\n} from "m";\n'),
        ("js add_import_name inline", "m.js", 'import { a, b } from "m";\n',
         lambda a: a.add_import_name("m", "c"), 'import { a, b, c } from "m";\n'),
        ("js add_import_name inline with a trailing comma", "m.js", 'import { a, b, } from "m";\n',
         lambda a: a.add_import_name("m", "c"), 'import { a, b, c, } from "m";\n'),
        ("ts add_import_name to a type import", "m.ts", 'import type {\n  A,\n  B,\n} from "m";\n',
         lambda a: a.add_import_name("m", "C"), 'import type {\n  A,\n  B,\n  C,\n} from "m";\n'),
        ("ts add_import_name of a type name", "m.ts", 'import {\n  type A,\n  b,\n} from "m";\n',
         lambda a: a.add_import_name("m", "type C"), 'import {\n  type A,\n  type C,\n  b,\n} from "m";\n'),
        ("py remove_import_name of the last name with its comment", "m.py", commented,
         lambda a: a.remove_import_name("m", "b"), "from m import (\n    a,  # A\n)\n"),
        ("py remove_import_name of a middle name with its comment", "m.py", "from m import (\n    a,  # A\n    b,  # B\n    c,\n)\n",
         lambda a: a.remove_import_name("m", "b"), "from m import (\n    a,  # A\n    c,\n)\n"),
        ("py remove_import_name of the first name", "m.py", commented,
         lambda a: a.remove_import_name("m", "a"), "from m import (\n    b,  # B\n)\n"),
        ("py remove_import_name without a trailing comma", "m.py", "from m import (\n    a,\n    b\n)\n",
         lambda a: a.remove_import_name("m", "b"), "from m import (\n    a\n)\n"),
        ("py remove_import_name inline in parentheses", "m.py", "from m import (a, b, c)\n",
         lambda a: a.remove_import_name("m", "b"), "from m import (a, c)\n"),
        ("py remove_import_name inline", "m.py", "from m import a, b, c\n",
         lambda a: a.remove_import_name("m", "c"), "from m import a, b\n"),
        ("js remove_import_name of the last name with its comment", "m.js", 'import {\n  a, // A\n  b, // B\n} from "m";\n',
         lambda a: a.remove_import_name("m", "b"), 'import {\n  a, // A\n} from "m";\n'),
        ("js remove_import_name of a middle name", "m.js", 'import {\n  a, // A\n  b, // B\n  c,\n} from "m";\n',
         lambda a: a.remove_import_name("m", "b"), 'import {\n  a, // A\n  c,\n} from "m";\n'),
        ("ts remove_import_name from a type import", "m.ts", 'import type {\n  A,\n  B,\n} from "m";\n',
         lambda a: a.remove_import_name("m", "B"), 'import type {\n  A,\n} from "m";\n'),
        ("ts remove_import_name of a type name inline", "m.ts", 'import { type A, b } from "m";\n',
         lambda a: a.remove_import_name("m", "A"), 'import { b } from "m";\n'),
    ]
    for label, name, source, action, expected in cases:
        _exact(label, _edit_result(name, source, action), expected)
    _exact("js add_import_name, one name per line (CRLF)",
           _edit_result("m.js", one, lambda a: a.add_import_name("m", "c"), "\r\n"),
           'import {\r\n  a,\r\n  b,\r\n  c,\r\n} from "m";\r\n')

    # replace_docstring with the target "" edits the module docstring: it
    # replaces the one the module starts with, or inserts one before the
    # first statement, below a `#!` line, an encoding line and a header
    # comment set off by a blank line (a comment right above the first
    # statement stays with it), followed by one blank line, two before a
    # def or class.
    new = '"""New."""'
    cases = [
        ("module docstring replaced", '"""Old."""\n\nimport os\n', new, '"""New."""\n\nimport os\n'),
        ("module docstring replaced below a #! line and a comment", '#!/usr/bin/env python\n# tool\n"""Old."""\nimport os\n',
         new, '#!/usr/bin/env python\n# tool\n"""New."""\nimport os\n'),
        ("module docstring alone replaced", "'''Old.'''\n", new, '"""New."""\n'),
        ("module docstring inserted below #!, above a __future__ import (reported)",
         "#!/usr/bin/env python\nfrom __future__ import annotations\nimport os\n", new,
         '#!/usr/bin/env python\n"""New."""\n\nfrom __future__ import annotations\nimport os\n'),
        ("module docstring inserted below an encoding line", "# -*- coding: utf-8 -*-\nimport os\n", new,
         '# -*- coding: utf-8 -*-\n"""New."""\n\nimport os\n'),
        ("module docstring inserted below a header comment", "# Copyright A\n# License B\n\nimport os\n", new,
         '# Copyright A\n# License B\n\n"""New."""\n\nimport os\n'),
        ("module docstring inserted above the first statement's comment", "# needed for X\nimport os\n", new,
         '"""New."""\n\n# needed for X\nimport os\n'),
        ("module docstring inserted before a def", "def f():\n    pass\n", new, '"""New."""\n\n\ndef f():\n    pass\n'),
        ("module docstring inserted before a decorated class", "@dataclass\nclass A:\n    pass\n", new,
         '"""New."""\n\n\n@dataclass\nclass A:\n    pass\n'),
        ("module docstring inserted after a blank line below #!", "#!/usr/bin/env python\n\nimport os\n", new,
         '#!/usr/bin/env python\n\n"""New."""\n\nimport os\n'),
        ("module docstring inserted below a #! line alone", "#!/usr/bin/env python\n", new,
         '#!/usr/bin/env python\n"""New."""\n'),
        ("module docstring inserted below comments alone", "# notes\n", new, '# notes\n\n"""New."""\n'),
        ("module docstring inserted, a later string is no docstring", 'import os\n"""Notes."""\n', new,
         '"""New."""\n\nimport os\n"""Notes."""\n'),
        ("module docstring of several lines inserted", "import os\n", '"""Summary.\n\nMore.\n"""',
         '"""Summary.\n\nMore.\n"""\n\nimport os\n'),
    ]
    for label, source, docstring, expected in cases:
        _exact(label, _edit_result("d.py", source, lambda a: a.replace_docstring("", docstring)), expected)
    _exact("module docstring inserted (CRLF)",
           _edit_result("d.py", "import os\n", lambda a: a.replace_docstring("", new), "\r\n"),
           '"""New."""\r\n\r\nimport os\r\n')
    for label, docstring in [("text", "New."), ("a name", "New"), ("an f-string", 'f"""New."""')]:
        _refused(f"module docstring that is no string literal ({label})",
                 _edit_result("d.py", "import os\n", lambda a: a.replace_docstring("", docstring)),
                 "new_docstring is not a Python string literal")

    # C: `(void)` is an empty parameter list. add_parameter replaces the
    # `void`, and removing the last parameter of a C function leaves
    # `(void)`, since `()` declares unspecified parameters before C23; C++
    # keeps `()`.
    cases = [
        ("c add_parameter to (void) (reported)", "f.c", "int f(void) { return 0; }\n",
         lambda a: a.add_parameter("f", "int c"), "int f(int c) { return 0; }\n"),
        ("c add_parameter at the start of (void)", "f.c", "int f(void) { return 0; }\n",
         lambda a: a.add_parameter("f", "int c", "start"), "int f(int c) { return 0; }\n"),
        ("c add_parameter to a prototype's (void)", "f.h", "int f(void);\n",
         lambda a: a.add_parameter("f", "int c"), "int f(int c);\n"),
        ("cpp add_parameter to (void)", "f.cpp", "int f(void) {}\n",
         lambda a: a.add_parameter("f", "int c"), "int f(int c) {}\n"),
        ("c add_parameter after a void pointer", "f.c", "int f(void *p) { return 0; }\n",
         lambda a: a.add_parameter("f", "int c"), "int f(void *p, int c) { return 0; }\n"),
        ("c remove_parameter of the last one (reported)", "f.c", "int f(int a) { return 0; }\n",
         lambda a: a.remove_parameter("f", "a"), "int f(void) { return 0; }\n"),
        ("c remove_parameter of a prototype's last one", "f.h", "int f(int a);\n",
         lambda a: a.remove_parameter("f", "a"), "int f(void);\n"),
        ("c remove_parameter of the last one, on its own line", "f.c", "int f(\n    int a\n) { return 0; }\n",
         lambda a: a.remove_parameter("f", "a"), "int f(void) { return 0; }\n"),
        ("c remove_parameter of the last one with the comment after it", "f.c", "int f(int a /* the a */) { return 0; }\n",
         lambda a: a.remove_parameter("f", "a"), "int f(void) { return 0; }\n"),
        ("c remove_parameter of the last one, a comment before it kept", "f.c", "int f(/* x */ int a) { return 0; }\n",
         lambda a: a.remove_parameter("f", "a"), "int f(/* x */ void) { return 0; }\n"),
        ("c remove_parameter of the last one, a comment line kept", "f.c", "int f(\n    // the a\n    int a\n) { return 0; }\n",
         lambda a: a.remove_parameter("f", "a"), "int f(\n    // the a\n    void\n) { return 0; }\n"),
        ("c remove_parameter of one of two", "f.c", "int f(int a, int b) { return b; }\n",
         lambda a: a.remove_parameter("f", "a"), "int f(int b) { return b; }\n"),
        ("cpp remove_parameter of the last one", "f.cpp", "int f(int a) { return 0; }\n",
         lambda a: a.remove_parameter("f", "a"), "int f() { return 0; }\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(label, _edit_result(name, source, action), expected)

    # Python: a bare `*` needs a keyword-only parameter after it and a `/`
    # a parameter before it, so removing the last of them takes the marker
    # too. add_parameter at the end goes before `**kwargs`, which must come
    # last.
    cases = [
        ("remove the only keyword-only parameter (reported)", "def f(a, *, b):\n", "b", "def f(a):\n"),
        ("remove the only positional-only parameter (reported)", "def f(a, /, b):\n", "a", "def f(b):\n"),
        ("remove a keyword-only parameter of two", "def f(a, *, b, c):\n", "b", "def f(a, *, c):\n"),
        ("remove the keyword-only parameter before **kwargs", "def f(a, *, b, **kw):\n", "b", "def f(a, **kw):\n"),
        ("remove the only parameter after *", "def f(*, b):\n", "b", "def f():\n"),
        ("remove the only parameter before /", "def f(a, /):\n", "a", "def f():\n"),
        ("remove a positional-only parameter of two", "def f(a, b, /, c):\n", "a", "def f(b, /, c):\n"),
        ("remove a typed keyword-only parameter", 'def f(a: int, *, b: str = "") -> None:\n', "b",
         "def f(a: int) -> None:\n"),
        ("remove one per line", "def f(\n    a,\n    *,\n    b,\n):\n", "b", "def f(\n    a,\n):\n"),
        ("remove one per line without a trailing comma", "def f(\n    a,\n    *,\n    b\n):\n", "b", "def f(\n    a\n):\n"),
        ("remove one per line before /", "def f(\n    a,\n    /,\n    b,\n):\n", "a", "def f(\n    b,\n):\n"),
    ]
    for label, head, name, expected in cases:
        _exact(f"py {label}", _edit_result("p.py", head + "    pass\n", lambda a: a.remove_parameter("f", name)),
               expected + "    pass\n")
    _exact("py remove the only keyword-only parameter of a method",
           _edit_result("p.py", "class A:\n    def f(self, *, b):\n        pass\n", lambda a: a.remove_parameter("A.f", "b")),
           "class A:\n    def f(self):\n        pass\n")
    cases = [
        ("add before **kwargs", "def f(a, **kw):\n", "b", "end", "def f(a, b, **kw):\n"),
        ("add a keyword-only parameter before **kwargs", "def f(self, *args, **kwargs):\n", "timeout=None", "end",
         "def f(self, *args, timeout=None, **kwargs):\n"),
        ("add before a typed **kwargs", "def f(a, **kw: int):\n", "b", "end", "def f(a, b, **kw: int):\n"),
        ("add before a lone **kwargs", "def f(**kw):\n", "b", "end", "def f(b, **kw):\n"),
        ("add one per line before **kwargs", "def f(\n    a,\n    **kw,\n):\n", "b", "end",
         "def f(\n    a,\n    b,\n    **kw,\n):\n"),
        ("add one per line before **kwargs without a trailing comma", "def f(\n    a,\n    **kw\n):\n", "b", "end",
         "def f(\n    a,\n    b,\n    **kw\n):\n"),
        ("add above the comment over **kwargs", "def f(\n    a,\n    # options\n    **kw,\n):\n", "b", "end",
         "def f(\n    a,\n    b,\n    # options\n    **kw,\n):\n"),
        ("add after a keyword-only parameter", "def f(a, *, b):\n", "c", "end", "def f(a, *, b, c):\n"),
        ("add at the start before /", "def f(a, /, b):\n", "c", "start", "def f(c, a, /, b):\n"),
        ("add **kwargs after *args", "def f(a, *args):\n", "**kw", "end", "def f(a, *args, **kw):\n"),
    ]
    for label, head, parameter, position, expected in cases:
        _exact(f"py {label}",
               _edit_result("p.py", head + "    pass\n", lambda a: a.add_parameter("f", parameter, position)),
               expected + "    pass\n")

    # A comment before a symbol on its first line (`/** @type {X} */ let
    # x;`) is not part of it, and replace_function keeps it there, as it
    # keeps code before the symbol.
    # (label, file name, source, target)
    cases = [
        ("js (reported)", "x.js", "/** @type {X} */ let x;\nlet y;\n", "x"),
        ("ts", "x.ts", "/* a */ function f(): void {}\nlet y = 1;\n", "f"),
        ("ts over several lines", "x.ts", "/* a */ function f(): void {\n  g();\n}\n", "f"),
        ("two comments", "x.js", "/* a */ /* b */ let x;\n", "x"),
        ("c", "x.c", "/* a */ int f(void) { return 0; }\nint g;\n", "f"),
        ("cpp", "x.cpp", "/* a */ int f() { return 0; }\n", "f"),
        ("java", "K.java", "class K {\n    /* a */ int f() { return 0; }\n}\n", "K.f"),
        ("java over several lines", "K.java", "class K {\n    /** a */ int f() {\n        return 0;\n    }\n}\n", "K.f"),
        ("go", "x.go", "package main\n\n/* a */ func f() {}\n", "f"),
    ]
    for label, name, source, target in cases:
        check(f"comment before the symbol on its line, {label}: round trip", _round_trip(name, source, target), "<unchanged>")
    cases = [
        ("js", "x.js", "/** @type {X} */ let x;\nlet y;\n", lambda a: a.replace_function("x", "let x = 1;"),
         "/** @type {X} */ let x = 1;\nlet y;\n"),
        ("js, with a comment after it", "x.js", "/* a */ let x; // x\n", lambda a: a.replace_function("x", "let x = 2;"),
         "/* a */ let x = 2; // x\n"),
        ("ts, content over several lines", "x.ts", "/* a */ function f(): void {}\nlet y = 1;\n",
         lambda a: a.replace_function("f", "function f(): void {\n  g();\n}"),
         "/* a */ function f(): void {\n  g();\n}\nlet y = 1;\n"),
        ("c", "x.c", "/* a */ int f(void) { return 0; }\nint g;\n",
         lambda a: a.replace_function("f", "int f(void) { return 1; }"), "/* a */ int f(void) { return 1; }\nint g;\n"),
        ("java, read_symbol's shape", "K.java", "class K {\n    /* a */ int f() { return 0; }\n}\n",
         lambda a: a.replace_function("K.f", "int f() {\n        return 1;\n    }"),
         "class K {\n    /* a */ int f() {\n        return 1;\n    }\n}\n"),
        ("java, relative content", "K.java", "class K {\n    /* a */ int f() { return 0; }\n}\n",
         lambda a: a.replace_function("K.f", "int f() {\n    return 1;\n}"),
         "class K {\n    /* a */ int f() {\n        return 1;\n    }\n}\n"),
        ("go", "x.go", "package main\n\n/* a */ func f() {}\n",
         lambda a: a.replace_function("f", "func f() {\n\treturn\n}"), "package main\n\n/* a */ func f() {\n\treturn\n}\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"comment before the symbol on its line, {label}: replace_function", _edit_result(name, source, action), expected)

    # A comment after a Python body written on its signature's line stays
    # on that line when replace_function_body puts the body on lines of
    # its own; read_symbol shows it as part of the function.
    one_line = "def b(): pass  # old\n"
    cases = [
        ("replace_function_body (reported)", one_line, lambda a: a.replace_function_body("b", "x()"),
         "def b():  # old\n    x()\n"),
        ("replace_function_body with several lines", one_line, lambda a: a.replace_function_body("b", "x()\ny()"),
         "def b():  # old\n    x()\n    y()\n"),
        ("replace_function_body of a method", "class A:\n    def b(self): pass  # old\n",
         lambda a: a.replace_function_body("A.b", "x()"), "class A:\n    def b(self):  # old\n        x()\n"),
        ("replace_function_body of several statements", "def c(): return 1; x = 2  # c\n",
         lambda a: a.replace_function_body("c", "y()"), "def c():  # c\n    y()\n"),
        ("replace_function_body of a class", "class A: pass  # k\n",
         lambda a: a.replace_function_body("A", "x = 1"), "class A:  # k\n    x = 1\n"),
        ("replace_function_body of a decorated function", "@d\ndef b(): pass  # old\n",
         lambda a: a.replace_function_body("b", "x()"), "@d\ndef b():  # old\n    x()\n"),
        ("replace_function_body, the next def kept", "def b(): pass  # old\ndef c(): pass\n",
         lambda a: a.replace_function_body("b", "x()"), "def b():  # old\n    x()\ndef c(): pass\n"),
        ("replace_function_body without a comment", "def b(): pass\n",
         lambda a: a.replace_function_body("b", "x()"), "def b():\n    x()\n"),
        ("replace_in_body", one_line, lambda a: a.replace_in_body("b", "pass", "x()"), "def b(): x()  # old\n"),
    ]
    for label, source, action, expected in cases:
        _exact(f"py one-line body with a comment: {label}", _edit_result("b.py", source, action), expected)
    _exact("py one-line body with a comment: read_symbol",
           _read_result("b.py", one_line, lambda a: a.read_symbol("b")), "def b(): pass  # old")
    check("py one-line body with a comment: round trip", _round_trip("b.py", one_line, "b"), "<unchanged>")
    _refused("py one-line body with a comment: insert_in_body at the top",
             _edit_result("b.py", one_line, lambda a: a.insert_in_body("b", "x()", at="top")), "shares a line")

    # An empty Ruby method (`def f` over `end`) has no body node; content
    # goes one level deeper than its `def`, between the signature and the
    # `end`, and a method on one line (`def h; end`) is opened up.
    cls = "class A\n  def f\n  end\nend\n"
    filled = "class A\n  def f\n    1\n  end\nend\n"
    cases = [
        ("replace_function_body (reported)", cls, lambda a: a.replace_function_body("A.f", "1"), filled),
        ("insert_in_body at the top", cls, lambda a: a.insert_in_body("A.f", "1", at="top"), filled),
        ("insert_in_body at the bottom", cls, lambda a: a.insert_in_body("A.f", "1", at="bottom"), filled),
        ("with parameters", "def f(a)\nend\n", lambda a: a.replace_function_body("f", "a"), "def f(a)\n  a\nend\n"),
        ("with a signature over two lines", "class A\n  def g\n    1\n  end\n\n  def f(a,\n        b)\n  end\nend\n",
         lambda a: a.replace_function_body("A.f", "a"), "class A\n  def g\n    1\n  end\n\n  def f(a,\n        b)\n    a\n  end\nend\n"),
        ("with a comment on the def line", "class A\n  def g # c\n  end\nend\n",
         lambda a: a.replace_function_body("A.g", "1"), "class A\n  def g # c\n    1\n  end\nend\n"),
        ("with a comment inside", "def f\n  # todo\nend\n", lambda a: a.replace_function_body("f", "1"), "def f\n  1\nend\n"),
        ("insert_in_body at the top, above a comment", "def f\n  # todo\nend\n",
         lambda a: a.insert_in_body("f", "1", at="top"), "def f\n  1\n  # todo\nend\n"),
        ("insert_in_body at the bottom, below a comment", "def f\n  # todo\nend\n",
         lambda a: a.insert_in_body("f", "1", at="bottom"), "def f\n  # todo\n  1\nend\n"),
        ("with a blank line inside", "def f\n\nend\n", lambda a: a.replace_function_body("f", "1"), "def f\n  1\nend\n"),
        ("with content over several lines", "def f\nend\n", lambda a: a.replace_function_body("f", "if x\n  1\nend"),
         "def f\n  if x\n    1\n  end\nend\n"),
        ("on one line", "def h; end\n", lambda a: a.replace_function_body("h", "1"), "def h\n  1\nend\n"),
        ("on one line, in a class", "class A\n  def h; end\nend\n", lambda a: a.replace_function_body("A.h", "1"),
         "class A\n  def h\n    1\n  end\nend\n"),
        ("on one line with parameters", "def h(a); end\n", lambda a: a.replace_function_body("h", "a"),
         "def h(a)\n  a\nend\n"),
        ("a singleton method", "class A\n  def self.f\n  end\nend\n", lambda a: a.replace_function_body("A.f", "1"),
         "class A\n  def self.f\n    1\n  end\nend\n"),
    ]
    for label, source, action, expected in cases:
        _exact(f"rb empty method: {label}", _edit_result("e.rb", source, action), expected)
    _refused("rb empty method on one line: insert_in_body at the top",
             _edit_result("e.rb", "def h; end\n", lambda a: a.insert_in_body("h", "1", at="top")), "shares a line")
    _refused("rb empty method: replace_in_body",
             _edit_result("e.rb", "def f\nend\n", lambda a: a.replace_in_body("f", "1", "2")),
             "The body of 'f' is empty")
    _refused("rb empty method: insert_in_body after an anchor",
             _edit_result("e.rb", "def f\nend\n", lambda a: a.insert_in_body("f", "2", after="1")),
             "The body of 'f' is empty")
    # Empty braced bodies already take content one level deeper.
    cases = [
        ("js insert_in_body at the top", "e.js", "function f() {\n}\n", lambda a: a.insert_in_body("f", "x();", at="top"),
         "function f() {\n  x();\n}\n"),
        ("go insert_in_body at the bottom", "e.go", "package main\n\nfunc f() {\n}\n",
         lambda a: a.insert_in_body("f", "x()", at="bottom"), "package main\n\nfunc f() {\n\tx()\n}\n"),
        ("c replace_function_body", "e.c", "void f(void) {\n}\n", lambda a: a.replace_function_body("f", "x();"),
         "void f(void) {\n  x();\n}\n"),
        ("java insert_in_body at the top", "K.java", "class K {\n    void f() {\n    }\n}\n",
         lambda a: a.insert_in_body("K.f", "x();", at="top"), "class K {\n    void f() {\n        x();\n    }\n}\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"empty body: {label}", _edit_result(name, source, action), expected)


# ──────────────────────────────────────────────
# Review follow-ups: string literals, block openers, read_symbol-shaped
# insertions, sibling and import spacing, mixed line breaks
# ──────────────────────────────────────────────


def test_snippet_layout_followups():
    print("\n═══ follow-ups: snippets and strings, insertion indentation, spacing, line breaks ═══")

    # The text of a multi-line string is never shifted: a snippet matches
    # the lines that start inside one only as they are written in the
    # file, and new lines that go into one, or replace lines of one, keep
    # the text they are given, in tabs files too. A docstring moves with
    # the code, as it does elsewhere.
    query = 'def f():\n    q = """\n    a\n    b\n    """\n    return q\n'
    refusals = [
        ("py string lines shifted (reported)", "k.py", query,
         lambda a: a.replace_in_body("f", 'q = """\na\nb\n"""', 'q = """\na\nc\n"""'), "Snippet not found in body of 'f'"),
        ("js template lines shifted", "k.js", "function f() {\n  if (a) {\n    const t = `\n    line\n    `;\n  }\n}\n",
         lambda a: a.replace_in_body("f", "const t = `\nline\n`;", "const t = `\nline2\n`;"),
         "Snippet not found in body of 'f'"),
        ("go raw string lines shifted", "k.go",
         "package main\n\nfunc f() {\n\tif a {\n\t\ts := `\n\t\tline\n\t\t`\n\t\t_ = s\n\t}\n}\n",
         lambda a: a.replace_in_body("f", "s := `\nline\n`\n_ = s", "s := `\nline2\n`\n_ = s"),
         "Snippet not found in body of 'f'"),
    ]
    for label, name, source, action, reason in refusals:
        _refused(f"string text ({label})", _edit_result(name, source, action), reason)
    tabbed = 'def f():\n\tsql = """\nSELECT a\n    FROM t\n"""\n\treturn sql\n'
    raw = "package main\n\nfunc f() string {\n\treturn `\nline one\n    indented two\n`\n}\n"
    docstring = 'def f():\n    """One.\n\n    Two.\n    """\n    return 1\n'
    cases = [
        ("py string written as in the file", "k.py", query,
         lambda a: a.replace_in_body("f", 'q = """\n    a\n    b\n    """', 'q = """\n    a\n    c\n    """'),
         query.replace("    b\n", "    c\n")),
        ("py code shifted, string as in the file", "k.py", "def f():\n    if x:\n        q = '''\n    a\n'''\n    return 1\n",
         lambda a: a.replace_in_body("f", "if x:\n    q = '''\n    a\n'''", "if x:\n    q = '''\n    b\n'''"),
         "def f():\n    if x:\n        q = '''\n    b\n'''\n    return 1\n"),
        ("go raw string at column 0 (reported)", "a.go", raw,
         lambda a: a.replace_in_body("f", "line one\n    indented two", "line one\n    indented three"),
         raw.replace("two", "three")),
        ("py tab file, string at column 0 (reported)", "a.py", tabbed,
         lambda a: a.replace_in_body("f", "SELECT a\n    FROM t", "SELECT b\n    FROM t"), tabbed.replace("SELECT a", "SELECT b")),
        ("py tab file, one line of a string", "a.py", tabbed,
         lambda a: a.replace_in_body("f", "SELECT a", "SELECT a,\n    b"), tabbed.replace("SELECT a\n", "SELECT a,\n    b\n")),
        ("py tab file, code still in tabs", "a.py", tabbed,
         lambda a: a.replace_in_body("f", "return sql", "if sql:\n    return sql"),
         tabbed.replace("\treturn sql", "\tif sql:\n\t\treturn sql")),
        ("py docstring shifted with the code", "k.py", docstring,
         lambda a: a.replace_in_body("f", '"""One.\n\nTwo.\n"""', '"""One.\n\nThree.\n"""'), docstring.replace("Two", "Three")),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"string text ({label})", _edit_result(name, source, action), expected)

    # A snippet found as written only inside a string or a comment, and in
    # code with its indentation shifted, matches both places.
    sql = 'def f():\n    sql = """\nx = 1\ny = 2\n"""\n    x = 1\n    y = 2\n    return sql\n'
    template = "function f() {\n  const t = `\nif (a) {\n  b();\n}\n`;\n  if (a) {\n    b();\n  }\n}\n"
    refusals = [
        ("py replace_in_body (reported)", "k.py", sql, lambda a: a.replace_in_body("f", "x = 1\ny = 2", "x = 1\ny = 3"),
         "Snippet matches 2 places in body of 'f' (lines 3, 6): as written inside a string or comment, and with its "
         "indentation shifted. Include more surrounding context"),
        ("py delete_in_body", "k.py", sql, lambda a: a.delete_in_body("f", "x = 1\ny = 2"),
         "Snippet matches 2 places in body of 'f' (lines 3, 6)"),
        ("js template", "k.js", template, lambda a: a.replace_in_body("f", "if (a) {\n  b();\n}", "if (a) {\n  c();\n}"),
         "Snippet matches 2 places in body of 'f' (lines 3, 7)"),
        ("anchor", "k.py", sql, lambda a: a.insert_in_body("f", "z = 3", after="x = 1\ny = 2"),
         "Anchor matches 2 places in body of 'f' (lines 3, 6)"),
    ]
    for label, name, source, action, reason in refusals:
        _refused(f"text and shifted code ({label})", _edit_result(name, source, action), reason)
    _exact("text and shifted code (only in a string, still found)",
           _edit_result("k.py", 'def f():\n    s = """\nx = 1\n"""\n    return s\n',
                        lambda a: a.replace_in_body("f", "x = 1", "x = 2")),
           'def f():\n    s = """\nx = 2\n"""\n    return s\n')

    # A snippet may end at a Python backslash continuation.
    continued = "def f(a, b):\n    x = a + \\\n        b\n    return x\n"
    cases = [
        ("the line (reported)", lambda a: a.replace_in_body("f", "x = a + \\", "x = a - \\"), continued.replace("+", "-")),
        ("part of the line", lambda a: a.replace_in_body("f", "a + \\", "a * \\"), continued.replace("+", "*")),
    ]
    for label, action, expected in cases:
        _exact(f"backslash continuation ({label})", _edit_result("k.py", continued, action), expected)

    # insert_in_body after an anchor that opens a block puts the new lines
    # inside it, at the indentation of the line below; an anchor whose line
    # ends inside a string takes new_snippet byte for byte, in the string.
    opened = "function f(x) {\n  if (x) {\n    a();\n  }\n}\n"
    ruby = "def f(x)\n  y = x + 1\n  if y > 2\n    y = 2\n  end\nend\n"
    cases = [
        ("js (reported)", "k.js", opened, lambda a: a.insert_in_body("f", "b();", after="if (x) {"),
         "function f(x) {\n  if (x) {\n    b();\n    a();\n  }\n}\n"),
        ("js, new_snippet at the opener's indentation", "k.js", opened, lambda a: a.insert_in_body("f", "  b();", after="  if (x) {"),
         "function f(x) {\n  if (x) {\n    b();\n    a();\n  }\n}\n"),
        ("js, new_snippet already inside", "k.js", opened, lambda a: a.insert_in_body("f", "\n    b();", after="if (x) {"),
         "function f(x) {\n  if (x) {\n    b();\n    a();\n  }\n}\n"),
        ("ruby", "k.rb", ruby, lambda a: a.insert_in_body("f", "z = 0", after="if y > 2"),
         "def f(x)\n  y = x + 1\n  if y > 2\n    z = 0\n    y = 2\n  end\nend\n"),
        ("python", "k.py", "def f(x):\n    if x:\n        a()\n", lambda a: a.insert_in_body("f", "b()", after="if x:"),
         "def f(x):\n    if x:\n        b()\n        a()\n"),
        ("after the block it opens", "k.js", opened, lambda a: a.insert_in_body("f", "b();", after="if (x) {\n    a();\n  }"),
         "function f(x) {\n  if (x) {\n    a();\n  }\n  b();\n}\n"),
        ("an opener with a comment after it", "k.js", "function f(x) {\n  if (x) { // open\n    a();\n  }\n}\n",
         lambda a: a.insert_in_body("f", "b();", after="if (x) {"),
         "function f(x) {\n  if (x) { // open\n    b();\n    a();\n  }\n}\n"),
        ("the opening line of a block comment", "k.js", "function f() {\n  /**\n   * Doc.\n   */\n  a();\n}\n",
         lambda a: a.insert_in_body("f", " * More.", after="/**"),
         "function f() {\n  /**\n   * More.\n   * Doc.\n   */\n  a();\n}\n"),
        ("js template line", "k.js", "function f(k) {\n  const m = `a ${k}\nb`;\n  return m;\n}\n",
         lambda a: a.insert_in_body("f", " c", after="const m = `a ${k}"),
         "function f(k) {\n  const m = `a ${k} c\nb`;\n  return m;\n}\n"),
        ("python string line", "k.py", 'def f(k):\n    m = """a\nb"""\n    return m\n',
         lambda a: a.insert_in_body("f", " c", after='m = """a'), 'def f(k):\n    m = """a c\nb"""\n    return m\n'),
        ("before a line inside a string", "k.py", 'def f(k):\n    m = """a\n    b"""\n    return m\n',
         lambda a: a.insert_in_body("f", "c ", before='b"""'), 'def f(k):\n    m = """a\n    c b"""\n    return m\n'),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"anchored lines ({label})", _edit_result(name, source, action), expected)
    _refused("anchored lines (after the line that opens a heredoc, in its text)",
             _edit_result("k.rb", "def f\n  sql = <<-SQL\n    SELECT *\n  SQL\n  sql\nend\n",
                          lambda a: a.insert_in_body("f", "puts 'x'", after="sql = <<-SQL")), "syntax error")
    # The lines of a docstring, a `<<~` heredoc or a Java text block are
    # indented like code, and new ones go on lines of their own.
    doc = 'class A:\n    def f(self):\n        """One.\n\n        Two.\n        """\n        return 1\n'
    three = doc.replace("        Two.\n", "        Two.\n        Three.\n")
    aligned = ('class T:\n    def h(self, a):\n        """h(chunks : [string],\n             cur_line : [string])\n\n'
               '        Text.\n        """\n        return 1\n')
    cases = [
        ("a line after a docstring line", "k.py", doc, lambda a: a.insert_in_body("A.f", "Three.", after="Two."), three),
        ("a docstring line replaced by two", "k.py", doc, lambda a: a.replace_in_body("A.f", "Two.", "Two.\nThree."), three),
        ("a docstring line and its end shifted", "k.py", doc,
         lambda a: a.replace_in_body("A.f", 'Two.\n"""', 'Two.\nThree.\n"""'), three),
        ("a docstring's opening lines shifted and given back", "k.py", aligned,
         lambda a: a.replace_in_body("T.h", '"""h(chunks : [string],\n     cur_line : [string])',
                                     '"""h(chunks : [string],\n     cur_line : [string])'), aligned),
        ("a line after a docstring line, aligned text below", "k.py", aligned,
         lambda a: a.insert_in_body("T.h", "x", after='"""h(chunks : [string],'),
         aligned.replace("[string],\n", "[string],\n        x\n", 1)),
        ("a line in a squiggly heredoc", "k.rb", "def f\n  sql = <<~SQL\n    SELECT *\n  SQL\n  sql\nend\n",
         lambda a: a.insert_in_body("f", "FROM t", after="SELECT *"),
         "def f\n  sql = <<~SQL\n    SELECT *\n    FROM t\n  SQL\n  sql\nend\n"),
        ("a line in a java text block", "K.java",
         'class K {\n    String f() {\n        return """\n            a\n            """;\n    }\n}\n',
         lambda a: a.insert_in_body("K.f", "b", after="a"),
         'class K {\n    String f() {\n        return """\n            a\n            b\n            """;\n    }\n}\n'),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"anchored lines ({label})", _edit_result(name, source, action), expected)

    # Several lines in read_symbol's shape (the first without indentation,
    # the others at their file indentation) go in as written, the first
    # at the anchor line's indentation; new_snippet at column 0 after an
    # anchor written with its indentation is indented like it. A Python
    # new_snippet that would not parse in one shape is taken in the other.
    small = "def f(x):\n    a = 1\n    return a\n"
    nested = "def f(x):\n    a = 1\n    if x:\n        a = 2\n    return a\n"
    assign = "function f(x) {\n  let a = 1;\n  return a;\n}\n"
    js_nested = "function f(x) {\n  let a = 1;\n  if (x) {\n    a = 2;\n  }\n  return a;\n}\n"
    cases = [
        ("before, as placed byte for byte (reported)", "k.py", small,
         lambda a: a.insert_in_body("f", "if x:\n        a = 2\n    ", before="return a"), nested),
        ("js before, as placed byte for byte", "k.js", assign,
         lambda a: a.insert_in_body("f", "if (x) {\n    a = 2;\n  }\n  ", before="return a;"), js_nested),
        ("before, in read_symbol's shape", "k.py", small,
         lambda a: a.insert_in_body("f", "if x:\n        a = 2", before="return a"), nested),
        ("after, in read_symbol's shape", "k.py", small,
         lambda a: a.insert_in_body("f", "if x:\n        a = 2", after="a = 1"), nested),
        ("relative", "k.py", small, lambda a: a.insert_in_body("f", "if x:\n    a = 2", before="return a"), nested),
        ("js relative", "k.js", assign, lambda a: a.insert_in_body("f", "if (x) {\n  a = 2;\n}", before="return a;"),
         js_nested),
        ("column 0 after an anchor with its indentation", "k.py", small,
         lambda a: a.insert_in_body("f", "y = 2", after="    a = 1"), "def f(x):\n    a = 1\n    y = 2\n    return a\n"),
        ("column 0 before an anchor with its indentation", "k.py", small,
         lambda a: a.insert_in_body("f", "y = 2", before="    return a"), "def f(x):\n    a = 1\n    y = 2\n    return a\n"),
        ("column 0 after two lines with their indentation", "k.py", small,
         lambda a: a.insert_in_body("f", "y = 2", after="    a = 1\n    return a"),
         "def f(x):\n    a = 1\n    return a\n    y = 2\n"),
        ("shifted snippet given back as it was", "k.js", "class Legacy {\n  run() {\n    return 1;\n  }\n};\n",
         lambda a: a.replace_in_body("Legacy", "run() {\n  return 1;", "run() {\n  return 1;"),
         "class Legacy {\n  run() {\n    return 1;\n  }\n};\n"),
        ("replace_in_body, later lines written out of the block", "k.py",
         "def f(x):\n    if x:\n        return 2\n    return 3\n",
         lambda a: a.replace_in_body("f", "return 2", "return 2\n    y = 3"),
         "def f(x):\n    if x:\n        return 2\n    y = 3\n    return 3\n"),
        ("replace_in_body, relative later lines", "k.py", "def f(x):\n    x = 1\n    return x\n",
         lambda a: a.replace_in_body("f", "x = 1", "x = 1\nif x:\n    return 3"),
         "def f(x):\n    x = 1\n    if x:\n        return 3\n    return x\n"),
        ("replace_in_body, relative later lines at the body's depth", "k.py", "def f(x):\n    x = 1\n    return x\n",
         lambda a: a.replace_in_body("f", "x = 1", "if x:\n    return 3"),
         "def f(x):\n    if x:\n        return 3\n    return x\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"read_symbol-shaped lines ({label})", _edit_result(name, source, action), expected)

    # Tabs: the code of the symbol decides, not the text of its strings or
    # the lines that align a continued call.
    strings = 'def f():\n    return """\nall:\n\techo hi\n"""\n\n\ndef g():\n    pass\n'
    tab_string = 'def f():\n    s = """\n\tindented with a tab\n"""\n    return s\n\n\ndef g():\n    return 1\n'
    gnu = 'int\nf (char *arg)\n{\n  printf ("%s has %d\\n",\n\t  arg,\n\t  n);\n  return (0);\n}\n'
    cases = [
        ("py replace_function (reported)", "k.py", strings, lambda a: a.replace_function("f", "def f():\n    if x:\n        return 1"),
         "def f():\n    if x:\n        return 1\n\n\ndef g():\n    pass\n"),
        ("py insert_sibling", "k.py", strings, lambda a: a.insert_sibling("f", "def h():\n    if x:\n        return 1", "after"),
         strings.replace("\n\n\ndef g", "\n\n\ndef h():\n    if x:\n        return 1\n\n\ndef g")),
        ("js template", "k.js", "function f() {\n  return `\n\tx\n`;\n}\n",
         lambda a: a.replace_function("f", "function f() {\n  if (a) {\n    return 1;\n  }\n}"),
         "function f() {\n  if (a) {\n    return 1;\n  }\n}\n"),
        ("py tab in a string", "k.py", tab_string,
         lambda a: a.replace_function("f", "def f():\n    if x:\n        return 2\n    return 1"),
         "def f():\n    if x:\n        return 2\n    return 1\n\n\ndef g():\n    return 1\n"),
        ("c continuation aligned with a tab", "k.c", gnu,
         lambda a: a.replace_function("f", "int\nf (char *arg)\n{\n  if (arg)\n    return (1);\n  return (0);\n}"),
         "int\nf (char *arg)\n{\n  if (arg)\n    return (1);\n  return (0);\n}\n"),
        ("py tab-indented function", "k.py", "def f():\n\tif x:\n\t\treturn 1\n",
         lambda a: a.replace_function("f", "def f():\n    if x:\n        return 2"), "def f():\n\tif x:\n\t\treturn 2\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"tabs beside ({label})", _edit_result(name, source, action), expected)

    # A block comment that ends on the symbol's first line: its later lines
    # keep the indentation they have below the comment's first line.
    commented = [
        ("java", "k.java", "class A {\n    /**\n     * Doc.\n     */ void f() {\n        g();\n    }\n}\n", "A.f",
         "void f() {\n    h();\n}", "class A {\n    /**\n     * Doc.\n     */ void f() {\n        h();\n    }\n}\n"),
        ("c", "k.c", "/*\n * c\n */ int f(void) {\n    return 0;\n}\n", "f", "int f(void) {\n    return 1;\n}",
         "/*\n * c\n */ int f(void) {\n    return 1;\n}\n"),
        ("ts", "k.ts", "/*\n * c\n */ class A {\n  m(): void {}\n}\n", "A", "class A {\n  n(): void {}\n}",
         "/*\n * c\n */ class A {\n  n(): void {}\n}\n"),
        ("js", "k.js", "/* a\n   b */ function f() {\n  return 1;\n}\n", "f", "function f() {\n  return 2;\n}",
         "/* a\n   b */ function f() {\n  return 2;\n}\n"),
    ]
    for label, name, source, target, content, expected in commented:
        _exact(f"comment ending on the first line ({label} round trip)", _round_trip(name, source, target), "<unchanged>")
        _exact(f"comment ending on the first line ({label})",
               _edit_result(name, source, lambda a, t=target, c=content: a.replace_function(t, c)), expected)

    # An f-string or bytes literal is no docstring.
    cases = [
        ("an f-string first", 'f"{setup()}"\nimport os\n', '"""Doc."""\n\nf"{setup()}"\nimport os\n'),
        ("a bytes literal first", 'b"x"\nimport os\n', '"""Doc."""\n\nb"x"\nimport os\n'),
        ("a raw docstring", 'r"""Old."""\nimport os\n', '"""Doc."""\nimport os\n'),
    ]
    for label, source, expected in cases:
        _exact(f"module docstring ({label})",
               _edit_result("k.py", source, lambda a: a.replace_docstring("", '"""Doc."""')), expected)

    # One-line code joins the stack of one-line siblings next to it; after
    # imports, includes and a package clause new code is set apart.
    fields = "class C:\n    a: int\n    b: int\n\n    def m(self):\n        pass\n"
    cases = [
        ("a field before a method (reported)", "k.py", fields, lambda a: a.insert_sibling("C.m", "c: int = 0", "before"),
         "class C:\n    a: int\n    b: int\n    c: int = 0\n\n    def m(self):\n        pass\n"),
        ("a field after a method", "k.py", "class C:\n    def m(self):\n        pass\n\n    a: int\n    b: int\n",
         lambda a: a.insert_sibling("C.m", "c: int = 0", "after"),
         "class C:\n    def m(self):\n        pass\n\n    c: int = 0\n    a: int\n    b: int\n"),
        ("a constant before a def", "k.py", "X = 1\nY = 2\n\n\ndef m():\n    pass\n",
         lambda a: a.insert_sibling("m", "Z = 3", "before"), "X = 1\nY = 2\nZ = 3\n\n\ndef m():\n    pass\n"),
        ("a lone field before a method", "k.py", "class C:\n    a: int\n\n    def m(self):\n        pass\n",
         lambda a: a.insert_sibling("C.m", "c: int = 0", "before"),
         "class C:\n    a: int\n\n    c: int = 0\n\n    def m(self):\n        pass\n"),
    ]
    for label, name, source, action, expected in cases:
        _exact(f"stacked siblings ({label})", _edit_result(name, source, action), expected)
    cases = [
        ("py imports (reported)", "k.py", "import os\nimport sys\n", "Z = 3", "import os\nimport sys\n\nZ = 3\n"),
        ("py future import", "k.py", "from __future__ import annotations\nimport os\n", "LOG = os.getenv('LOG')",
         "from __future__ import annotations\nimport os\n\nLOG = os.getenv('LOG')\n"),
        ("js imports", "k.js", 'import a from "a";\nimport b from "b";\n', "const Z = 3;",
         'import a from "a";\nimport b from "b";\n\nconst Z = 3;\n'),
        ("c includes", "k.c", "#include <a.h>\n#include <b.h>\n", "int x = 1;", "#include <a.h>\n#include <b.h>\n\nint x = 1;\n"),
        ("header includes", "k.h", "#ifndef A_H\n#define A_H\n\n#include <a.h>\n#include <b.h>\n\n#endif\n", "int f(void);",
         "#ifndef A_H\n#define A_H\n\n#include <a.h>\n#include <b.h>\n\nint f(void);\n\n#endif\n"),
        ("go package and import", "k.go", 'package main\nimport "fmt"\n', "var z = 3", 'package main\nimport "fmt"\n\nvar z = 3\n'),
        ("an import after imports", "k.py", "import os\nimport sys\n", "import re", "import os\nimport sys\nimport re\n"),
    ]
    for label, name, source, content, expected in cases:
        _exact(f"add_top_level after imports ({label})", _edit_result(name, source, lambda a, c=content: a.add_top_level(c)),
               expected)

    # Mixed line breaks: the lines next to the edit keep theirs although
    # they read like the lines the edit removed or added.
    cases = [
        ("delete_symbol (reported)", "class A {\r\n    @Override\r\n    public void a() {}\r\n    @Override\n    public void b() {}\n}\n",
         lambda a: a.delete_symbol("A.a"), "class A {\r\n    @Override\n    public void b() {}\n}\n"),
        ("insert_sibling", "class A {\r\n    @Override\r\n    public void a() {}\r\n\r\n    @Override\n    public void b() {}\n}\n",
         lambda a: a.insert_sibling("A.b", "@Override\npublic void c() {}", "before"),
         "class A {\r\n    @Override\r\n    public void a() {}\r\n\r\n    @Override\r\n    public void c() {}\r\n\r\n"
         "    @Override\n    public void b() {}\n}\n"),
        ("insert_in_body", "class A {\r\n    int x;\r\n    void a() {\r\n        g();\r\n        g();\n    }\n}\n",
         lambda a: a.insert_in_body("A.a", "g();", before="g();\n    }"),
         "class A {\r\n    int x;\r\n    void a() {\r\n        g();\r\n        g();\r\n        g();\n    }\n}\n"),
    ]
    for label, source, action, expected in cases:
        path = _write_temp("K.java", "")
        with open(path, "wb") as f:
            f.write(source.encode("utf-8"))
        try:
            action(Applier(path))
            result = _read_bytes(path).decode("utf-8")
        except ApplierError as e:
            result = f"REFUSED: {e}"
        os.remove(path)
        _exact(f"mixed line breaks ({label})", result, expected)


def test_final_docstring_literals():
    print("\n═══ replace_docstring takes a string literal for a function, method or class too ═══")

    # Bare text would go in as a statement (`Summary` over `return 1`): it
    # is refused, the file unchanged, as it is for the module (target "").
    targets = [
        ("a function without a docstring (reported)", "def f():\n    return 1\n", "f"),
        ("a function's docstring", 'def f():\n    """Old."""\n    return 1\n', "f"),
        ("a method", "class A:\n    def m(self):\n        return 1\n", "A.m"),
        ("a class", 'class A:\n    """Old."""\n\n    x = 1\n', "A"),
        ("a decorated function", "@cache\ndef f():\n    return 1\n", "f"),
    ]
    contents = [("a word", "Summary"), ("a sentence", "Return the sum."), ("an f-string", 'f"""Summary."""'),
                ("a bytes literal", 'b"""Summary."""'), ("nothing", "")]
    for label, source, target in targets:
        for kind, docstring in contents:
            _refused(f"docstring that is no string literal ({label}, {kind})",
                     _edit_result("d.py", source, lambda a, t=target, d=docstring: a.replace_docstring(t, d)),
                     "new_docstring is not a Python string literal: write it with its quotes, as in "
                     "'\"\"\"Summary.\"\"\"'")

    # A string literal goes in as before, whatever its quotes and prefix.
    cases = [
        ("inserted", "def f():\n    return 1\n", "f", '"""Summary."""', 'def f():\n    """Summary."""\n    return 1\n'),
        ("replaced", 'def f():\n    """Old."""\n    return 1\n', "f", "'''Summary.'''",
         "def f():\n    '''Summary.'''\n    return 1\n"),
        ("a method's, raw", "class A:\n    def m(self):\n        return 1\n", "A.m", 'r"""Summary."""',
         'class A:\n    def m(self):\n        r"""Summary."""\n        return 1\n'),
        ("a class's, one quote", "class A:\n    x = 1\n", "A", '"Summary."', 'class A:\n    "Summary."\n    x = 1\n'),
    ]
    for label, source, target, docstring, expected in cases:
        _exact(f"docstring literal ({label})",
               _edit_result("d.py", source, lambda a, t=target, d=docstring: a.replace_docstring(t, d)), expected)


def test_final_keyword_only_parameters():
    print("\n═══ remove_parameter of *args keeps the parameters after it keyword-only ═══")

    # The parameters after `*args`, but a `**kwargs`, are keyword-only: a
    # bare `*` takes the place of `*args` to keep them so. Without them it
    # goes alone.
    cases = [
        ("a keyword-only parameter after it (reported)", "def f(a, *args, b):\n    pass\n", "f",
         "def f(a, *, b):\n    pass\n"),
        ("a default and **kw after it", "def f(a, *args, b=1, **kw):\n    pass\n", "f",
         "def f(a, *, b=1, **kw):\n    pass\n"),
        ("nothing after it", "def f(a, *args):\n    pass\n", "f", "def f(a):\n    pass\n"),
        ("only **kw after it", "def f(a, *args, **kw):\n    pass\n", "f", "def f(a, **kw):\n    pass\n"),
        ("annotated", "def f(a, *args: int, b: str):\n    pass\n", "f", "def f(a, *, b: str):\n    pass\n"),
        ("first", "def f(*args, b):\n    pass\n", "f", "def f(*, b):\n    pass\n"),
        ("a method", "class K:\n    def m(self, *args, b):\n        pass\n", "K.m",
         "class K:\n    def m(self, *, b):\n        pass\n"),
        ("one per line", "def f(\n    a,\n    *args,\n    b,\n):\n    pass\n", "f",
         "def f(\n    a,\n    *,\n    b,\n):\n    pass\n"),
        ("one per line, **kw after it", "def f(\n    a,\n    *args,\n    **kw,\n):\n    pass\n", "f",
         "def f(\n    a,\n    **kw,\n):\n    pass\n"),
        ("after a /", "def f(a, /, *args, b):\n    pass\n", "f", "def f(a, /, *, b):\n    pass\n"),
        ("an async def", "async def f(a, *args, b):\n    pass\n", "f", "async def f(a, *, b):\n    pass\n"),
    ]
    for label, source, target, expected in cases:
        _exact(f"remove *args ({label})",
               _edit_result("k.py", source, lambda a, t=target: a.remove_parameter(t, "args")), expected)


def test_final_last_parameters():
    print("\n═══ add_parameter keeps a parameter that must come last at the end ═══")

    # 'end' goes before the parameters that must stay last: a JS/TS rest
    # parameter, a Go or Java variadic one, the `...` of C and C++ and a C++
    # parameter pack, a Ruby `**opts`, `**nil`, `&blk` or `...`, and a
    # Python `**kwargs` (after `*args` a new parameter is keyword-only, so
    # it goes last). 'start' goes after a TS `this` parameter or a Java
    # receiver parameter, which must stay first.
    cases = [
        ("js rest (reported)", "k.js", "function f(a, ...rest) {}\n", "f", "b", "end", "function f(a, b, ...rest) {}\n"),
        ("js rest alone", "k.js", "function f(...rest) {}\n", "f", "b", "end", "function f(b, ...rest) {}\n"),
        ("js rest alone, start", "k.js", "function f(...rest) {}\n", "f", "b", "start", "function f(b, ...rest) {}\n"),
        ("js rest, start", "k.js", "function f(a, ...rest) {}\n", "f", "b", "start", "function f(b, a, ...rest) {}\n"),
        ("js arrow function", "k.js", "const g = (a, ...r) => {};\n", "g", "b", "end", "const g = (a, b, ...r) => {};\n"),
        ("js method", "k.js", "class K {\n  m(a, ...r) {}\n}\n", "K.m", "b", "end", "class K {\n  m(a, b, ...r) {}\n}\n"),
        ("js destructured rest", "k.js", "function f(a, ...[x, y]) {}\n", "f", "b", "end",
         "function f(a, b, ...[x, y]) {}\n"),
        ("js one per line", "k.js", "function f(\n  a,\n  ...rest\n) {}\n", "f", "b", "end",
         "function f(\n  a,\n  b,\n  ...rest\n) {}\n"),
        ("js one per line, a comment above the rest", "k.js", "function f(\n  a,\n  // the rest\n  ...rest\n) {}\n",
         "f", "b", "end", "function f(\n  a,\n  b,\n  // the rest\n  ...rest\n) {}\n"),
        ("js aligned", "k.js", "function f(a,\n           ...rest) {}\n", "f", "b", "end",
         "function f(a,\n           b,\n           ...rest) {}\n"),
        ("js rest alone on a line", "k.js", "function f(\n  ...rest\n) {}\n", "f", "b", "end",
         "function f(\n  b,\n  ...rest\n) {}\n"),
        ("ts rest with a type", "k.ts", "function f(a: number, ...rest: string[]) {}\n", "f", "b: number", "end",
         "function f(a: number, b: number, ...rest: string[]) {}\n"),
        ("ts arrow function", "k.ts", "const g = (a: number, ...r: number[]): void => {};\n", "g", "b?: string", "end",
         "const g = (a: number, b?: string, ...r: number[]): void => {};\n"),
        ("ts method", "k.ts", "class K {\n  m(a: number, ...r: number[]): void {}\n}\n", "K.m", "b = 1", "end",
         "class K {\n  m(a: number, b = 1, ...r: number[]): void {}\n}\n"),
        ("ts this, start", "k.ts", "function f(this: Window, a: number) {}\n", "f", "b: number", "start",
         "function f(this: Window, b: number, a: number) {}\n"),
        ("ts this alone, start", "k.ts", "function f(this: Window) {}\n", "f", "b: number", "start",
         "function f(this: Window, b: number) {}\n"),
        ("ts this and rest", "k.ts", "function f(this: Window, ...r: number[]) {}\n", "f", "b: number", "end",
         "function f(this: Window, b: number, ...r: number[]) {}\n"),
        ("go variadic (reported)", "k.go", "package main\n\nfunc f(a int, xs ...int) {}\n", "f", "b string", "end",
         "package main\n\nfunc f(a int, b string, xs ...int) {}\n"),
        ("go variadic alone", "k.go", "package main\n\nfunc f(xs ...int) {}\n", "f", "b string", "end",
         "package main\n\nfunc f(b string, xs ...int) {}\n"),
        ("go method", "k.go", "package main\n\ntype S struct{}\n\nfunc (s *S) f(a int, xs ...int) {}\n", "S.f", "b string",
         "end", "package main\n\ntype S struct{}\n\nfunc (s *S) f(a int, b string, xs ...int) {}\n"),
        ("go one per line", "k.go", "package main\n\nfunc f(\n\ta int,\n\txs ...int,\n) {}\n", "f", "b string", "end",
         "package main\n\nfunc f(\n\ta int,\n\tb string,\n\txs ...int,\n) {}\n"),
        ("java varargs", "K.java", "class A {\n    void f(int a, String... xs) {}\n}\n", "A.f", "int b", "end",
         "class A {\n    void f(int a, int b, String... xs) {}\n}\n"),
        ("java varargs, start", "K.java", "class A {\n    void f(int a, String... xs) {}\n}\n", "A.f", "int b", "start",
         "class A {\n    void f(int b, int a, String... xs) {}\n}\n"),
        ("java varargs one per line", "K.java", "class A {\n    void f(\n        int a,\n        String... xs\n    ) {}\n}\n",
         "A.f", "int b", "end", "class A {\n    void f(\n        int a,\n        int b,\n        String... xs\n    ) {}\n}\n"),
        ("java receiver, start", "K.java", "class A {\n    void g(A this, int a) {}\n}\n", "A.g", "int b", "start",
         "class A {\n    void g(A this, int b, int a) {}\n}\n"),
        ("c ...", "k.c", "int f(int a, ...) { return 0; }\n", "f", "int b", "end", "int f(int a, int b, ...) { return 0; }\n"),
        ("c ..., start", "k.c", "int f(int a, ...) { return 0; }\n", "f", "int b", "start",
         "int f(int b, int a, ...) { return 0; }\n"),
        ("c prototype", "k.h", "int f(const char *fmt, ...);\n", "f", "int n", "end", "int f(const char *fmt, int n, ...);\n"),
        ("c one per line", "k.c", "int f(\n    int a,\n    ...\n) { return 0; }\n", "f", "int b", "end",
         "int f(\n    int a,\n    int b,\n    ...\n) { return 0; }\n"),
        ("cpp ...", "k.cpp", "int f(int a, ...) { return 0; }\n", "f", "int b", "end", "int f(int a, int b, ...) { return 0; }\n"),
        ("cpp ... alone", "k.cpp", "int f(...) { return 0; }\n", "f", "int b", "end", "int f(int b, ...) { return 0; }\n"),
        ("cpp ... alone, start", "k.cpp", "int f(...) { return 0; }\n", "f", "int b", "start",
         "int f(int b, ...) { return 0; }\n"),
        ("cpp one per line", "k.cpp", "int f(\n    int a,\n    ...\n) { return 0; }\n", "f", "int b", "end",
         "int f(\n    int a,\n    int b,\n    ...\n) { return 0; }\n"),
        ("cpp parameter pack", "k.cpp", "template <typename... Ts> void h(int a, Ts... xs) {}\n", "h", "int b", "end",
         "template <typename... Ts> void h(int a, int b, Ts... xs) {}\n"),
        ("rb &blk", "k.rb", "def f(a, &blk)\nend\n", "f", "b", "end", "def f(a, b, &blk)\nend\n"),
        ("rb **opts before &blk", "k.rb", "def f(a, **opts, &blk)\nend\n", "f", "b", "end", "def f(a, b, **opts, &blk)\nend\n"),
        ("rb **opts", "k.rb", "def f(a, **opts)\nend\n", "f", "k: 1", "end", "def f(a, k: 1, **opts)\nend\n"),
        ("rb **nil", "k.rb", "def f(a, **nil)\nend\n", "f", "b", "end", "def f(a, b, **nil)\nend\n"),
        ("rb ...", "k.rb", "def f(a, ...)\nend\n", "f", "b", "end", "def f(a, b, ...)\nend\n"),
        ("rb &blk alone", "k.rb", "def f(&blk)\nend\n", "f", "b", "end", "def f(b, &blk)\nend\n"),
        ("rb without parentheses", "k.rb", "def f a, &blk\nend\n", "f", "b", "end", "def f a, b, &blk\nend\n"),
        ("rb one per line", "k.rb", "def f(\n  a,\n  **opts,\n  &blk\n)\nend\n", "f", "b", "end",
         "def f(\n  a,\n  b,\n  **opts,\n  &blk\n)\nend\n"),
        ("rb aligned", "k.rb", "def f(**opts,\n      &blk)\nend\n", "f", "b", "end",
         "def f(b,\n      **opts,\n      &blk)\nend\n"),
        ("py **kw", "k.py", "def f(a, **kw):\n    pass\n", "f", "b", "end", "def f(a, b, **kw):\n    pass\n"),
        ("py *args stays before it", "k.py", "def f(a, *args):\n    pass\n", "f", "b", "end",
         "def f(a, *args, b):\n    pass\n"),
        ("py *args and **kw", "k.py", "def f(a, *args, **kw):\n    pass\n", "f", "b", "end",
         "def f(a, *args, b, **kw):\n    pass\n"),
        ("js function expression", "k.js", "const f = function (a, ...r) {};\n", "f", "b", "end",
         "const f = function (a, b, ...r) {};\n"),
        ("js one per line, trailing comma", "k.js", "function f(\n  a,\n  ...rest,\n) {}\n", "f", "b", "end",
         "function f(\n  a,\n  b,\n  ...rest,\n) {}\n"),
        ("ts this one per line, start", "k.ts", "function f(\n  this: Window,\n  a: number\n) {}\n", "f", "b: number",
         "start", "function f(\n  this: Window,\n  b: number,\n  a: number\n) {}\n"),
        ("ts method this, start", "k.ts", "class K {\n  m(this: K, a: number): void {}\n}\n", "K.m", "b: number", "start",
         "class K {\n  m(this: K, b: number, a: number): void {}\n}\n"),
        ("go func literal", "k.go", "package main\n\nvar f = func(a int, xs ...int) {}\n", "f", "b string", "end",
         "package main\n\nvar f = func(a int, b string, xs ...int) {}\n"),
        ("java constructor varargs", "K.java", "class A {\n    A(int a, String... xs) {}\n}\n", "A.A", "int b", "end",
         "class A {\n    A(int a, int b, String... xs) {}\n}\n"),
        ("java receiver alone, start", "K.java", "class A {\n    void g(A this) {}\n}\n", "A.g", "int b", "start",
         "class A {\n    void g(A this, int b) {}\n}\n"),
        ("cpp method ...", "k.cpp", "class K {\n    int m(int a, ...) { return 0; }\n};\n", "K.m", "int b", "end",
         "class K {\n    int m(int a, int b, ...) { return 0; }\n};\n"),
        ("rb singleton method", "k.rb", "class K\n  def self.f(a, &blk)\n  end\nend\n", "K.f", "b", "end",
         "class K\n  def self.f(a, b, &blk)\n  end\nend\n"),
        ("rb anonymous ** and &", "k.rb", "def f(a, **, &)\nend\n", "f", "b", "end", "def f(a, b, **, &)\nend\n"),
        ("rb one per line, comments", "k.rb", "def f(\n  a, # a\n  &blk # the block\n)\nend\n", "f", "b", "end",
         "def f(\n  a, # a\n  b,\n  &blk # the block\n)\nend\n"),
    ]
    for label, name, source, target, parameter, position, expected in cases:
        _exact(f"add_parameter ({label})",
               _edit_result(name, source, lambda a, t=target, p=parameter, s=position: a.add_parameter(t, p, s)), expected)


def test_final_c_variadic_parameters():
    print("\n═══ remove_parameter keeps a named parameter before a C `...` ═══")

    # Before C23 a C function needs a named parameter before its `...`, and
    # tree-sitter takes `f(...)` anyway: removing the last one is refused in
    # .c and .h files. C++ allows `f(...)`.
    reason = "C needs a named parameter before `...`"
    cases = [
        ("a definition (reported)", "k.c", "int f(int a, ...) { return 0; }\n"),
        ("a prototype", "k.h", "int f(int a, ...);\n"),
        ("one per line", "k.c", "int f(\n    int a,\n    ...\n) { return 0; }\n"),
        ("a comment stays in the list", "k.c", "int f(int a /* a */, ...) { return 0; }\n"),
    ]
    for label, name, source in cases:
        _refused(f"c last named parameter before ... ({label})",
                 _edit_result(name, source, lambda a: a.remove_parameter("f", "a")), reason)
    cases = [
        ("c another one stays", "k.c", "int f(int a, int b, ...) { return 0; }\n", "a", "int f(int b, ...) { return 0; }\n"),
        ("c the last before ...", "k.c", "int f(int a, int b, ...) { return 0; }\n", "b", "int f(int a, ...) { return 0; }\n"),
        ("cpp f(...)", "k.cpp", "int f(int a, ...) { return 0; }\n", "a", "int f(...) { return 0; }\n"),
        ("cpp one per line", "k.cpp", "int f(\n    int a,\n    ...\n) { return 0; }\n", "a",
         "int f(\n    ...\n) { return 0; }\n"),
        ("cpp the last before ...", "k.cpp", "int f(int a, int b, ...) { return 0; }\n", "b",
         "int f(int a, ...) { return 0; }\n"),
        ("c the only one leaves (void)", "k.c", "int f(int a) { return 0; }\n", "a", "int f(void) { return 0; }\n"),
    ]
    for label, name, source, parameter, expected in cases:
        _exact(f"remove_parameter beside ... ({label})",
               _edit_result(name, source, lambda a, p=parameter: a.remove_parameter("f", p)), expected)


def test_final_same_line_comments():
    print("\n═══ delete_symbol keeps a comment before the symbol on its line on request ═══")

    # With include_leading_comments=False a comment before the symbol on its
    # first line stays, on a line of its own, spaced as one above it would
    # be; with the default it goes, as one above it does.
    cases = [
        ("js (reported)", "k.js", "/** @type {X} */ let x;\nlet y;\n", "x",
         "/** @type {X} */\nlet y;\n", "let y;\n"),
        ("c", "k.c", "/* c */ int x;\nint y;\n", "x", "/* c */\nint y;\n", "int y;\n"),
        ("ts", "k.ts", "/** c */ let x: number;\nlet y: number;\n", "x",
         "/** c */\nlet y: number;\n", "let y: number;\n"),
        ("go", "k.go", "package main\n\n/* c */ var x int\n\nvar y int\n", "x",
         "package main\n\n/* c */\n\nvar y int\n", "package main\n\nvar y int\n"),
        ("a java field", "K.java", "class A {\n    /** c */ int x;\n    int y;\n}\n", "A.x",
         "class A {\n    /** c */\n    int y;\n}\n", "class A {\n    int y;\n}\n"),
        ("a c++ field", "k.cpp", "class A {\n  /* c */ int x;\n  int y;\n};\n", "A.x",
         "class A {\n  /* c */\n  int y;\n};\n", "class A {\n  int y;\n};\n"),
        ("a function", "k.js", "/* c */ function f() {\n  return 1;\n}\nlet y;\n", "f",
         "/* c */\nlet y;\n", "let y;\n"),
        ("a comment above too", "k.js", "// a\n/** c */ let x;\nlet y;\n", "x",
         "// a\n/** c */\nlet y;\n", "let y;\n"),
        ("a block comment that began above", "k.js", "/* a\n b */ let x;\nlet y;\n", "x",
         "/* a\n b */\nlet y;\n", "let y;\n"),
        ("two comments", "k.js", "/* a */ /* b */ let x;\nlet y;\n", "x", "/* a */ /* b */\nlet y;\n", "let y;\n"),
        ("a comment after it goes", "k.js", "/* a */ let x; // t\nlet y;\n", "x", "/* a */\nlet y;\n", "let y;\n"),
        ("between blank lines", "k.js", "let a;\n\n/* c */ let x;\n\nlet y;\n", "x",
         "let a;\n\n/* c */\n\nlet y;\n", "let a;\n\nlet y;\n"),
        ("last", "k.js", "let a;\n\n/* c */ let x;\n", "x", "let a;\n\n/* c */\n", "let a;\n"),
        # Code after it on its line stays there, after the comment or, when
        # that goes with it, at the line's indentation.
        ("code after it", "k.js", "/* c */ let x; let y;\n", "x", "/* c */ let y;\n", "let y;\n"),
        ("code after it, a comment above", "k.js", "// a\n/* c */ let x; let y;\n", "x",
         "// a\n/* c */ let y;\n", "let y;\n"),
        ("code after it, a java field", "K.java", "class A {\n    /** c */ int x; int y;\n}\n", "A.x",
         "class A {\n    /** c */ int y;\n}\n", "class A {\n    int y;\n}\n"),
    ]
    for label, name, source, target, kept, gone in cases:
        _exact(f"same-line comment kept ({label})",
               _edit_result(name, source, lambda a, t=target: a.delete_symbol(t, include_leading_comments=False)), kept)
        _exact(f"same-line comment deleted ({label})",
               _edit_result(name, source, lambda a, t=target: a.delete_symbol(t)), gone)
    _exact("same-line comment kept (crlf)",
           _edit_result("k.js", "/** c */ let x;\nlet y;\n",
                        lambda a: a.delete_symbol("x", include_leading_comments=False), "\r\n"),
           "/** c */\r\nlet y;\r\n")
    _exact("same-line comment deleted (crlf)",
           _edit_result("k.js", "/** c */ let x;\nlet y;\n", lambda a: a.delete_symbol("x"), "\r\n"), "let y;\r\n")
    # A symbol without one is deleted as before.
    _exact("same-line comment, none there",
           _edit_result("k.js", "/** c */\nlet x;\nlet y;\n", lambda a: a.delete_symbol("x", include_leading_comments=False)),
           "/** c */\nlet y;\n")


def test_final_ruby_method_clauses():
    print("\n═══ replace_function_body keeps a Ruby method's rescue, else and ensure clauses ═══")

    # The body that replace_function_body replaces is the code before the
    # method's first rescue, else or ensure clause, which stays; with no code
    # there (only comments, or nothing) it is one level deeper than the def,
    # as in an empty method.
    clauses = [
        ("rescue (reported)", "rescue => e\n  log(e)\n"),
        ("ensure", "ensure\n  close\n"),
        ("rescue and ensure", "rescue => e\n  log(e)\nensure\n  close\n"),
        ("rescue and else", "rescue => e\n  log(e)\nelse\n  ok\n"),
    ]
    for label, clause in clauses:
        expected = "def f\n  1\n" + clause + "end\n"
        _exact(f"ruby body before {label}",
               _edit_result("k.rb", "def f\n" + clause + "end\n", lambda a: a.replace_function_body("f", "1")), expected)
        _exact(f"ruby body before {label}, code there",
               _edit_result("k.rb", "def f\n  x\n  y\n" + clause + "end\n", lambda a: a.replace_function_body("f", "1")),
               expected)
        _exact(f"ruby body before {label}, a comment there",
               _edit_result("k.rb", "def f\n  # c\n" + clause + "end\n", lambda a: a.replace_function_body("f", "1")),
               expected)
    cases = [
        ("a method in a class", "class A\n  def f\n  rescue => e\n    log(e)\n  end\nend\n", "A.f", "a = 1\nb = a",
         "class A\n  def f\n    a = 1\n    b = a\n  rescue => e\n    log(e)\n  end\nend\n"),
        ("a method in a class, code there", "class A\n  def f\n    x\n  rescue => e\n    log(e)\n  end\nend\n", "A.f",
         "1", "class A\n  def f\n    1\n  rescue => e\n    log(e)\n  end\nend\n"),
        ("a singleton method", "def self.f\nrescue => e\n  log(e)\nend\n", "f", "1",
         "def self.f\n  1\nrescue => e\n  log(e)\nend\n"),
        ("parameters over lines", "def f(a,\n      b)\nrescue => e\n  log(e)\nend\n", "f", "1",
         "def f(a,\n      b)\n  1\nrescue => e\n  log(e)\nend\n"),
        ("a comment above the code stays", "def f\n  # c\n  x\nrescue => e\n  log(e)\nend\n", "f", "1",
         "def f\n  # c\n  1\nrescue => e\n  log(e)\nend\n"),
        # Content with clauses of its own replaces the method's.
        ("content with its own rescue", "def f\n  x\nrescue => e\n  log(e)\nend\n", "f", "y\nrescue => e\n  warn(e)",
         "def f\n  y\n  rescue => e\n    warn(e)\nend\n"),
        ("content with its own ensure", "def f\nrescue => e\n  log(e)\nend\n", "f", "y\nensure\n  close",
         "def f\n  y\n  ensure\n    close\nend\n"),
        ("a blank line before the clause stays", "def f\n  x\n\nrescue => e\n  log(e)\nend\n", "f", "1",
         "def f\n  1\n\nrescue => e\n  log(e)\nend\n"),
        ("tabs", "class A\n\tdef f\n\trescue => e\n\t\tlog(e)\n\tend\nend\n", "A.f", "1",
         "class A\n\tdef f\n\t\t1\n\trescue => e\n\t\tlog(e)\n\tend\nend\n"),
        # A clause that shares a line with code moves to a line of its own.
        ("a clause after code on its line", "def f\n  x; rescue => e\n  log(e)\nend\n", "f", "1",
         "def f\n  1\nrescue => e\n  log(e)\nend\n"),
        ("on one line", "def f; x; rescue => e; log(e); end\n", "f", "1", "def f\n  1\nrescue => e\n  log(e)\nend\n"),
        # A method without clauses as before.
        ("no clause", "def f\n  x\nend\n", "f", "1", "def f\n  1\nend\n"),
        ("content with an if and else", "def f\n  x\nrescue => e\n  log(e)\nend\n", "f", "if a\n  b\nelse\n  c\nend",
         "def f\n  if a\n    b\n  else\n    c\n  end\nrescue => e\n  log(e)\nend\n"),
    ]
    for label, source, target, content, expected in cases:
        _exact(f"ruby body before its clauses ({label})",
               _edit_result("k.rb", source, lambda a, t=target, c=content: a.replace_function_body(t, c)), expected)

    _exact("ruby body before its clauses (crlf)",
           _edit_result("k.rb", "def f\nrescue => e\n  log(e)\nend\n", lambda a: a.replace_function_body("f", "1"), "\r\n"),
           "def f\r\n  1\r\nrescue => e\r\n  log(e)\r\nend\r\n")

    # The other body tools on such a method, as before.
    source = "def f\nrescue => e\n  log(e)\nensure\n  close\nend\n"
    tools = [
        ("insert at top", lambda a: a.insert_in_body("f", "y = 2", at="top"),
         "def f\n  y = 2\nrescue => e\n  log(e)\nensure\n  close\nend\n"),
        ("insert at bottom", lambda a: a.insert_in_body("f", "y = 2", at="bottom"),
         "def f\n  y = 2\nrescue => e\n  log(e)\nensure\n  close\nend\n"),
        ("replace_in_body", lambda a: a.replace_in_body("f", "log(e)", "warn(e)"),
         "def f\nrescue => e\n  warn(e)\nensure\n  close\nend\n"),
        ("delete_in_body", lambda a: a.delete_in_body("f", "close"), "def f\nrescue => e\n  log(e)\nensure\nend\n"),
        ("insert after", lambda a: a.insert_in_body("f", "flush", after="close"),
         "def f\nrescue => e\n  log(e)\nensure\n  close\n  flush\nend\n"),
    ]
    for label, action, expected in tools:
        _exact(f"ruby clauses, {label}", _edit_result("k.rb", source, action), expected)
    _exact("ruby clauses, insert at bottom in a class",
           _edit_result("k.rb", "class A\n  def f\n  ensure\n    close\n  end\nend\n",
                        lambda a: a.insert_in_body("A.f", "y = 2", at="bottom")),
           "class A\n  def f\n    y = 2\n  ensure\n    close\n  end\nend\n")


def test_final_cpp_method_access():
    print("\n═══ add_method keeps a C++ method in the access section of the class's last method ═══")

    # When an access label follows the class's last method, the new method
    # goes after that method (its comment on its line too), so that it gets
    # its access, spaced as add_method spaces methods; otherwise, and in a
    # class without methods, after the last member as before.
    cases = [
        ("reported", "class Box {\npublic:\n    int get() { return v; }\nprivate:\n    int v;\n};\n", "Box", "void f() {}",
         "class Box {\npublic:\n    int get() { return v; }\n\n    void f() {}\nprivate:\n    int v;\n};\n"),
        ("a struct", "struct Box {\n    int get() { return v; }\nprivate:\n    int v;\n};\n", "Box", "void f() {}",
         "struct Box {\n    int get() { return v; }\n\n    void f() {}\nprivate:\n    int v;\n};\n"),
        ("declared methods", "class Box {\npublic:\n    int get();\n    int set(int);\nprivate:\n    int v;\n};\n", "Box",
         "void f();", "class Box {\npublic:\n    int get();\n    int set(int);\n    void f();\nprivate:\n    int v;\n};\n"),
        ("a declared destructor", "class Box {\npublic:\n    ~Box();\nprivate:\n    int v;\n};\n", "Box", "void f() {}",
         "class Box {\npublic:\n    ~Box();\n\n    void f() {}\nprivate:\n    int v;\n};\n"),
        ("a constructor", "class Box {\npublic:\n    Box() : v(0) {}\nprivate:\n    int v;\n};\n", "Box", "void f() {}",
         "class Box {\npublic:\n    Box() : v(0) {}\n\n    void f() {}\nprivate:\n    int v;\n};\n"),
        ("an operator", "class Box {\npublic:\n    bool operator==(const Box& o) const { return v == o.v; }\nprivate:\n"
         "    int v;\n};\n", "Box", "void f() {}",
         "class Box {\npublic:\n    bool operator==(const Box& o) const { return v == o.v; }\n\n    void f() {}\nprivate:\n"
         "    int v;\n};\n"),
        ("a defaulted operator", "class Box {\npublic:\n    Box& operator=(const Box&) = default;\nprivate:\n    int v;\n};\n",
         "Box", "void f() {}",
         "class Box {\npublic:\n    Box& operator=(const Box&) = default;\n\n    void f() {}\nprivate:\n    int v;\n};\n"),
        ("a pure virtual method", "class Box {\npublic:\n    virtual int get() const = 0;\nprotected:\n    int v;\n};\n", "Box",
         "virtual void f() = 0;",
         "class Box {\npublic:\n    virtual int get() const = 0;\n\n    virtual void f() = 0;\nprotected:\n    int v;\n};\n"),
        ("a member template", "class Box {\npublic:\n    template <typename T>\n    T as() const { return T(v); }\nprivate:\n"
         "    int v;\n};\n", "Box", "void f() {}",
         "class Box {\npublic:\n    template <typename T>\n    T as() const { return T(v); }\n\n    void f() {}\nprivate:\n"
         "    int v;\n};\n"),
        ("a comment after it on its line", "class Box {\npublic:\n    int get() { return v; }  // getter\nprivate:\n"
         "    int v;\n};\n", "Box", "void f() {}",
         "class Box {\npublic:\n    int get() { return v; }  // getter\n\n    void f() {}\nprivate:\n    int v;\n};\n"),
        ("a comment below it", "class Box {\npublic:\n    int get() { return v; }\n    // fields\nprivate:\n    int v;\n};\n",
         "Box", "void f() {}",
         "class Box {\npublic:\n    int get() { return v; }\n\n    void f() {}\n    // fields\nprivate:\n    int v;\n};\n"),
        ("a field after it", "class Box {\npublic:\n    int get() { return v; }\n    int w;\nprivate:\n    int v;\n};\n", "Box",
         "void f() {}",
         "class Box {\npublic:\n    int get() { return v; }\n\n    void f() {}\n    int w;\nprivate:\n    int v;\n};\n"),
        ("a blank line before the label", "class Box {\npublic:\n    int get() { return v; }\n\nprivate:\n    int v;\n};\n",
         "Box", "void f() {}",
         "class Box {\npublic:\n    int get() { return v; }\n\n    void f() {}\n\nprivate:\n    int v;\n};\n"),
        ("stacked methods", "class Box {\npublic:\n    int get() { return v; }\n    void set(int x) { v = x; }\nprivate:\n"
         "    int v;\n};\n", "Box", "void f() {}",
         "class Box {\npublic:\n    int get() { return v; }\n    void set(int x) { v = x; }\n    void f() {}\nprivate:\n"
         "    int v;\n};\n"),
        ("indented labels", "class Box {\n  public:\n    int get() { return v; }\n  protected:\n    int v;\n};\n", "Box",
         "void f() {}",
         "class Box {\n  public:\n    int get() { return v; }\n\n    void f() {}\n  protected:\n    int v;\n};\n"),
        ("over several lines", "class Box {\npublic:\n    int get() {\n        return v;\n    }\nprivate:\n    int v;\n};\n",
         "Box", "void f() {\n    v = 0;\n}",
         "class Box {\npublic:\n    int get() {\n        return v;\n    }\n\n    void f() {\n        v = 0;\n    }\nprivate:\n"
         "    int v;\n};\n"),
        ("tabs", "class Box {\npublic:\n\tint get() { return v; }\nprivate:\n\tint v;\n};\n", "Box", "void f() {}",
         "class Box {\npublic:\n\tint get() { return v; }\n\n\tvoid f() {}\nprivate:\n\tint v;\n};\n"),
        ("a nested class", "class Outer {\npublic:\n    class Inner {\n    public:\n        void a() {}\n    private:\n"
         "        int x;\n    };\n    void b() {}\nprivate:\n    int y;\n};\n", "Outer.Inner", "void f() {}",
         "class Outer {\npublic:\n    class Inner {\n    public:\n        void a() {}\n\n        void f() {}\n    private:\n"
         "        int x;\n    };\n    void b() {}\nprivate:\n    int y;\n};\n"),
        ("the class around a nested class", "class Outer {\npublic:\n    class Inner {\n    public:\n        void a() {}\n"
         "    private:\n        int x;\n    };\n    void b() {}\nprivate:\n    int y;\n};\n", "Outer", "void f() {}",
         "class Outer {\npublic:\n    class Inner {\n    public:\n        void a() {}\n    private:\n        int x;\n    };\n"
         "    void b() {}\n    void f() {}\nprivate:\n    int y;\n};\n"),
        ("a friend and a function pointer are no methods", "class Box {\npublic:\n    int get() { return v; }\nprivate:\n"
         "    friend bool eq(const Box&, const Box&);\n    int (*fp)(int);\n};\n", "Box", "void f() {}",
         "class Box {\npublic:\n    int get() { return v; }\n\n    void f() {}\nprivate:\n"
         "    friend bool eq(const Box&, const Box&);\n    int (*fp)(int);\n};\n"),
        ("on one line", "class Box { public: int get() { return v; } private: int v; };\n", "Box", "void f() {}",
         "class Box {\n  public: int get() { return v; }\n\n  void f() {}\n  private: int v;\n};\n"),
        ("the label on its line", "class Box {\npublic:\n    int get() { return v; } private:\n    int v;\n};\n", "Box",
         "void f() {}",
         "class Box {\npublic:\n    int get() { return v; }\n\n    void f() {}\nprivate:\n    int v;\n};\n"),
        # As before: no label after the last method, or no method.
        ("no labels", "class Box {\n    int get() { return v; }\n    int v;\n};\n", "Box", "void f() {}",
         "class Box {\n    int get() { return v; }\n    int v;\n\n    void f() {}\n};\n"),
        ("no methods", "class Box {\npublic:\n    int w;\nprivate:\n    int v;\n};\n", "Box", "void f() {}",
         "class Box {\npublic:\n    int w;\nprivate:\n    int v;\n\n    void f() {}\n};\n"),
        ("the last method in the last section", "class Box {\nprivate:\n    int v;\npublic:\n    int get() { return v; }\n};\n",
         "Box", "void f() {}",
         "class Box {\nprivate:\n    int v;\npublic:\n    int get() { return v; }\n    void f() {}\n};\n"),
        ("a comment after the last member", "class Box {\npublic:\n    int get() { return v; }\n    // end\n};\n", "Box",
         "void f() {}", "class Box {\npublic:\n    int get() { return v; }\n    // end\n\n    void f() {}\n};\n"),
    ]
    for label, source, target, content, expected in cases:
        _exact(f"cpp add_method access ({label})",
               _edit_result("k.cpp", source, lambda a, t=target, c=content: a.add_method(t, c)), expected)
    # Only C++ changes: a Java class has no access sections.
    _exact("cpp add_method access (java as before)",
           _edit_result("K.java", "class Box {\n    int get() { return v; }\n    private int v;\n}\n",
                        lambda a: a.add_method("Box", "void f() {}")),
           "class Box {\n    int get() { return v; }\n    private int v;\n\n    void f() {}\n}\n")


def test_final_import_groups():
    print("\n═══ add_import puts an import in its group, at its sorted place ═══")

    # A group is a run of imports that no blank line or other code
    # separates (comments may). The new import goes in the group it
    # belongs with, at its sorted place when the group is sorted, else
    # after the group's last import; when no group fits, after the last
    # import, as before. The blank lines between groups stay.
    # (label, file name, source, import text, expected file text)
    py = "import os\nimport sys\n\nimport numpy\n\nfrom app import x\n\nX = 1\n"
    c = '#include <stdio.h>\n#include <string.h>\n\n#include "b.h"\n#include "d.h"\n\nint x;\n'
    go = 'package main\n\nimport (\n\t"fmt"\n\t"os"\n\n\t"github.com/a/b"\n\n\t"example.com/me/x"\n)\n'
    js = 'import a from "a";\nimport c from "c";\n\nimport x from "./x";\nimport z from "./z";\n\nf();\n'
    cjs = "const fs = require('fs');\nconst path = require('path');\n\nconst a = require('./a');\n"
    mixed = 'import a from "a";\n\nconst b = require("b");\nconst d = require("d");\n'
    java = ("package p;\n\nimport java.util.List;\nimport java.util.Map;\n\nimport org.junit.Test;\n\n"
            "import static org.junit.Assert.assertEquals;\n\nclass A {}\n")
    rb = "require 'json'\nrequire 'set'\n\nrequire_relative 'a'\nrequire_relative 'c'\n"
    cases = [
        ("py (reported)", "m.py", "import ast\nimport json\nfrom x import (\n    a,\n    b,\n)\n\nX = 1\n", "import functools",
         "import ast\nimport functools\nimport json\nfrom x import (\n    a,\n    b,\n)\n\nX = 1\n"),
        ("py standard library", "m.py", py, "import platform",
         "import os\nimport platform\nimport sys\n\nimport numpy\n\nfrom app import x\n\nX = 1\n"),
        ("py another module, the first group of others", "m.py", py, "import requests",
         "import os\nimport sys\n\nimport numpy\nimport requests\n\nfrom app import x\n\nX = 1\n"),
        ("py the same top-level package", "m.py", py, "from app.y import z",
         "import os\nimport sys\n\nimport numpy\n\nfrom app import x\nfrom app.y import z\n\nX = 1\n"),
        ("py an import line before the from-imports", "m.py", py, "import app",
         "import os\nimport sys\n\nimport numpy\n\nimport app\nfrom app import x\n\nX = 1\n"),
        ("py a from-import after the import lines", "m.py", "import os\nimport sys\n\nx = 1\n", "from collections import abc",
         "import os\nimport sys\nfrom collections import abc\n\nx = 1\n"),
        ("py from-imports sorted among the import lines", "m.py", "from collections import abc\nimport os\nfrom typing import Any\n",
         "import json", "from collections import abc\nimport json\nimport os\nfrom typing import Any\n"),
        ("py module names compared without case", "m.py", "import abc\nimport Cython\n", "import base64",
         "import abc\nimport base64\nimport Cython\n"),
        ("py an unsorted group", "m.py", "import sys\nimport os\n\nx = 1\n", "import json",
         "import sys\nimport os\nimport json\n\nx = 1\n"),
        ("py the standard library group after another", "m.py", "import numpy\n\nimport os\n", "import abc",
         "import numpy\n\nimport abc\nimport os\n"),
        ("py no group of its kind", "m.py", "import numpy\nimport pandas\n\nx = 1\n", "import os",
         "import numpy\nimport pandas\nimport os\n\nx = 1\n"),
        ("py a relative import", "m.py", "import os\n\nfrom . import a\nfrom .c import d\n", "from .b import e",
         "import os\n\nfrom . import a\nfrom .b import e\nfrom .c import d\n"),
        ("py above the comment over the next import", "m.py", "import a\n# for c\nimport c\n", "import b",
         "import a\nimport b\n# for c\nimport c\n"),
        ("py below a comment heading the group", "m.py", "# Standard library\nimport os\nimport sys\n", "import abc",
         "# Standard library\nimport abc\nimport os\nimport sys\n"),
        ("py between imports over several lines", "m.py", "from a import (\n    x,\n)\nfrom c import (\n    y,\n)\n",
         "from b import z", "from a import (\n    x,\n)\nfrom b import z\nfrom c import (\n    y,\n)\n"),
        ("py after a __future__ import", "m.py", "from __future__ import annotations\nimport os\nimport sys\n", "import abc",
         "from __future__ import annotations\nimport abc\nimport os\nimport sys\n"),
        ("py a __future__ import goes first", "m.py", "import os\n\nx = 1\n", "from __future__ import annotations",
         "from __future__ import annotations\nimport os\n\nx = 1\n"),
        ("py a __future__ import with the others", "m.py", "from __future__ import annotations\n\nimport os\n",
         "from __future__ import division", "from __future__ import annotations\nfrom __future__ import division\n\nimport os\n"),
        ("py a __future__ import in an unsorted group", "m.py", "from __future__ import annotations\nimport sys\nimport os\n",
         "from __future__ import division",
         "from __future__ import annotations\nfrom __future__ import division\nimport sys\nimport os\n"),
        ("py after a group of __future__ imports", "m.py", "from __future__ import annotations\n\nx = 1\n", "import os",
         "from __future__ import annotations\nimport os\n\nx = 1\n"),
        ("c angle brackets", "m.c", c, "#include <stdlib.h>",
         '#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n\n#include "b.h"\n#include "d.h"\n\nint x;\n'),
        ("c quotes", "m.c", c, '#include "c.h"',
         '#include <stdio.h>\n#include <string.h>\n\n#include "b.h"\n#include "c.h"\n#include "d.h"\n\nint x;\n'),
        ("c angle brackets after quotes", "m.c", '#include "a.h"\n\n#include <stdio.h>\n', "#include <assert.h>",
         '#include "a.h"\n\n#include <assert.h>\n#include <stdio.h>\n'),
        ("cpp a shared directory", "m.cpp", "#include <stdio.h>\n\n#include <sys/stat.h>\n#include <sys/wait.h>\n",
         "#include <sys/types.h>", "#include <stdio.h>\n\n#include <sys/stat.h>\n#include <sys/types.h>\n#include <sys/wait.h>\n"),
        ("cpp not with the file's own header", "foo.cpp", '#include "foo.h"\n\n#include <string>\n\n#include "bar/baz.h"\n',
         '#include "abc.h"', '#include "foo.h"\n\n#include <string>\n\n#include "abc.h"\n#include "bar/baz.h"\n'),
        ("c in an include guard", "m.h", "#ifndef M_H\n#define M_H\n\n#include <stdio.h>\n#include <string.h>\n\nint f(void);\n\n#endif\n",
         "#include <stdlib.h>",
         "#ifndef M_H\n#define M_H\n\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n\nint f(void);\n\n#endif\n"),
        ("go standard library", "m.go", go, '"io"',
         'package main\n\nimport (\n\t"fmt"\n\t"io"\n\t"os"\n\n\t"github.com/a/b"\n\n\t"example.com/me/x"\n)\n'),
        ("go a shared path", "m.go", go, 'import "example.com/me/y"',
         'package main\n\nimport (\n\t"fmt"\n\t"os"\n\n\t"github.com/a/b"\n\n\t"example.com/me/x"\n\t"example.com/me/y"\n)\n'),
        ("go another module, the first group of others", "m.go", go, '"golang.org/x/sync"',
         'package main\n\nimport (\n\t"fmt"\n\t"os"\n\n\t"github.com/a/b"\n\t"golang.org/x/sync"\n\n\t"example.com/me/x"\n)\n'),
        ("go an alias sorts by its path", "m.go", go, 'f "path/filepath"',
         'package main\n\nimport (\n\t"fmt"\n\t"os"\n\tf "path/filepath"\n\n\t"github.com/a/b"\n\n\t"example.com/me/x"\n)\n'),
        ("go the standard library group after another", "m.go", 'package main\n\nimport (\n\t"github.com/a/b"\n\n\t"fmt"\n)\n',
         '"os"', 'package main\n\nimport (\n\t"github.com/a/b"\n\n\t"fmt"\n\t"os"\n)\n'),
        ("go no group of its kind", "m.go", 'package main\n\nimport (\n\t"fmt"\n)\n', '"github.com/a/b"',
         'package main\n\nimport (\n\t"fmt"\n\t"github.com/a/b"\n)\n'),
        ("go import lines", "m.go", 'package main\n\nimport "fmt"\nimport "os"\n\nfunc main() {}\n', 'import "io"',
         'package main\n\nimport "fmt"\nimport "io"\nimport "os"\n\nfunc main() {}\n'),
        ("go not with cgo's C", "m.go", 'package main\n\n// #include <stdio.h>\nimport "C"\n\nimport "fmt"\n', 'import "os"',
         'package main\n\n// #include <stdio.h>\nimport "C"\n\nimport "fmt"\nimport "os"\n'),
        ("go above a ) that closes the last spec's line", "m.go", 'package main\n\nimport (\n\t"fmt"\n\t"os")\n', '"zz"',
         'package main\n\nimport (\n\t"fmt"\n\t"zz"\n\t"os")\n'),
        ("go a comment over the next spec", "m.go", 'package main\n\nimport (\n\t"fmt"\n\t// for os\n\t"os"\n)\n', '"io"',
         'package main\n\nimport (\n\t"fmt"\n\t"io"\n\t// for os\n\t"os"\n)\n'),
        ("js packages", "m.js", js, 'import b from "b";',
         'import a from "a";\nimport b from "b";\nimport c from "c";\n\nimport x from "./x";\nimport z from "./z";\n\nf();\n'),
        ("js relative paths", "m.js", js, 'import y from "./y";',
         'import a from "a";\nimport c from "c";\n\nimport x from "./x";\nimport y from "./y";\nimport z from "./z";\n\nf();\n'),
        ("js a parent directory", "m.js", js, 'import p from "../p";',
         'import a from "a";\nimport c from "c";\n\nimport p from "../p";\nimport x from "./x";\nimport z from "./z";\n\nf();\n'),
        ("js requires", "m.js", cjs, "const os = require('os');",
         "const fs = require('fs');\nconst os = require('os');\nconst path = require('path');\n\nconst a = require('./a');\n"),
        ("js a relative require", "m.js", cjs, "const b = require('./b');",
         "const fs = require('fs');\nconst path = require('path');\n\nconst a = require('./a');\nconst b = require('./b');\n"),
        ("js a require with requires", "m.js", mixed, "const c = require('c');",
         'import a from "a";\n\nconst b = require("b");\nconst c = require(\'c\');\nconst d = require("d");\n'),
        ("js an import with imports", "m.js", mixed, 'import z from "z";',
         'import a from "a";\nimport z from "z";\n\nconst b = require("b");\nconst d = require("d");\n'),
        ("ts a type import", "m.ts", 'import { A } from "a";\nimport { C } from "c";\n', 'import type { B } from "b";',
         'import { A } from "a";\nimport type { B } from "b";\nimport { C } from "c";\n'),
        ("java a shared package", "A.java", java, "import java.util.HashMap;",
         java.replace("import java.util.List;", "import java.util.HashMap;\nimport java.util.List;")),
        ("java the longest shared package", "A.java", java, "import org.junit.Before;",
         java.replace("import org.junit.Test;", "import org.junit.Before;\nimport org.junit.Test;")),
        ("java static with static", "A.java", java, "import static org.junit.Assert.assertTrue;",
         java.replace("assertEquals;", "assertEquals;\nimport static org.junit.Assert.assertTrue;")),
        ("java static, no shared package", "A.java", java, "import static java.util.Collections.sort;",
         java.replace("import static org", "import static java.util.Collections.sort;\nimport static org")),
        ("java no shared package, the first group", "A.java", java, "import com.foo.Bar;",
         java.replace("import java.util.List;", "import com.foo.Bar;\nimport java.util.List;")),
        ("rb require", "m.rb", rb, "require 'pp'",
         "require 'json'\nrequire 'pp'\nrequire 'set'\n\nrequire_relative 'a'\nrequire_relative 'c'\n"),
        ("rb require_relative", "m.rb", rb, "require_relative 'b'",
         "require 'json'\nrequire 'set'\n\nrequire_relative 'a'\nrequire_relative 'b'\nrequire_relative 'c'\n"),
    ]
    for label, name, source, text, expected in cases:
        _exact(f"add_import in its group ({label})", _edit_result(name, source, lambda a, t=text: a.add_import(t)), expected)

    # A file without imports gets its first one after the preamble, as
    # before, and an import already there is not added again.
    _exact("add_import in its group (no imports yet)",
           _edit_result("m.py", '"""Doc."""\n\nx = 1\n', lambda a: a.add_import("import os")),
           '"""Doc."""\n\nimport os\n\nx = 1\n')
    _exact("add_import in its group (already there)",
           _edit_result("m.py", py, lambda a: a.add_import("import sys")), py)


def test_final_import_name_order():
    print("\n═══ add_import_name puts a name at its sorted place in sorted names ═══")

    # Names in plain (case-sensitive) order, or else in isort's and ruff's
    # order by type (CONSTANT_CASE, then CamelCase, then the rest), get the
    # new one at its place in that order, an alias sorting by its name; one
    # name counts as sorted in plain order. Other names get it at the end,
    # as before. The list keeps its layout.
    # (label, file name, source, module, name, expected file text)
    by_type = "from m import TYPE_CHECKING, Any, cast\n"
    cases = [
        ("py one name per line (reported)", "m.py", "from x import (\n    alpha,\n    gamma,\n)\n", "x", "beta",
         "from x import (\n    alpha,\n    beta,\n    gamma,\n)\n"),
        ("py first, one name per line", "m.py", "from x import (\n    b,\n    c,\n)\n", "x", "a",
         "from x import (\n    a,\n    b,\n    c,\n)\n"),
        ("py without a trailing comma", "m.py", "from x import (\n    a,\n    c\n)\n", "x", "b",
         "from x import (\n    a,\n    b,\n    c\n)\n"),
        ("py above the comment over the next name", "m.py", "from x import (\n    a,\n    # about c\n    c,\n)\n", "x", "b",
         "from x import (\n    a,\n    b,\n    # about c\n    c,\n)\n"),
        ("py below a comment ending a name's line", "m.py", "from x import (\n    a,  # A\n    c,  # C\n)\n", "x", "b",
         "from x import (\n    a,  # A\n    b,\n    c,  # C\n)\n"),
        ("py inline", "m.py", "from x import a, c\n", "x", "b", "from x import a, b, c\n"),
        ("py inline, first", "m.py", "from x import b, c\n", "x", "a", "from x import a, b, c\n"),
        ("py inline in parentheses", "m.py", "from x import (a, c)\n", "x", "b", "from x import (a, b, c)\n"),
        ("py aligned under the (", "m.py", "from x import (a,\n               c)\n", "x", "b",
         "from x import (a,\n               b,\n               c)\n"),
        ("py after a backslash continuation", "m.py", "from x import a, \\\n    c\n", "x", "b",
         "from x import a, \\\n    b, c\n"),
        ("py a new alias sorts by its name", "m.py", "from x import (\n    a as z,\n    c,\n)\n", "x", "b as y",
         "from x import (\n    a as z,\n    b as y,\n    c,\n)\n"),
        ("py an alias sorts by its name", "m.py", "from x import b as z, c\n", "x", "a", "from x import a, b as z, c\n"),
        ("py order by type, a class", "m.py", by_type, "m", "Dict", "from m import TYPE_CHECKING, Any, Dict, cast\n"),
        ("py order by type, a constant", "m.py", by_type, "m", "MAX", "from m import MAX, TYPE_CHECKING, Any, cast\n"),
        ("py order by type, the rest", "m.py", by_type, "m", "bar", "from m import TYPE_CHECKING, Any, bar, cast\n"),
        ("py plain order first", "m.py", "from typing import Any, Dict\n", "typing", "TYPE_CHECKING",
         "from typing import Any, Dict, TYPE_CHECKING\n"),
        ("py one name", "m.py", "from x import b\n", "x", "a", "from x import a, b\n"),
        ("py one name, plain order", "m.py", "from typing import Any\n", "typing", "TYPE_CHECKING",
         "from typing import Any, TYPE_CHECKING\n"),
        ("py unsorted names", "m.py", "from x import c, a\n", "x", "b", "from x import c, a, b\n"),
        ("py unsorted names one per line", "m.py", "from x import (\n    c,\n    a,\n)\n", "x", "b",
         "from x import (\n    c,\n    a,\n    b,\n)\n"),
        ("js inline", "m.js", 'import { a, c } from "m";\n', "m", "b", 'import { a, b, c } from "m";\n'),
        ("js one name per line", "m.js", 'import {\n  a,\n  c,\n} from "m";\n', "m", "b",
         'import {\n  a,\n  b,\n  c,\n} from "m";\n'),
        ("js below a comment ending a name's line", "m.js", 'import {\n  a, // A\n  c, // C\n} from "m";\n', "m", "b",
         'import {\n  a, // A\n  b,\n  c, // C\n} from "m";\n'),
        ("js first", "m.js", 'import { b, c } from "m";\n', "m", "a", 'import { a, b, c } from "m";\n'),
        ("js with a default import", "m.js", 'import D, { a, c } from "m";\n', "m", "b", 'import D, { a, b, c } from "m";\n'),
        ("js an alias sorts by its name", "m.js", 'import { a as z, c } from "m";\n', "m", "b",
         'import { a as z, b, c } from "m";\n'),
        ("ts type-only names", "m.ts", 'import {\n  type A,\n  c,\n} from "m";\n', "m", "type B",
         'import {\n  type A,\n  type B,\n  c,\n} from "m";\n'),
        ("ts a type import", "m.ts", 'import type { A, C } from "m";\n', "m", "B", 'import type { A, B, C } from "m";\n'),
        ("js order by type", "m.js", 'import { FOO, Bar, baz } from "m";\n', "m", "Qux",
         'import { FOO, Bar, Qux, baz } from "m";\n'),
        ("js unsorted names", "m.js", 'import { c, a } from "m";\n', "m", "b", 'import { c, a, b } from "m";\n'),
    ]
    for label, name, source, module, new, expected in cases:
        _exact(f"add_import_name in order ({label})",
               _edit_result(name, source, lambda a, m=module, n=new: a.add_import_name(m, n)), expected)


def test_final_import_directives():
    print("\n═══ add_import keeps next-line directives, cgo preambles and Go specs valid ═══")

    # A comment heading a group stays above a new first import, but a
    # directive for the next line right above the first import (a
    # @ts-ignore, eslint-disable-next-line, NOLINTNEXTLINE, a Go //nolint)
    # stays on that import. cgo's preamble stays right above import "C".
    # A new `from __future__` import goes after the module docstring when
    # code comes before the first import. A Go spec given without `import`
    # gets the keyword when there is no block to put it in, and a block on
    # one line takes it inline.
    # (label, file name, source, import text, expected file text)
    cases = [
        ("ts a @ts-ignore over the first import (reported)", "m.ts",
         '// @ts-ignore\nimport foo from "untyped";\nimport bar from "z";\n', 'import a from "a";',
         'import a from "a";\n// @ts-ignore\nimport foo from "untyped";\nimport bar from "z";\n'),
        ("js an eslint-disable-next-line (reported)", "m.js",
         '// eslint-disable-next-line import/no-unresolved\nimport b from "b";\nimport c from "c";\n', 'import a from "a";',
         'import a from "a";\n// eslint-disable-next-line import/no-unresolved\nimport b from "b";\nimport c from "c";\n'),
        ("cpp a NOLINTNEXTLINE (reported)", "m.cpp",
         "// NOLINTNEXTLINE(build/include)\n#include <b.h>\n#include <c.h>\n", "#include <a.h>",
         "#include <a.h>\n// NOLINTNEXTLINE(build/include)\n#include <b.h>\n#include <c.h>\n"),
        ("ts a heading comment above the directive stays first", "m.ts",
         '// Packages\n// @ts-expect-error\nimport foo from "untyped";\n', 'import a from "a";',
         '// Packages\nimport a from "a";\n// @ts-expect-error\nimport foo from "untyped";\n'),
        ("ts a file pragma stays first", "m.ts", '// @ts-nocheck\nimport b from "b";\n', 'import a from "a";',
         '// @ts-nocheck\nimport a from "a";\nimport b from "b";\n'),
        ("py a pylint disable-next", "m.py", "import os\n\n# pylint: disable-next=import-error\nimport foo\nimport zed\n",
         "import bar", "import os\n\nimport bar\n# pylint: disable-next=import-error\nimport foo\nimport zed\n"),
        ("go a nolint over the first spec", "m.go", 'package p\n\nimport (\n\t//nolint:depguard\n\t"os"\n)\n', '"fmt"',
         'package p\n\nimport (\n\t"fmt"\n\t//nolint:depguard\n\t"os"\n)\n'),
        ("go not between the cgo preamble and import C (reported)", "m.go",
         'package p\n\n// #include <stdio.h>\nimport "C"\nimport "github.com/x/y"\n', 'import "9fans.net/go/acme"',
         'package p\n\n// #include <stdio.h>\nimport "C"\nimport "9fans.net/go/acme"\nimport "github.com/x/y"\n'),
        ("go not between the cgo preamble and C in a block", "m.go",
         'package p\n\nimport (\n\t// #include <stdio.h>\n\t"C"\n\t"github.com/x/y"\n)\n', '"9fans.net/go/acme"',
         'package p\n\nimport (\n\t// #include <stdio.h>\n\t"C"\n\t"9fans.net/go/acme"\n\t"github.com/x/y"\n)\n'),
        ("py a __future__ import after code (reported)", "m.py", '"""Doc."""\nx = 1\n\nimport os\n',
         "from __future__ import annotations",
         '"""Doc."""\n\nfrom __future__ import annotations\n\nx = 1\n\nimport os\n'),
        ("py a __future__ import before a try block", "m.py",
         "try:\n    import json\nexcept ImportError:\n    json = None\nimport os\n", "from __future__ import annotations",
         "from __future__ import annotations\n\ntry:\n    import json\nexcept ImportError:\n    json = None\nimport os\n"),
        ("py a __future__ import after the docstring and comments, still", "m.py",
         '#!/usr/bin/env python\n"""Doc."""\n# imports\nimport os\n', "from __future__ import annotations",
         '#!/usr/bin/env python\n"""Doc."""\n# imports\nfrom __future__ import annotations\nimport os\n'),
        ("go a bare spec after import lines (reported)", "m.go", 'package p\n\nimport "fmt"\nimport "os"\n', '"io"',
         'package p\n\nimport "fmt"\nimport "io"\nimport "os"\n'),
        ("go a bare spec after one import line", "m.go", 'package p\n\nimport "fmt"\n', '"os"',
         'package p\n\nimport "fmt"\nimport "os"\n'),
        ("go an alias spec", "m.go", 'package p\n\nimport "fmt"\n', 'f "path/filepath"',
         'package p\n\nimport "fmt"\nimport f "path/filepath"\n'),
        ("go a bare spec, no imports yet", "m.go", "package p\n\nfunc main() {}\n", '"os"',
         'package p\n\nimport "os"\n\nfunc main() {}\n'),
        ("go a bare spec already there", "m.go", 'package p\n\nimport "fmt"\n', '"fmt"', 'package p\n\nimport "fmt"\n'),
        ("go a block on one line (reported)", "m.go", 'package p\n\nimport ("fmt"; "os")\n', '"io"',
         'package p\n\nimport ("fmt"; "io"; "os")\n'),
        ("go a block on one line, last", "m.go", 'package p\n\nimport ("fmt"; "os")\n', 'import "sync"',
         'package p\n\nimport ("fmt"; "os"; "sync")\n'),
        ("go an empty block on one line", "m.go", "package p\n\nimport ()\n", '"fmt"', 'package p\n\nimport ("fmt")\n'),
    ]
    for label, name, source, text, expected in cases:
        _exact(f"add_import directives ({label})", _edit_result(name, source, lambda a, t=text: a.add_import(t)), expected)

    # add_import_name follows the same rule: a comment heading the names
    # stays first, a directive stays on the name below it.
    # (label, file name, source, module, name, expected file text)
    names = [
        ("py a comment heading the names (reported)", "m.py", "from x import (\n    # first\n    beta,\n    gamma,\n)\n",
         "x", "alpha", "from x import (\n    # first\n    alpha,\n    beta,\n    gamma,\n)\n"),
        ("ts a comment heading the names (reported)", "m.ts", 'import {\n  // types\n  B,\n  C,\n} from "m";\n', "m", "A",
         'import {\n  // types\n  A,\n  B,\n  C,\n} from "m";\n'),
        ("ts a directive over the first name", "m.ts", 'import {\n  // @ts-ignore\n  B,\n  C,\n} from "m";\n', "m", "A",
         'import {\n  A,\n  // @ts-ignore\n  B,\n  C,\n} from "m";\n'),
        ("py a comment over a later name, still", "m.py", "from x import (\n    a,\n    # about c\n    c,\n)\n", "x", "b",
         "from x import (\n    a,\n    b,\n    # about c\n    c,\n)\n"),
    ]
    for label, name, source, module, new, expected in names:
        _exact(f"add_import_name directives ({label})",
               _edit_result(name, source, lambda a, m=module, n=new: a.add_import_name(m, n)), expected)


def test_final_parameter_order():
    print("\n═══ add_parameter keeps Ruby's parameter order and C/C++ variadic forms ═══")

    # Ruby orders parameters: required, optional, the splat, required
    # again, keywords, `**opts`, `&blk`. At the end, a new parameter goes
    # before those that must come after its kind; at the start, first.
    # A GNU named variadic macro parameter (`args...`) and the old C++
    # `int a...` keep their `...` last.
    # (label, file name, source, target, parameter, position, expected file text)
    cases = [
        ("rb a positional parameter before keyword ones (reported)", "m.rb", "def f(a, k: 1, &blk)\nend\n", "f", "b", "end",
         "def f(a, b, k: 1, &blk)\nend\n"),
        ("rb before a required keyword (reported)", "m.rb", "def f(a, k:)\nend\n", "f", "b", "end", "def f(a, b, k:)\nend\n"),
        ("rb an optional parameter before the splat (reported)", "m.rb", "def f(a, *r)\nend\n", "f", "b = 1", "end",
         "def f(a, b = 1, *r)\nend\n"),
        ("rb a positional parameter after the splat", "m.rb", "def f(a, *r)\nend\n", "f", "b", "end", "def f(a, *r, b)\nend\n"),
        ("rb an optional parameter before those after the splat", "m.rb", "def f(a = 1, *r, z)\nend\n", "f", "b = 2", "end",
         "def f(a = 1, b = 2, *r, z)\nend\n"),
        ("rb an optional parameter after optional ones", "m.rb", "def f(a, b = 1)\nend\n", "f", "c = 2", "end",
         "def f(a, b = 1, c = 2)\nend\n"),
        ("rb an optional parameter before a required one after it", "m.rb", "def f(a = 1, b)\nend\n", "f", "c = 2", "end",
         "def f(a = 1, c = 2, b)\nend\n"),
        ("rb a splat before keyword ones", "m.rb", "def f(a, k: 1)\nend\n", "f", "*r", "end", "def f(a, *r, k: 1)\nend\n"),
        ("rb a destructured parameter before keyword ones", "m.rb", "def f(a, k: 1)\nend\n", "f", "(x, y)", "end",
         "def f(a, (x, y), k: 1)\nend\n"),
        ("rb before **nil", "m.rb", "def f(a, **nil)\nend\n", "f", "b", "end", "def f(a, b, **nil)\nend\n"),
        ("rb a keyword parameter before **opts and &blk", "m.rb", "def f(a, **o, &b)\nend\n", "f", "k: 1", "end",
         "def f(a, k: 1, **o, &b)\nend\n"),
        ("rb a keyword parameter after keyword ones", "m.rb", "def f(a, k: 1)\nend\n", "f", "j: 2", "end",
         "def f(a, k: 1, j: 2)\nend\n"),
        ("rb **opts before &blk", "m.rb", "def f(a, &b)\nend\n", "f", "**o", "end", "def f(a, **o, &b)\nend\n"),
        ("rb &blk last", "m.rb", "def f(a, k: 1)\nend\n", "f", "&blk", "end", "def f(a, k: 1, &blk)\nend\n"),
        ("rb one per line", "m.rb", "def f(\n  a,\n  k: 1\n)\nend\n", "f", "b", "end", "def f(\n  a,\n  b,\n  k: 1\n)\nend\n"),
        ("rb at the start", "m.rb", "def f(a, k: 1)\nend\n", "f", "z", "start", "def f(z, a, k: 1)\nend\n"),
        ("c a GNU named variadic macro (reported)", "m.c", "#define M(a, args...) a\n", "M", "b", "end",
         "#define M(a, b, args...) a\n"),
        ("c only a named variadic macro parameter", "m.c", "#define M(args...) 0\n", "M", "b", "end",
         "#define M(b, args...) 0\n"),
        ("c a named variadic macro, at the start", "m.c", "#define M(a, args...) a\n", "M", "z", "start",
         "#define M(z, a, args...) a\n"),
        ("c a variadic macro, still", "m.c", "#define M(a, ...) a\n", "M", "b", "end", "#define M(a, b, ...) a\n"),
        ("cpp the old variadic form (reported)", "m.cpp", "int g(int a...) { return 0; }\n", "g", "int b", "end",
         "int g(int a, int b...) { return 0; }\n"),
        ("cpp the old variadic form with a space", "m.cpp", "int g(int a ...);\n", "g", "int b", "end",
         "int g(int a, int b ...);\n"),
        ("cpp an unnamed parameter before the ..., still", "m.cpp", "void f(int...);\n", "f", "int b", "end",
         "void f(int b, int...);\n"),
        ("cpp the old variadic form, at the start", "m.cpp", "int g(int a...);\n", "g", "int z", "start",
         "int g(int z, int a...);\n"),
        ("cpp a parameter pack, still", "m.cpp", "template <class... Ts> void f(int a, Ts... xs);\n", "f", "int b", "end",
         "template <class... Ts> void f(int a, int b, Ts... xs);\n"),
        ("cpp a pack written like the old form in a template keeps its place", "m.cpp",
         "template <class... Ts> void f(Ts a...);\n", "f", "int b", "end", "template <class... Ts> void f(int b, Ts a...);\n"),
    ]
    for label, name, source, target, parameter, position, expected in cases:
        _exact(f"add_parameter order ({label})",
               _edit_result(name, source, lambda a, t=target, p=parameter, w=position: a.add_parameter(t, p, w)), expected)


def test_final_cpp_method_sections():
    print("\n═══ add_method finds C++ methods in #ifdef blocks and indents moved labels ═══")

    # A method inside an #if/#ifdef block (either branch) counts as the
    # class's last method: the new one goes after the block's #endif, in
    # that section. An access label moved off the method's line is indented
    # like the class's other labels (at the class's indentation without any).
    # (label, file name, source, class, content, expected file text)
    cases = [
        ("a method declared in an #ifdef (reported)", "m.cpp",
         "class Box {\npublic:\n#ifdef X\n    void h();\n#endif\nprivate:\n    int v;\n};\n", "Box", "void f();",
         "class Box {\npublic:\n#ifdef X\n    void h();\n#endif\n\n    void f();\nprivate:\n    int v;\n};\n"),
        ("a method defined in an #ifdef (reported)", "m.cpp",
         "class A {\npublic:\n#ifdef X\n    void g() {}\n#endif\nprivate:\n    int v;\n};\n", "A", "void k() {}",
         "class A {\npublic:\n#ifdef X\n    void g() {}\n#endif\n\n    void k() {}\nprivate:\n    int v;\n};\n"),
        ("a method in an #else branch", "m.cpp",
         "class A {\npublic:\n#ifdef X\n    int x;\n#else\n    void g() {}\n#endif\nprivate:\n    int v;\n};\n", "A", "void k() {}",
         "class A {\npublic:\n#ifdef X\n    int x;\n#else\n    void g() {}\n#endif\n\n    void k() {}\nprivate:\n    int v;\n};\n"),
        ("nested #if blocks", "m.cpp",
         "class A {\npublic:\n#if A\n#ifdef B\n    void g();\n#endif\n#endif\nprivate:\n    int v;\n};\n", "A", "void k();",
         "class A {\npublic:\n#if A\n#ifdef B\n    void g();\n#endif\n#endif\n\n    void k();\nprivate:\n    int v;\n};\n"),
        ("an #ifdef of fields after the method, still", "m.cpp",
         "class A {\npublic:\n    void g() {}\n#ifdef X\n    int x;\n#endif\nprivate:\n    int v;\n};\n", "A", "void k() {}",
         "class A {\npublic:\n    void g() {}\n\n    void k() {}\n#ifdef X\n    int x;\n#endif\nprivate:\n    int v;\n};\n"),
        ("a label moved off the method's line (reported)", "m.cpp",
         "class A {\npublic:\n    void g() {} private:\n    int v;\n};\n", "A", "void k() {}",
         "class A {\npublic:\n    void g() {}\n\n    void k() {}\nprivate:\n    int v;\n};\n"),
        ("a label moved off the method's line, labels indented", "m.cpp",
         "class A {\n  public:\n    void g() {} private:\n    int v;\n};\n", "A", "void k() {}",
         "class A {\n  public:\n    void g() {}\n\n    void k() {}\n  private:\n    int v;\n};\n"),
        ("a label moved off the method's line, no other label", "m.cpp",
         "struct A {\n    void g() {} private:\n    int v;\n};\n", "A", "void k() {}",
         "struct A {\n    void g() {}\n\n    void k() {}\nprivate:\n    int v;\n};\n"),
        ("a field moved off the method's line, still", "m.cpp",
         "class A {\npublic:\n    void g() {} int w;\nprivate:\n    int v;\n};\n", "A", "void k() {}",
         "class A {\npublic:\n    void g() {}\n\n    void k() {}\n    int w;\nprivate:\n    int v;\n};\n"),
    ]
    for label, name, source, cls, content, expected in cases:
        _exact(f"add_method C++ sections ({label})",
               _edit_result(name, source, lambda a, c=cls, t=content: a.add_method(c, t)), expected)


def test_final_ruby_clause_layout():
    print("\n═══ replace_function_body rebuilds Ruby clauses that share lines ═══")

    # When the body of a Ruby method with rescue, else or ensure clauses
    # is rebuilt over lines of its own, the clauses are too when they
    # share a line with their code or the `end`: each clause's header,
    # each of its statements and the `end` on a line of their own. Clauses
    # laid out that way already stay as they are.
    # (label, source, target, content, expected file text)
    cases = [
        ("a one-line method with rescue (reported)", "def f; x; rescue; y; end\n", "f", "1",
         "def f\n  1\nrescue\n  y\nend\n"),
        ("a clause on the line of the code (reported)", "def f\n  x; rescue; y\nend\n", "f", "1",
         "def f\n  1\nrescue\n  y\nend\n"),
        ("rescue with exceptions, else and ensure", "def f; x; rescue A, B => e; log(e); else w; ensure; q; end\n", "f", "1",
         "def f\n  1\nrescue A, B => e\n  log(e)\nelse\n  w\nensure\n  q\nend\n"),
        ("rescue then", "def f; x; rescue A then y; end\n", "f", "1", "def f\n  1\nrescue A\n  y\nend\n"),
        ("several statements in a clause", "def f; x; rescue; y; z; end\n", "f", "1", "def f\n  1\nrescue\n  y\n  z\nend\n"),
        ("an empty rescue clause", "def f; x; rescue; end\n", "f", "1", "def f\n  1\nrescue\nend\n"),
        ("a method in a class", "class K\n  def f; x; rescue; y; end\nend\n", "K.f", "1",
         "class K\n  def f\n    1\n  rescue\n    y\n  end\nend\n"),
        ("a comment ending a clause's line", "def f\n  x; rescue; y # c\nend\n", "f", "1",
         "def f\n  1\nrescue\n  y # c\nend\n"),
        ("several lines of content", "def f; x; rescue; y; end\n", "f", "a = 1\nb(a)",
         "def f\n  a = 1\n  b(a)\nrescue\n  y\nend\n"),
        ("clauses on lines of their own, still", "def f; x\nrescue\n  # why\n  y\n\n  z\nend\n", "f", "1",
         "def f\n  1\nrescue\n  # why\n  y\n\n  z\nend\n"),
    ]
    for label, source, target, content, expected in cases:
        _exact(f"replace_function_body Ruby clauses ({label})",
               _edit_result("m.rb", source, lambda a, t=target, c=content: a.replace_function_body(t, c)), expected)


if __name__ == "__main__":
    test_python()
    test_python_decorated()
    test_javascript()
    test_typescript()
    test_json()
    test_yaml()
    test_yaml_sequence_fixes()
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
    test_ruby()
    test_go()
    test_java()

    test_delete_symbol_leading_comments()
    test_add_top_level_position()
    test_import_names_jsts()
    test_delete_key_jsts()
    test_closure_addressing()
    test_in_body_family()
    test_merged_apis()
    test_ast_reader()
    test_tool_schemas()
    test_syntax_guard()
    test_line_endings()
    test_replace_signature_indentation()
    test_add_key_jsts()
    test_add_key_duplicates()
    test_add_key_layout()
    test_java_signature_annotations()
    test_comment_and_parameter_validation()
    test_body_insert_placement()
    test_exported_symbols()
    test_class_member_layout()
    test_decorator_leading_comments()
    test_docs_name_real_tools()
    test_config_path_lookup()
    test_add_key_config_shapes()
    test_content_line_breaks()
    test_json_plus_exponents()
    test_member_layout_followups()
    test_config_key_followups()
    test_insert_before_leading_comments()
    test_ts_abstract_classes()
    test_delete_symbol_separators()
    test_interface_indentation()
    test_js_ts_symbol_kinds()
    test_config_quoted_paths()
    test_config_inline_entries()
    test_yaml_keys_without_value()
    test_append_to_array_layout()
    test_indentation_whitespace()
    test_leading_comments_in_strings()
    test_ts_ambiguous_names()
    test_ts_kind_tool_followups()
    test_yaml_explicit_keys()
    test_symbols_sharing_a_line()
    test_bodies_sharing_a_line()
    test_cpp_templates()
    test_sibling_spacing()
    test_reindent_string_literals()
    test_remove_from_array_lines()
    test_parameter_lines()
    test_interface_as_written()
    test_depth_refusals()
    test_review_followups()
    test_read_symbol_round_trips()
    test_ruby_embedded_documents()
    test_symbol_discovery()
    test_deeper_comments()
    test_go_grouped_parameters()
    test_byte_order_mark()
    test_lone_surrogate()
    test_python_list_append()
    test_final_review_followups()
    test_overloaded_targets()
    test_overload_groups()
    test_keyword_targets()
    test_listed_targets_everywhere()
    test_listed_data()
    test_depths_agree()
    test_js_trailing_comments()
    test_find_references_line_order()
    test_config_whole_symbol_tools()
    test_replace_value_variables()
    test_first_import_placement()
    test_destructured_parameters()
    test_parameter_followups()
    test_final_newline_state()
    test_text_encodings()
    test_layout_followups()
    test_yaml_only_item()
    test_ruby_attached_lines()
    test_comments_ending_code()
    test_target_resolution_followups()
    test_body_snippets()
    test_content_layout()
    test_lists_docstrings_bodies()
    test_snippet_layout_followups()
    test_final_docstring_literals()
    test_final_keyword_only_parameters()
    test_final_last_parameters()
    test_final_c_variadic_parameters()
    test_final_same_line_comments()
    test_final_ruby_method_clauses()
    test_final_cpp_method_access()
    test_final_import_groups()
    test_final_import_name_order()
    test_final_import_directives()
    test_final_parameter_order()
    test_final_cpp_method_sections()
    test_final_ruby_clause_layout()

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
