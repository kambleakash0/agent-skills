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
    check("add_method: closing brace intact", result, "}")
    # Verify blank line before closing brace
    lines = result.splitlines()
    closing_idx = next(
        i for i in reversed(range(len(lines))) if lines[i].strip() == "}"
    )
    check(
        "add_method: blank line before closing brace",
        lines[closing_idx - 1].strip(),
        "",
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
            ("at line 17, column 2 (missing '}')",),
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
            ("at line 27, column 2 (missing '}')",),
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
    # Such a file still counts as clean (json accepts it), so a later
    # broken edit is refused, at json's position.
    message = _refusal(lambda: Applier(path).replace_value("a", "[1,"))
    check("json with + exponents: broken edit refused", message,
          "Edit refused: the result would have a syntax error at line 2, column 11 (Expecting value)")
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
            "SIZE = 1\n\nclass LRUCache:\n",
        ),
        (
            "py",
            "insert_sibling after",
            lambda a: a.insert_sibling("LRUCache", "def after():\n    pass", "after"),
            "        return self.items.get(key)\n\ndef after():\n    pass\n",
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
    test_docs_name_real_tools()

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
