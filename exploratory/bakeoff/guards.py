"""Isolation guards for the bake-off. Import and call these before anything reads data.

- install_audit_hook(): refuses, for the rest of the process, to open anything collected after the freeze.
- verify_inputs(): checks MANIFEST input hashes (plus two pinned files) and exits on any difference.
"""
import hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST = "outputs/frozen/v1/MANIFEST.json"
# Pinned from freeze commit 683a8fb (2026-11-16). daily_errors.csv is not listed in the MANIFEST inputs.
PINNED = {
    MANIFEST: "4436e39578e68ba394e24ce4fa7b7cbfe19bc3463a8dfd3928bc2610dff03a2d",
    "outputs/backtest/daily_errors.csv": "fe0b8a3aacbd329b89350ba8ef4867438ca52cf3fd02123bdb8145cb86f5d594",
}
FORBIDDEN_DIRS = ("data/post", "outputs/tracker")
FORBIDDEN_FILES = ("outputs/dashboard/tracker.csv",)


def _norm(p):
    return os.path.normcase(os.path.abspath(p)).replace("\\", "/")


_BAD_DIRS = [_norm(os.path.join(ROOT, d)) for d in FORBIDDEN_DIRS]
_BAD_FILES = [_norm(os.path.join(ROOT, f)) for f in FORBIDDEN_FILES]


def forbidden(path):
    p = _norm(path)
    return any(p == d or p.startswith(d + "/") for d in _BAD_DIRS) or p in _BAD_FILES


def install_audit_hook():
    def hook(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            path = os.fsdecode(args[0])
            if forbidden(path):
                raise PermissionError(f"bake-off isolation: refusing to open post-freeze path {path}")
    sys.addaudithook(hook)


def _sha(path):
    with open(os.path.join(ROOT, path), "rb") as f:
        b = f.read()
    return hashlib.sha256(b).hexdigest(), hashlib.sha256(b.replace(b"\r\n", b"\n")).hexdigest()


def verify_inputs(log=print):
    """Exact bytes, or bytes after CRLF->LF (a Windows checkout with core.autocrlf). Anything else aborts."""
    expected = dict(PINNED)
    raw, lf = _sha(MANIFEST)
    if PINNED[MANIFEST] not in (raw, lf):
        sys.exit(f"ABORT: {MANIFEST} differs from the freeze commit")
    with open(os.path.join(ROOT, MANIFEST)) as f:
        expected.update(json.load(f)["inputs"])
    bad, modes = [], {"exact": 0, "after CRLF->LF": 0}
    for path, h in expected.items():
        if not os.path.exists(os.path.join(ROOT, path)):
            bad.append(f"{path} (missing)"); continue
        raw, lf = _sha(path)
        if raw == h: modes["exact"] += 1
        elif lf == h: modes["after CRLF->LF"] += 1
        else: bad.append(path)
    if bad:
        sys.exit("ABORT: input hash mismatch: " + ", ".join(bad))
    log(f"hash check passed: {len(expected)} files ({modes['exact']} exact, {modes['after CRLF->LF']} after CRLF->LF)")
    return {"files": len(expected), **modes}
