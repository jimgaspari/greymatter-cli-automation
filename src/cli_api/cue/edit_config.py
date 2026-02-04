from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Union


def update_tenant_namespaces(config_path: Path, tenant_ns: Union[str, List[str]]) -> Dict[str, Any]:
    """
    Add tenant_ns to config.tenant_namespaces array in config.cue.

    - Additive: does not remove existing entries
    - Idempotent: no duplicate adds
    - Supports: tenant_namespaces: []  OR  tenant_namespaces: ["a"]  OR multiline lists
    """
    step: Dict[str, Any] = {"returncode": 1}

    if isinstance(tenant_ns, list):
        steps = []
        for ns in tenant_ns:
            steps.append(update_tenant_namespaces(config_path, str(ns)))
        # overall rc is 0 if all succeeded
        rc = 0 if all(s.get("returncode", 1) == 0 for s in steps) else 1
        return {"returncode": rc, "steps": steps}
    
    try:
        s = config_path.read_text(encoding="utf-8")
    except Exception as e:
        step["stderr"] = f"Failed to read {config_path}: {e}"
        return step

    tenant_ns = (tenant_ns or "").strip()
    if not tenant_ns:
        step["stderr"] = "tenant namespace is empty"
        return step

    # Match: tenant_namespaces: [ ... ]
    # DOTALL so it works with multiline arrays.
    pat = re.compile(r"(tenant_namespaces\s*:\s*\[)(.*?)(\])", re.DOTALL)

    m = pat.search(s)
    if not m:
        step["stderr"] = "tenant_namespaces array not found in config.cue"
        return step

    prefix, body, suffix = m.group(1), m.group(2), m.group(3)

    # Extract existing quoted string entries (CUE list of strings)
    existing: List[str] = re.findall(r'"([^"]+)"', body)

    if tenant_ns in existing:
        step["stdout"] = f"tenant_namespaces already contains {tenant_ns}"
        step["returncode"] = 0
        return step

    # Decide whether list is single-line or multi-line based on original content
    original_block = m.group(0)
    multiline = "\n" in original_block

    if multiline:
        # Preserve indentation: use indentation of first list item if present,
        # otherwise infer from line containing tenant_namespaces.
        # Find indent from the line that begins tenant_namespaces
        line_start = s.rfind("\n", 0, m.start(1)) + 1
        line = s[line_start : s.find("\n", line_start) if "\n" in s[line_start:] else len(s)]
        base_indent = re.match(r"(\s*)", line).group(1)
        item_indent = base_indent + "  "

        # Clean trailing whitespace in body but keep internal newlines
        body_stripped = body.rstrip()

        # Ensure body ends with newline if it already has items
        if body_stripped.strip() == "":
            new_body = f'\n{item_indent}"{tenant_ns}",\n{base_indent}'
        else:
            # Ensure body ends with newline
            if not body_stripped.endswith("\n"):
                body_stripped += "\n"
            new_body = f'{body_stripped}{item_indent}"{tenant_ns}",\n{base_indent}'

        new_block = f"{prefix}{new_body}{suffix}"
    else:
        # Single-line list
        if existing:
            new_items = existing + [tenant_ns]
        else:
            new_items = [tenant_ns]
        new_list = ", ".join([f'"{x}"' for x in new_items])
        new_block = f"{prefix}{new_list}{suffix}"

    s2 = s[: m.start(0)] + new_block + s[m.end(0) :]

    try:
        config_path.write_text(s2, encoding="utf-8")
    except Exception as e:
        step["stderr"] = f"Failed to write {config_path}: {e}"
        return step

    step["stdout"] = f"Added {tenant_ns} to tenant_namespaces"
    step["returncode"] = 0
    return step

OPEN_BLOCK_RE = re.compile(r"^(\s*)([A-Za-z_]\w*)\s*:\s*\{\s*$")
KEY_RE = re.compile(r"^(\s*)([A-Za-z_]\w*)\s*:\s*(.*?)\s*$")

