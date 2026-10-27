# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Zero-dependency robust YAML frontmatter parser (ADR-014).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter and markdown body from skill, agent, or doc files.
    Returns (frontmatter_dict, markdown_body).
    """
    if not content or not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    raw_fm = parts[1]
    body = parts[2].lstrip()
    result: Dict[str, Any] = {}
    lines = raw_fm.strip().splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()

            if val in (">-", ">", "|", "|-"):
                buf: List[str] = []
                i += 1
                while i < len(lines) and (
                    lines[i].startswith("  ")
                    or lines[i].startswith("\t")
                    or not lines[i].strip()
                ):
                    if lines[i].strip():
                        buf.append(lines[i].strip())
                    i += 1
                joiner = " " if val in (">-", ">") else "\n"
                result[key] = joiner.join(buf)
                continue
            elif val == "":
                i += 1
                child_list: List[str] = []
                child_dict: Dict[str, Any] = {}
                is_list = False
                is_dict = False
                while i < len(lines) and (
                    lines[i].startswith("  ")
                    or lines[i].startswith("\t")
                    or not lines[i].strip()
                ):
                    cline = lines[i].strip()
                    if not cline:
                        i += 1
                        continue
                    if cline.startswith("- ") and not is_dict:
                        is_list = True
                        child_list.append(cline[2:].strip())
                    elif ":" in cline:
                        is_dict = True
                        ck, cv = cline.split(":", 1)
                        ck = ck.strip()
                        cv = cv.strip()
                        if cv == "":
                            sub_list: List[str] = []
                            j = i + 1
                            while j < len(lines) and (
                                lines[j].startswith("    ")
                                or lines[j].startswith("\t\t")
                                or (lines[j].startswith("  ") and lines[j].strip().startswith("- "))
                            ):
                                scline = lines[j].strip()
                                if scline.startswith("- "):
                                    val_entry = scline[2:].strip()
                                    if (
                                        val_entry.startswith(('"', "'"))
                                        and val_entry.endswith(('"', "'"))
                                        and len(val_entry) >= 2
                                    ):
                                        val_entry = val_entry[1:-1]
                                    sub_list.append(val_entry)
                                j += 1
                            if sub_list:
                                child_dict[ck] = sub_list
                                i = j - 1
                            else:
                                child_dict[ck] = ""
                        elif cv.startswith("[") and cv.endswith("]"):
                            child_dict[ck] = [
                                x.strip().strip("'\"")
                                for x in cv[1:-1].split(",")
                                if x.strip()
                            ]
                        elif cv.lower() == "true":
                            child_dict[ck] = True
                        elif cv.lower() == "false":
                            child_dict[ck] = False
                        elif (
                            cv.startswith(('"', "'"))
                            and cv.endswith(('"', "'"))
                            and len(cv) >= 2
                        ):
                            child_dict[ck] = cv[1:-1]
                        elif cv.isdigit():
                            child_dict[ck] = int(cv)
                        else:
                            child_dict[ck] = cv
                    i += 1

                if is_list:
                    result[key] = child_list
                elif is_dict:
                    result[key] = child_dict
                else:
                    result[key] = ""
                continue
            else:
                if val.lower() == "true":
                    result[key] = True
                elif val.lower() == "false":
                    result[key] = False
                elif (
                    val.startswith(('"', "'"))
                    and val.endswith(('"', "'"))
                    and len(val) >= 2
                ):
                    result[key] = val[1:-1]
                elif val.startswith("[") and val.endswith("]"):
                    inner = val[1:-1].strip()
                    if not inner:
                        result[key] = []
                    else:
                        result[key] = [
                            item.strip().strip("'\"")
                            for item in inner.split(",")
                            if item.strip()
                        ]
                elif val.startswith("{") and val.endswith("}"):
                    inner = val[1:-1].strip()
                    c_dict: Dict[str, Any] = {}
                    if inner:
                        for pair in inner.split(","):
                            if ":" in pair:
                                pk, pv = pair.split(":", 1)
                                pk = pk.strip().strip("'\"")
                                pv = pv.strip().strip("'\"")
                                if pv.lower() == "true":
                                    c_dict[pk] = True
                                elif pv.lower() == "false":
                                    c_dict[pk] = False
                                elif pv.isdigit():
                                    c_dict[pk] = int(pv)
                                else:
                                    c_dict[pk] = pv
                    result[key] = c_dict
                else:
                    result[key] = val
        i += 1

    return result, body
