#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import ast
import sys
from pathlib import Path


class PythonFormatter:

    def __init__(self, source_code: str):
        self.source_lines = source_code.splitlines()
        self.tree = ast.parse(source_code)
        self.node_parents = {
            child: parent for parent in ast.walk(self.tree) for child in ast.iter_child_nodes(parent)
        }
        self.disabled_ranges = self._find_disabled_ranges()


    def _find_disabled_ranges(self):
        ranges = []
        in_disabled_block = False
        start_line = 0
        for i, line in enumerate(self.source_lines):
            if "# fmt: off" in line:
                in_disabled_block = True
                start_line = i + 1
            elif "# fmt: on" in line:
                if in_disabled_block:
                    ranges.append((start_line, i + 1))
                in_disabled_block = False
        return ranges


    def _is_in_disabled_range(self, lineno):
        for start, end in self.disabled_ranges:
            if start <= lineno <= end:
                return True
        return False


    def get_node_start_line(self, node):
        if node.decorator_list:
            return node.decorator_list[0].lineno
        return node.lineno


    def is_method(self, node) -> bool:
        return isinstance(self.node_parents.get(node), ast.ClassDef)


    def format(self) -> str:
        nodes = {}
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start_line = self.get_node_start_line(node)
                nodes[start_line] = node

        lines = list(self.source_lines)
        sorted_nodes = sorted(nodes.items(), key=lambda x: x[0], reverse=True)

        for lineno, node in sorted_nodes:
            start_index = lineno - 1
            num_blank_lines = 0

            # Skip formatting if node is inside a "fmt: off" block
            if self._is_in_disabled_range(lineno):
                continue

            if isinstance(node, ast.ClassDef):
                num_blank_lines = 2
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if self.is_method(node):
                    if node.name == "__init__":
                        num_blank_lines = 1
                    else:
                        num_blank_lines = 2
                else:
                    num_blank_lines = 2

            i = start_index - 1
            while i > 0 and not lines[i].strip():
                i -= 1

            if i < 0:  # start of file
                i = -1  # will insert at 0

            # For top-level nodes, we don't want to add spaces if it's the first thing in the file
            # after imports. Let's check if there's anything but imports above.
            is_truly_top_level = i == -1
            if not is_truly_top_level:
                # Count existing blank lines
                existing_blank_lines = 0
                for k in range(start_index - 1, i, -1):
                    if not lines[k].strip():
                        existing_blank_lines += 1

                # Only add lines if there are not enough
                if existing_blank_lines < num_blank_lines:
                    # remove existing blank lines
                    del lines[i + 1 : start_index]
                    # insert new blank lines
                    for _ in range(num_blank_lines):
                        lines.insert(i + 1, "")

        result = "\n".join(line.rstrip() for line in lines)
        if result:
            result = result.strip() + "\n"

        return result


def main():
    parser = argparse.ArgumentParser(description="Python custom formatter.")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()

    for path in args.files:
        try:
            source = path.read_text()
            # Skip empty files
            if not source.strip():
                continue
            formatter = PythonFormatter(source)
            formatted_source = formatter.format()
            path.write_text(formatted_source)
            print(f"Formatted {path}")
        except Exception as e:
            print(f"Could not format {path}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
