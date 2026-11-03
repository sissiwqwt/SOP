#!/usr/bin/env python3
"""Step through a SOP-UQ data file in the terminal, one case per Enter.

    python view_data.py train.jsonl
    python view_data.py test/initial_M9.jsonl --start 40

Reads the labeled files and both test files. Standard library only.
"""

import argparse
import json
import os
import re
import shutil
import sys
import textwrap
from pathlib import Path

CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
COMPACT_VALUE = 80
MIN_COLUMN = 6
HEADER_FIELDS = {"case_id", "split", "domain", "status", "failure"}
SECTION_FIELDS = {"inputs", "label", "answer", "p_error", "samples", "trajectory", "history"}
TAG_WIDTH = 8
TAG_STYLES = {"call": "36", "receipt": "32", "final": "1;35", "error": "31", "invalid": "31", "reply": "33"}
MARK_STYLES = {"✓": "32", "✗": "31"}

use_color = False


def paint(text, style):
    return f"\033[{style}m{text}\033[0m" if use_color else text


def heading(title, note=""):
    return "\n" + paint(title, "1;34") + (f"  {paint(note, '2')}" if note else "")


def show(value):
    """One line of plain text for any JSON value."""
    if value is None:
        return "—"
    if isinstance(value, str):
        return CONTROL.sub(" ", value).strip()
    return json.dumps(value, ensure_ascii=False)


def clip(text, limit):
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


def wrapped(text, width, prefix="", plain_prefix=None):
    """Wrap text after a prefix; continuation lines line up under the first."""
    indent = " " * len(prefix if plain_prefix is None else plain_prefix)
    lines = textwrap.wrap(text, max(width - len(indent), 20), break_on_hyphens=False) or [""]
    return [prefix + lines[0]] + [indent + line for line in lines[1:]]


def field_block(mapping, width):
    """Aligned ``key  value`` lines, with long values wrapped."""
    pad = min(max(len(key) for key in mapping), 34)
    lines = []
    for key, value in mapping.items():
        plain = f"  {key:<{pad}}  "
        lines += wrapped(show(value), width, f"  {paint(f'{key:<{pad}}', '2')}  ", plain)
    return lines


def fit_columns(rows, width):
    """Column widths for a table, shrinking the widest until it fits."""
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    while sum(widths) + 2 * len(widths) > width and max(widths) > MIN_COLUMN:
        widths[widths.index(max(widths))] -= 1
    return widths


def answer_table(record, width):
    """Fields by row; label, answer and each sample by column."""
    label, answer = record.get("label"), record.get("answer")
    samples = record.get("samples") or []
    has_label = isinstance(label, dict)
    graded = has_label and answer is not None
    fields = list(label or {})
    for source in [answer, *(s.get("answer") for s in samples)]:
        fields += [key for key in source or {} if key not in fields]

    def table_row(name, label_cell, answer_cell, mark, sample_cells):
        return [name] + [label_cell] * has_label + [answer_cell] + [mark] * graded + sample_cells

    rows = [table_row("field", "label", "answer", "ok", [f"s{i + 1}" for i in range(len(samples))])]
    for field in fields:
        given = (answer or {}).get(field)
        cells = [show(s["answer"].get(field)) if s.get("answer") else "—" for s in samples]
        if answer is not None:
            cells = ["=" if cell == show(given) else cell for cell in cells]
        expected = label.get(field) if has_label else None
        rows.append(table_row(field, show(expected), show(given), "✓" if given == expected else "✗", cells))

    for key in ("p_error", "failure", "redrawn_seed"):
        values = [record.get(key), *(s.get(key) for s in samples)]
        if any(value is not None for value in values):
            top, *rest = ["" if value is None else show(value) for value in values]
            rows.append(table_row(key, "", top, "", rest))

    widths = fit_columns(rows, width - 2)
    lines = []
    for number, row in enumerate(rows):
        cells = [f"{clip(cell, size):<{size}}" for cell, size in zip(row, widths)]
        if number == 0:
            lines.append("  " + paint("  ".join(cells).rstrip(), "2"))
            continue
        cells = [paint(text, MARK_STYLES[cell]) if cell in MARK_STYLES else text for cell, text in zip(row, cells)]
        lines.append("  " + "  ".join(cells).rstrip())
    if samples and answer is not None:
        lines.append("  " + paint("= same as answer", "2"))
    return lines


def pairs(mapping, limit):
    return "  ".join(f"{key}={clip(show(value), limit)}" for key, value in mapping.items())


def describe_event(event, full):
    """The tag and text of one trajectory event."""
    limit = 10**9 if full else COMPACT_VALUE
    kind = event.get("kind")
    if kind == "tool_receipt":
        receipt = event["receipt"]
        text = f"{receipt['tool']}  {pairs(receipt['payload'], limit)}"
        extras = {k: v for k, v in receipt.items() if k not in {"tool", "payload", "case_id"}}
        if not full:
            extras = {k: extras[k] for k in ("phase", "cost") if k in extras}
        return "receipt", f"{text}  [{pairs(extras, limit)}]"
    if kind == "tool_error":
        return "error", show(event.get("code"))
    if kind == "invalid_response":
        return "invalid", "the previous reply could not be parsed"
    if kind != "model_response":
        return "reply", show(event)
    try:
        reply = json.loads(event["text"])
    except json.JSONDecodeError:
        reply = None
    if isinstance(reply, dict) and reply.get("type") == "tool_call":
        return "call", f"{reply.get('tool')}  {pairs(reply.get('arguments') or {}, limit)}"
    if isinstance(reply, dict) and reply.get("type") == "final_proposal":
        confidence = {
            "p_" + key.removeprefix("self_reported_").removesuffix("_probability"): value
            for key, value in reply.items()
            if key.startswith("self_reported_")
        }
        return "final", f"{pairs(reply.get('result') or {}, limit)}  [{pairs(confidence, limit)}]"
    return "reply", clip(show(event.get("text")), limit)


