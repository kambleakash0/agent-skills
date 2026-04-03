import logging
import os

from mcp.server.fastmcp import FastMCP
from ast_editor.applier import Applier, ApplierError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ast-editor")

mcp = FastMCP("AST-Code-Editor")

def _validate_file(file_path: str) -> str | None:
    """Return an error message if file_path is invalid, else None."""
    if not os.path.isabs(file_path):
        return f"file_path must be an absolute path, got: {file_path}"
    if not os.path.isfile(file_path):
        return f"File not found: {file_path}"
    return None

@mcp.tool()
def replace_function(file_path: str, target: str, content: str) -> str:
    """
    Replace an entire function definition (including signature and decorators) with new content.
    Target must be the semantically exact name of the function or class.method.
    Useful for completely modifying a function's arguments and return types.
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("replace_function: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        applier.replace_function(target, content)
        return f"Successfully replaced function '{target}' in {file_path}."
    except Exception as e:
        logger.error("replace_function failed: %s", e)
        return f"Failed to execute AST edit: {str(e)}"

@mcp.tool()
def replace_function_body(file_path: str, target: str, content: str) -> str:
    """
    Replace ONLY the body of a function, preserving its signature.
    Do NOT include the `def func():` line or JS signature inside `content`.
    Target must be the exact name (e.g. 'LRUCache.get').
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("replace_function_body: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        applier.replace_function_body(target, content)
        return f"Successfully replaced body of '{target}' in {file_path}."
    except Exception as e:
        logger.error("replace_function_body failed: %s", e)
        return f"Failed to execute AST edit: {str(e)}"

@mcp.tool()
def add_method(file_path: str, class_target: str, content: str) -> str:
    """
    Add a new method to the end of a class block.
    Class target should be the class name.
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("add_method: class='%s' file='%s'", class_target, file_path)
        applier = Applier(file_path)
        applier.add_method(class_target, content)
        return f"Successfully added method to class '{class_target}' in {file_path}."
    except Exception as e:
        logger.error("add_method failed: %s", e)
        return f"Failed to execute AST edit: {str(e)}"

@mcp.tool()
def delete_node(file_path: str, target: str) -> str:
    """
    Delete an entire function or class definition block identified by target name.
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("delete_node: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        applier.delete_node(target)
        return f"Successfully deleted '{target}' in {file_path}."
    except Exception as e:
        logger.error("delete_node failed: %s", e)
        return f"Failed to execute AST edit: {str(e)}"

@mcp.tool()
def replace_value(file_path: str, target: str, content: str) -> str:
    """
    Used exclusively for Configuration Files (JSON, YAML, TOML).
    Target should be the dotted path to the key (e.g. 'dependencies.mcp' or 'server.port').
    The content will overwrite ONLY the value of the targeted pair.
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("replace_value: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        applier.replace_value(target, content)
        return f"Successfully replaced value at '{target}' in {file_path}."
    except Exception as e:
        logger.error("replace_value failed: %s", e)
        return f"Failed to execute AST config edit: {str(e)}"

def main():
    logger.info("Starting AST Code Editor MCP server")
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
