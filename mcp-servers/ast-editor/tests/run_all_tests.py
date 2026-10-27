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
    app = Applier(ts_path)
    app.add_import_name("other", "extra")
    result = read_file(ts_path)
    check(
        "ts add_import_name: works with default+named import",
        result,
        "{ named, extra }",
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
        "schema: server instructions are at most 1500 characters",
        "PASS" if size <= 1500 else f"FAIL: {size} characters",
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
            ("at line 9, column 12 (missing ')')",),
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
        check("py PEP 696 plus a real error: refused at the real error", message, "syntax error at line 10, column ")
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
            "        return self.items.get(key)\n\ndef helper():\n    return 1\n",
        ),
        (
            "py",
            "add_top_level top",
            lambda a: a.add_top_level("SIZE = 1", position="top"),
            "SIZE = 1\n\nclass LRUCache:\n",
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

    # A mixed file is written back in its majority style.
    path = _write_temp("test_mixed.py", "a = 1\r\nb = 2\r\nc = 3\n")
    Applier(path).add_top_level("d = 4")
    check("mixed endings: normalised to the majority (CRLF)", _read_bytes(path).decode("utf-8"), "a = 1\r\nb = 2\r\nc = 3\r\n\r\nd = 4\r\n")
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
         lambda a: a.add_top_level("def g():\n    pass\n\n"), "a = 1\n\ndef g():\n    pass\n"),
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
        "class Svc (line 4)\n  method Svc.run (line 6)",
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
           _read_result("d.py", dc, lambda a: a.list_symbols()), "class D (line 5)")
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
        ("cpp add_method: after a trailing access label", "c.cpp",
         "class K {\n  void a() {}\npublic:\n};\n", lambda a: a.add_method("K", "void b() {}"),
         "class K {\n  void a() {}\npublic:\n  void b() {}\n};\n"),
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
           "class O (line 1)\n  class O.I (line 2)\n  method O.m (line 6)")


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
           "class A (line 1)\n  method A.m (line 5)\n  method A.n (line 7)\n"
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

    # Functions bound to one name by const/let/var, exported or not; other
    # values, and declarations of several names, are not functions.
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
        "function ex (line 11)"
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

    # One function among several names is not listed, but still targetable.
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
        ("block on a last line with no newline", "b: 1\na:", "a", "k: 1\nm: 2", "b: 1\na:\n  k: 1\n  m: 2\n"),
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
    print("\n═══ TS: a name that is both a type and a value is refused ═══")

    zod = (
        "import { z } from 'zod';\n\n"
        "export const User = z.object({ name: z.string() });\n\n"
        "/** The user type. */\n"
        "export type User = z.infer<typeof User>;\n"
    )
    zod_refusal = (
        "REFUSED: 'User' is ambiguous: `const User` (line 3) and `type User` (line 6) "
        "both declare it, and a target cannot say which one it means. Edit these "
        "declarations with your normal edit tool."
    )
    _exact("zod pattern: list_symbols lists the type",
           _read_result("amb.ts", zod, lambda a: a.list_symbols()), "type User (line 6)")
    _exact("zod pattern: read_symbol is refused (reported)",
           _read_result("amb.ts", zod, lambda a: a.read_symbol("User")), zod_refusal)
    _exact("zod pattern: delete_symbol is refused, the file untouched (reported)",
           _edit_result("amb.ts", zod, lambda a: a.delete_symbol("User")), zod_refusal)
    _exact("zod pattern in .tsx: replace_function is refused",
           _edit_result("amb.tsx", zod, lambda a: a.replace_function("User", "export type User = {};")),
           zod_refusal)

    props = "export interface Props {\n  a: number;\n}\nexport const Props = (p: Props) => p.a;\n"
    _exact("interface and function: read_symbol is refused",
           _read_result("amb.ts", props, lambda a: a.read_symbol("Props")),
           "REFUSED: 'Props' is ambiguous: `interface Props` (line 1) and `const Props` (line 4) "
           "both declare it, and a target cannot say which one it means. Edit these "
           "declarations with your normal edit tool.")
    _exact("three declarations are all named",
           _read_result("amb.ts", "const U = 1;\ntype U = number;\ninterface U {}\n",
                        lambda a: a.read_symbol("U")),
           "REFUSED: 'U' is ambiguous: `const U` (line 1), `type U` (line 2) and `interface U` "
           "(line 3) all declare it, and a target cannot say which one it means. Edit these "
           "declarations with your normal edit tool.")
    _exact("declare const and type: refused",
           _read_result("amb.ts", "declare const X: number;\ntype X = string;\n",
                        lambda a: a.read_symbol("X")).split(" both ")[0],
           "REFUSED: 'X' is ambiguous: `const X` (line 1) and `type X` (line 2)")

    # Not ambiguous: overload signatures, merged interfaces, getter/setter
    # pairs, a same-named local in another scope.
    _exact("function overloads: the implementation",
           _read_result("amb.ts", "export function f(a: string): string;\nexport function f(a: any) { return a; }\n",
                        lambda a: a.read_symbol("f")),
           "export function f(a: any) { return a; }")
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
         lambda a: a.replace_value("a", "3"), "b: 1\n? a\n: 3\n"),
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
    # own names, with or without a template header.
    plain_out = "struct A { int f(); };\n\nint A::f() { return 1; }\n"
    _exact("cpp out-of-line definition: list_symbols",
           read(lambda a: a.list_symbols(), plain_out), "struct A (line 1)\n  method A.f (line 1)\nfunction f (line 3)")
    out = ("template <typename T>\nT Box<T>::get() {\n    return v;\n}\n\n"
           "template <class T> template <class U> U Box<T>::as() { return U(v); }\n")
    _exact("cpp out-of-line template definitions: list_symbols",
           read(lambda a: a.list_symbols(), out), "function get (line 1)\nfunction as (line 6)")
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
         "X = 1\n\nZ = 3\n\nY = 2\n"),
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
        ("py, after **kwargs: refused as before", "p.py", "def f(\n    a,\n    **kwargs,\n):\n    pass\n", "f", "*args", "end", None),
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
        if expected is None:
            # No reordering: what goes after **kwargs is refused as before.
            _refused(f"add_parameter ({label})", result, "syntax error")
        else:
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
         "x = 1\n\n@staticmethod\ndef m():\n    return 1\n"),
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
    name targets: read_symbol finds it, and finds the symbol at the listed
    line."""
    listed = _read_result(name, source, lambda a: a.list_symbols())

    def found_at(a, target):
        node = a.parser.find_node_by_name(target)
        return "no line" if node is None else str(a._symbol_span(node)[0].start_point[0] + 1)

    for line in listed.splitlines():
        entry, number = line.split(" (line ")
        target = " ".join(entry.split()[1:])
        result = _read_result(name, source, lambda a: a.read_symbol(target))
        at = _read_result(name, source, lambda a: found_at(a, target))
        if result.startswith("REFUSED"):
            result = "FAIL: " + result
        elif at != number.rstrip(")"):
            result = f"FAIL: listed at line {number.rstrip(')')}, found at {at}"
        else:
            result = "PASS"
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
        # A struct is found and listed rather than a typedef of its name,
        # and a Java method rather than the field it shares its name with.
        ("c typedef before its struct", "k.c",
         "typedef struct Node Node;\n\nstruct Node {\n    Node *next;\n};\n",
         "struct Node (line 3)\n  field Node.next (line 4)",
         [("Node", "struct Node {\n    Node *next;\n};", ("struct Node", "struct Node {\n    Node *next;\n};"),
           "typedef struct Node Node;\n")]),
        ("java field and accessor sharing a name", "K.java",
         "class A {\n    private int size;\n\n    int size() {\n        return size;\n    }\n}\n",
         "class A (line 1)\n  method A.size (line 4)",
         [("A.size", "int size() {\n        return size;\n    }", "int size()", "class A {\n    private int size;\n}\n")]),
        ("cpp methods declared in their class", "k.cpp",
         "class A {\npublic:\n    A();\n    int g();\n    virtual void v() = 0;\n};\n\nint A::g() { return 1; }\n",
         "class A (line 1)\n  method A.A (line 3)\n  method A.g (line 4)\n  method A.v (line 5)\nfunction g (line 8)",
         [("A.A", "A();", "A()", "class A {\npublic:\n    int g();\n    virtual void v() = 0;\n};\n\nint A::g() { return 1; }\n"),
          ("A.g", "int g();", "int g()", "class A {\npublic:\n    A();\n    virtual void v() = 0;\n};\n\nint A::g() { return 1; }\n"),
          ("A.v", "virtual void v() = 0;", "virtual void v() = 0",
           "class A {\npublic:\n    A();\n    int g();\n};\n\nint A::g() { return 1; }\n"),
          ("g", "int A::g() { return 1; }", "int A::g()",
           "class A {\npublic:\n    A();\n    int g();\n    virtual void v() = 0;\n};\n")]),
        # TS: an overload signature yields to the implementation, and a
        # function declared without one (`declare function`) is a target.
        # Known limitation, pinned so that a change shows: an overload group
        # is not one symbol, so delete_symbol takes the implementation alone
        # (leaving signatures tsc rejects) or the first `declare` signature.
        ("ts overloads and declared functions", "k.ts",
         "function f(a: string): void;\nfunction f(a: any) {\n  return a;\n}\n"
         "declare function g(x: number): void;\ndeclare function g(x: string): void;\n",
         "function f (line 2)\nfunction g (line 5)",
         [("f", "function f(a: any) {\n  return a;\n}", "function f(a: any)",
           "function f(a: string): void;\ndeclare function g(x: number): void;\ndeclare function g(x: string): void;\n"),
          ("g", "declare function g(x: number): void;", "function g(x: number): void",
           "function f(a: string): void;\nfunction f(a: any) {\n  return a;\n}\ndeclare function g(x: string): void;\n")]),
        ("ts method overloads (listed once, as before)", "k.ts",
         "class K {\n  m(a: string): void;\n  m(a: any) {}\n}\n",
         "class K (line 1)\n  method K.m (line 3)",
         [("K.m", "m(a: any) {}", "m(a: any)", "class K {\n  m(a: string): void;\n}\n")]),

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
         [("N", "typedef struct N {\n    int v;\n} N;", ("struct N", "struct N {\n    int v;\n}"),
           "typedef struct {\n    int x;\n} P;\ntypedef int (*cb)(int);\n"),
          ("P", "typedef struct {\n    int x;\n} P;", "a type alias",
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
         "struct A (line 1)\n  field A.n (line 2)\n  field A.N (line 3)\n  type A.T (line 4)\nvariable n (line 6)",
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
         "class A (line 1)\n  class A.B (line 2)\n    method A.B.m (line 3)\n  class A.C (line 6)\n  method A.n (line 10)",
         [("A.C", "@dataclass\n    class C:\n        x: int", ("class C:", "@dataclass\nclass C:\n    x: int"),
           "class A:\n    class B:\n        def m(self):\n            return 1\n\n    def n(self):\n        pass\n")]),
        ("ruby nested modules and classes", "k.rb",
         "module M\n  class A\n    def m\n    end\n\n    private def p\n    end\n  end\n\n  module N\n    def self.s; end\n  end\n\n"
         "  def self.f\n  end\nend\n",
         "module M (line 1)\n  class M.A (line 2)\n    method M.A.m (line 3)\n    method M.A.p (line 6)\n"
         "  module M.N (line 10)\n    method M.N.s (line 11)\n  method M.f (line 14)",
         [("M.A.p", "private def p\n    end", "def p",
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
         "function ~A (line 8)\nfunction operator== (line 11)\nfunction operator const char* (line 13)",
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
         lambda a: a.insert_sibling("M", "#define N 2", "after"), "#define M 1\n\n#define N 2\n\nint g = 1;\n"),
        ("insert_sibling after a macro over two lines", "k.c", "#define F(x) \\\n    ((x) + 1)\nint y;\n",
         lambda a: a.insert_sibling("F", "#define G 2", "after"), "#define F(x) \\\n    ((x) + 1)\n\n#define G 2\n\nint y;\n"),
        ("insert_sibling before a global", "k.c", "#define M 1\nint g = 1;\n",
         lambda a: a.insert_sibling("g", "int h = 2;", "before"), "#define M 1\n\nint h = 2;\n\nint g = 1;\n"),
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
         bom + "import os\ndef f():\n    pass\n"),
        ("go add_import", "k.go", bom + 'package main\n\nimport "os"\n\nfunc f() {}\n',
         lambda a: a.add_import('import "fmt"'),
         bom + 'package main\n\nimport "os"\nimport "fmt"\n\nfunc f() {}\n'),
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
         "class Foo (line 1)\n  method Foo.bar (line 2)\n  function Foo.parse (line 9)",
         [("Foo", None), ("Foo.bar", "bar(): number {\n    return 1;\n  }"), ("Foo.parse", "export function parse() {}"),
          ("Foo.VERSION", "export const VERSION = 1;")]),
        ("ts class and a namespace not exported", "k.ts", ts_class.replace("export namespace", "namespace"),
         "class Foo (line 1)\n  method Foo.bar (line 2)\n  function Foo.parse (line 9)",
         [("Foo.parse", "export function parse() {}")]),
        ("ts enum and namespace (reported)", "k.ts", ts_enum, "enum Color (line 1)\n  function Color.parse (line 3)",
         [("Color", "export enum Color { Red }"),
          ("Color.parse", "export function parse(s: string): Color { return Color.Red; }")]),
        ("ts function and namespace (reported)", "k.ts", ts_function, "function build (line 1)",
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
    # the name targets the first; C++ overloads are listed as before.
    _exact("final review list_symbols (alternatives in #ifdef ... #else)",
           _read_result("k.c", "#ifdef X\nint f(void) { return 1; }\n#else\nint f(void) { return 2; }\n#endif\n",
                        lambda a: a.list_symbols()), "function f (line 2)")
    _exact("final review list_symbols (cpp overloads)",
           _read_result("k.cpp", "void g(int) {}\nvoid g(double) {}\n", lambda a: a.list_symbols()),
           "function g (line 1)\nfunction g (line 2)")

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
           bom + "X = 1\n\ndef f():\n    pass\n")


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
    test_python_list_append()
    test_final_review_followups()

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