def _find_matching_brace(lines: List[str], start_idx: int) -> int:
    """Given index of a line that opens a block, return index of its closing brace line."""
    depth = 0
    for i in range(start_idx, len(lines)):
        depth += lines[i].count("{")
        depth -= lines[i].count("}")
        if i > start_idx and depth == 0:
            return i
    raise ValueError("Unbalanced braces in file")

def _find_block_occurrence(lines: List[str], name: str, which: str) -> Optional[int]:
    idxs = []
    for i, line in enumerate(lines):
        m = OPEN_BLOCK_RE.match(line)
        if m and m.group(2) == name:
            idxs.append(i)
    if not idxs:
        return None
    if which == "first":
        return idxs[0]
    if which == "last":
        return idxs[-1]
    raise ValueError("which must be 'first' or 'last'")

def set_deep_path(
    text: str,
    path: str,
    value: str,
    *,
    which_top_level: str = "last",
    indent_unit: str = "\t",
) -> str:
    """
    Set a deep path like 'defaults.edge.oauth2.token_endpoint.timeout' to `value`.
    Creates missing blocks and keys. Targets first/last top-level block if duplicates exist.
    """
    parts = path.split(".")
    if len(parts) < 2:
        raise ValueError("path must be like 'block.key' or deeper")

    lines = text.splitlines()
    top = parts[0]
    rest = parts[1:]

    # Find or create the top-level block
    top_idx = _find_block_occurrence(lines, top, which_top_level)
    if top_idx is None:
        # append new top-level block at end
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"{top}: {{")
        lines.append(f"{indent_unit}}}")
        top_idx = len(lines) - 2  # the line with "{"

    top_end = _find_matching_brace(lines, top_idx)

    # Determine indentation inside top-level block
    top_indent = OPEN_BLOCK_RE.match(lines[top_idx]).group(1)
    cur_block_start = top_idx
    cur_block_end = top_end
    cur_indent = top_indent + indent_unit

    # Walk/create intermediate blocks for all but last key
    for name in rest[:-1]:
        # search for an existing child block inside current block
        child_start = None
        for i in range(cur_block_start + 1, cur_block_end):
            m = OPEN_BLOCK_RE.match(lines[i])
            if m and m.group(2) == name:
                child_start = i
                break

        if child_start is None:
            # create child block right before cur_block_end
            lines.insert(cur_block_end, f"{cur_indent}{name}: {{")
            lines.insert(cur_block_end + 1, f"{cur_indent}{indent_unit}}}")
            # after insertion, closing brace index shifts down by 2
            cur_block_end += 2
            child_start = cur_block_end - 2  # the inserted "{"

        # move into child block
        child_end = _find_matching_brace(lines, child_start)
        cur_block_start, cur_block_end = child_start, child_end
        # update indentation for deeper level
        parent_indent = OPEN_BLOCK_RE.match(lines[cur_block_start]).group(1)
        cur_indent = parent_indent + indent_unit

    # Set (or insert) the final key
    final_key = rest[-1]
    key_line_idx = None
    for i in range(cur_block_start + 1, cur_block_end):
        m = KEY_RE.match(lines[i])
        if m and m.group(2) == final_key:
            key_line_idx = i
            key_indent = m.group(1)
            lines[i] = f"{key_indent}{final_key}: {value}"
            break

    if key_line_idx is None:
        # insert before block close
        lines.insert(cur_block_end, f"{cur_indent}{final_key}: {value}")

    # Preserve trailing newline behavior
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

def set_deep_path_in_file(
    file_path: str | Path,
    path: str,
    value: str,
    *,
    which_top_level: str = "last",
) -> dict:
    p = Path(file_path)
    if not p.exists():
        return {"returncode": 1, "stderr": f"file not found: {p}", "path": str(p)}

    try:
        text = p.read_text(encoding="utf-8")
        updated = set_deep_path(text, path, value, which_top_level=which_top_level)
        p.write_text(updated, encoding="utf-8")
        return {"returncode": 0, "stdout": f"set {path} = {value}", "path": str(p)}
    except Exception as e:
        return {"returncode": 1, "stderr": f"{type(e).__name__}: {e}", "path": str(p)}
