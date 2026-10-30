"""Checks the package against the notebook it was ported from.

Runs the notebook's checker (cells 0-3 and 6 of try_grobid.ipynb) and the
package on the same upload, and diffs the two reports. HTTP responses from the
notebook run are recorded and replayed to the package, so both see the same
web and any difference is a difference in the code.

    python scripts/regression_check.py path/to/try_grobid.ipynb submissions.zip
"""

import argparse
import ast
import io
import json
import os
import sys
import tempfile
from collections import defaultdict

import pandas as pd
import requests

from falseref import check_path, to_frame
from falseref.sources import browser

NOTEBOOK_CELLS = (0, 1, 2, 3, 6)


class Tape:
    """Records every HTTP request made through requests, then replays the
    responses in the same order per request."""

    def __init__(self):
        self.recorded = defaultdict(list)
        self.played = defaultdict(int)
        self.replaying = False
        self.misses = []
        self.real = requests.sessions.Session.request

    @staticmethod
    def key(method, url, params=None, data=None, files=None, headers=None, **_):
        # uploads are keyed by file name: the two runs convert to different temp dirs
        names = sorted(os.path.basename(getattr(f, "name", "")) for f in (files or {}).values())
        return json.dumps([method.upper(), url, params, data, names, (headers or {}).get("Accept")],
                          sort_keys=True, default=str)

    def install(self):
        tape = self

        def request(session, method, url, **kw):
            k = tape.key(method, url, **kw)
            if tape.replaying and tape.played[k] < len(tape.recorded[k]):
                ok, value = tape.recorded[k][tape.played[k]]
                tape.played[k] += 1
                if ok:
                    return value
                raise value
            if tape.replaying:
                tape.misses.append(k)
            try:
                r = tape.real(session, method, url, **kw)
                r.content  # read the body now, so it can be replayed
                outcome = (True, r)
            except Exception as exc:
                outcome = (False, exc)
            if not tape.replaying:
                tape.recorded[k].append(outcome)
            if outcome[0]:
                return outcome[1]
            raise outcome[1]

        requests.sessions.Session.request = request


def notebook_namespace(path):
    """Executes the notebook cells' definitions, skipping the statements that
    run checks (loops, prints, calls to the notebook's own functions)."""
    cells = json.load(open(path))["cells"]
    trees = [ast.parse("".join(cells[i]["source"])) for i in NOTEBOOK_CELLS]
    defined = {n.name for t in trees for n in t.body if isinstance(n, ast.FunctionDef)}

    def keep(node):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)):
            return True
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            call = node.value
            return not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in defined)
        return False

    ns = {"__name__": "notebook"}
    for i, tree in zip(NOTEBOOK_CELLS, trees):
        tree.body = [n for n in tree.body if keep(n)]
        exec(compile(tree, f"<cell {i}>", "exec"), ns)
    return ns


def notebook_report(ns, upload):
    """Cell 6's batch loop."""
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, pdf in ns["submission_pdfs"](upload, tmp):
            refs, _ = ns["parse_references"](str(pdf))
            results = [ns["check_reference"](r) for r in refs]
            rows += [{"file": name, **r} for r in ns["report_rows"](refs, results)]
    return pd.DataFrame(rows)


def as_text(table):
    """Round-trip through CSV, as the reports are read, so dtypes compare equal."""
    buf = io.StringIO()
    table.to_csv(buf, index=False)
    buf.seek(0)
    return pd.read_csv(buf, dtype=str, keep_default_na=False)


def diff(old, new, limit=30):
    if list(old.columns) != list(new.columns):
        print("columns differ:\n  notebook:", list(old.columns), "\n  package: ", list(new.columns))
        return 1
    if old.shape != new.shape:
        print(f"row counts differ: notebook {len(old)}, package {len(new)}")
        return 1
    cells = [(i, c) for c in old.columns for i in old.index[old[c] != new[c]]]
    for i, c in cells[:limit]:
        print(f"row {i} ({old.at[i, 'file']} #{old.at[i, 'n']}) {c}:\n  notebook: {old.at[i, c]!r}\n  package:  {new.at[i, c]!r}")
    print(f"{len(cells)} differing cells in {old.shape[0]} rows x {old.shape[1]} columns")
    return 1 if cells else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("notebook", help="try_grobid.ipynb")
    parser.add_argument("upload", help="a PDF/DOC/DOCX or a zip of them")
    parser.add_argument("--save", help="directory to write both CSVs to")
    args = parser.parse_args()

    tape = Tape()
    tape.install()
    browser.ENABLED = False  # the notebook has no browser, and browser traffic cannot be replayed
    print("running the notebook's checker (live HTTP, recorded) ...")
    old = as_text(notebook_report(notebook_namespace(args.notebook), args.upload))
    print("running the package (HTTP replayed) ...")
    tape.replaying = True
    new = as_text(to_frame(check_path(args.upload)))
    if tape.misses:
        print(f"{len(tape.misses)} requests the notebook never made (sent live):")
        for k in tape.misses[:10]:
            print("  ", k)
    if args.save:
        old.to_csv(os.path.join(args.save, "notebook.csv"), index=False)
        new.to_csv(os.path.join(args.save, "package.csv"), index=False)
    sys.exit(diff(old, new) or bool(tape.misses))


if __name__ == "__main__":
    main()
