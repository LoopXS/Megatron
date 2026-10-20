"""Detect JavaScript runtimes usable by yt-dlp's EJS challenge solver.

Modern yt-dlp needs a JavaScript runtime to solve YouTube's signature and
``n`` challenges.  Without one, authenticated extraction fails with
``The page needs to be reloaded.`` even when the cookies are valid.

yt-dlp supports Node.js >= 22, Deno >= 2.3, Bun >= 1.2.11 and QuickJS-ng.
The runtime is looked up on ``PATH`` first and then in the common install
locations used by the official installers (nvm, deno, bun).
"""

import glob
import os
import re
import shutil

JS_RUNTIME_HINT = (
    "Install Node.js 22+ (recommended), Deno 2.3+ or Bun 1.2.11+ on the "
    "server so yt-dlp can solve YouTube's JavaScript challenges."
)

# runtime key understood by yt-dlp -> (executable name, extra search paths)
_RUNTIMES = {
    "deno": (
        "deno",
        (
            "~/.deno/bin/deno",
            "/usr/local/bin/deno",
            "/usr/bin/deno",
        ),
    ),
    "node": (
        "node",
        (
            "/usr/local/bin/node",
            "/usr/bin/node",
            "/opt/node/bin/node",
            "/snap/bin/node",
            "~/.volta/bin/node",
        ),
    ),
    "bun": (
        "bun",
        (
            "~/.bun/bin/bun",
            "/usr/local/bin/bun",
            "/usr/bin/bun",
        ),
    ),
    "quickjs": (
        "qjs",
        (
            "~/.local/bin/qjs",
            "/usr/local/bin/qjs",
            "/usr/bin/qjs",
        ),
    ),
}


_VERSIONED_NODE_GLOBS = (
    "~/.nvm/versions/node/*/bin/node",
    "~/.local/share/fnm/node-versions/*/installation/bin/node",
    "~/.asdf/installs/nodejs/*/bin/node",
)


def _versioned_nodes():
    """Return version-manager Node binaries, newest version first."""
    found = []
    for pattern in _VERSIONED_NODE_GLOBS:
        pattern = os.path.expanduser(pattern)
        for path in glob.glob(pattern):
            match = re.search(r"[/\\]v?(\d+)\.(\d+)\.(\d+)[/\\]", path)
            version = (
                tuple(int(part) for part in match.groups())
                if match
                else (0, 0, 0)
            )
            found.append((version, path))
    return [path for _version, path in sorted(found, reverse=True)]


def _find_executable(name, extra_paths):
    path = shutil.which(name)
    if path:
        return path

    candidates = list(extra_paths)
    if name == "node":
        candidates.extend(_versioned_nodes())

    for candidate in candidates:
        candidate = os.path.expanduser(candidate)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


_cached_runtimes = None


def detect_js_runtimes(use_cache=True):
    """Return a yt-dlp ``js_runtimes`` mapping for installed runtimes.

    Results are cached because the runtime cannot change without a restart.
    """
    global _cached_runtimes
    if use_cache and _cached_runtimes is not None:
        return dict(_cached_runtimes)

    runtimes = {}
    for name, (executable, extra_paths) in _RUNTIMES.items():
        path = _find_executable(executable, extra_paths)
        if path:
            runtimes[name] = {"path": path}

    _cached_runtimes = runtimes
    return dict(runtimes)