def trajectory_lines(events, width, full):
    digits = len(str(len(events)))
    lines = []
    for number, event in enumerate(events, 1):
        tag, text = describe_event(event, full)
        plain = f"  {number:>{digits}} {tag:<{TAG_WIDTH}} "
        prefix = f"  {number:>{digits}} {paint(f'{tag:<{TAG_WIDTH}}', TAG_STYLES[tag])} "
        lines += wrapped(text, width, prefix, plain)
    return lines


def other_fields(record):
    """Anything the sections above do not show; the chat is only counted."""
    known = HEADER_FIELDS | SECTION_FIELDS
    other = {key: value for key, value in record.items() if key not in known}
    if "messages" in other:
        other["messages"] = f"{len(other['messages'])} chat messages (press j to see them)"
    return other


def record_inputs(record):
    """The case inputs; initial_M9 holds them only in its first chat message."""
    if "inputs" in record:
        return record["inputs"]
    try:
        return json.loads(record["messages"][0]["content"])["inputs"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


def render(record, name, index, total, width, full):
    title = f" {name}  case {index + 1}/{total} "
    lines = ["", paint("━━" + title + "━" * max(width - len(title) - 2, 0), "1")]

    identity = {key: record[key] for key in ("case_id", "split", "domain") if key in record}
    lines += field_block(identity, width)
    if "status" in record:
        failed = record["status"] != "completed"
        text = record["status"] + (f" ({record['failure']})" if record.get("failure") else "")
        lines.append(f"  {paint('status'.ljust(max(map(len, identity))), '2')}  {paint(text, '31' if failed else '32')}")

    inputs = record_inputs(record)
    if inputs:
        lines += [heading("INPUTS"), *field_block(inputs, width)]

    if "answer" in record or "label" in record:
        answer, label = record.get("answer"), record.get("label")
        note = ""
        if isinstance(label, dict) and answer is not None:
            right = sum(answer.get(key) == value for key, value in label.items())
            note = f"{right}/{len(label)} fields correct"
        lines += [heading("ANSWERS", note), *answer_table(record, width)]
        if full:
            for number, sample in enumerate(record.get("samples") or [], 1):
                if "text" in sample:
                    lines += wrapped(show(sample["text"]), width, f"  s{number} text  ")

    events = record.get("trajectory", record.get("history"))
    if events is not None:
        counts = {}
        for event in events:
            counts[event.get("kind")] = counts.get(event.get("kind"), 0) + 1
        note = "  ".join(f"{kind}={count}" for kind, count in counts.items())
        lines += [heading("TRAJECTORY", note), *trajectory_lines(events, width, full)]

    other = other_fields(record)
    if other:
        lines += [heading("OTHER"), *field_block(other, width)]
    return "\n".join(lines)


def load(path):
    if not path.is_file():
        sys.exit(f"view_data: no such file: {path}")
    rows = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                sys.exit(f"view_data: {path} line {number} is not JSON; expected one case per line")
            if not isinstance(row, dict):
                sys.exit(f"view_data: {path} line {number} is not a JSON object")
            rows.append(row)
    if not rows:
        sys.exit(f"view_data: {path} has no cases")
    return rows


def browse(rows, name, start):
    index, full, total = start, False, len(rows)

    def draw():
        width = min(shutil.get_terminal_size().columns, 120)
        print(render(rows[index], name, index, total, width, full))

    draw()
    while True:
        mode = "compact" if full else "full"
        try:
            command = input(f"\n[{index + 1}/{total}] Enter next · p prev · <n> go to · f {mode} · j JSON · q quit > ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        command = command.strip().lower()
        if command == "":
            if index + 1 == total:
                print("Last case. p goes back, q quits.")
                continue
            index += 1
        elif command == "p":
            if index == 0:
                print("First case.")
                continue
            index -= 1
        elif command.isdecimal():
            if not 1 <= int(command) <= total:
                print(f"Choose a case from 1 to {total}.")
                continue
            index = int(command) - 1
        elif command == "f":
            full = not full
        elif command == "j":
            print(json.dumps(rows[index], indent=2, ensure_ascii=False))
            continue
        elif command in ("q", "quit", "exit"):
            return
        else:
            print(f"Unknown command: {command}")
            continue
        draw()


def main():
    global use_color
    parser = argparse.ArgumentParser(description="Step through a SOP-UQ data file, one case per Enter.")
    parser.add_argument("file", type=Path, help="a .jsonl file, such as train.jsonl or test/initial_M9.jsonl")
    parser.add_argument("-s", "--start", type=int, default=1, help="case number to open first (default 1)")
    args = parser.parse_args()

    rows = load(args.file)
    if not 1 <= args.start <= len(rows):
        sys.exit(f"view_data: --start must be from 1 to {len(rows)}")
    use_color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    sys.stdout.reconfigure(errors="replace")
    try:
        browse(rows, args.file.name, args.start - 1)
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


if __name__ == "__main__":
    main()
