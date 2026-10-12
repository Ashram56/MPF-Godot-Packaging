"""Folder wipes, copies and renames that survive Windows/OneDrive: a file there can be read-only, or held for
a moment while OneDrive syncs it, and a deleted folder can still "exist" for a moment after rmtree returns.
Every call retries for a few seconds and makes files writable before giving up; on Linux and macOS they behave
like the plain shutil/os calls they replace."""
import os
import shutil
import stat
import sys
import time

TRIES = 10              # ~5 s in all
PAUSE = 0.5


def _retry(func, *args):
    for n in range(TRIES):
        try:
            return func(*args)
        except OSError:
            if n == TRIES - 1:
                raise
            time.sleep(PAUSE)


def _writable(path):
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _on_error(func, target, _exc):
    _writable(target)
    _retry(func, target)


def remove_dir(path):
    """rmtree, retried; what still cannot go (a file another program holds) is left, made writable."""
    if not os.path.lexists(path):
        return
    kw = {"onexc": _on_error} if sys.version_info >= (3, 12) else {"onerror": _on_error}
    try:
        shutil.rmtree(path, **kw)
    except OSError:
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                target = os.path.join(root, name)
                _writable(target)
                try:
                    os.remove(target)
                except OSError:
                    pass
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass
    for _ in range(TRIES):             # a removed folder can linger on OneDrive
        if not os.path.exists(path):
            return
        time.sleep(PAUSE)


def clear_dir(path):
    """path as an empty folder (or as empty as Windows allows: leftovers are writable, to be overwritten)."""
    remove_dir(path)
    _retry(os.makedirs, path, 0o777, True)


def replace(src, dst):
    """os.replace over a destination that may be read-only or briefly held."""
    if os.path.exists(dst):
        _writable(dst)
    _retry(os.replace, src, dst)


def replace_cached(tmp, cached):
    """tmp moved into place as cached, an entry of a cache keyed on the content. On Windows another worker can
    hold the same entry open (same key, same bytes): replacing it is "Access denied", so that copy stays and
    tmp goes. Any other failure is retried as replace() does."""
    try:
        os.replace(tmp, cached)
    except PermissionError:
        if not os.path.exists(cached):
            return replace(tmp, cached)
        try:
            os.remove(tmp)
        except OSError:
            pass


def copy_file(src, dst):
    if os.path.exists(dst):
        _writable(dst)
    return _retry(shutil.copy2, src, dst)


def copy_tree(src, dst):
    """dst replaced by a copy of src, overwriting whatever could not be removed."""
    remove_dir(dst)
    shutil.copytree(src, dst, dirs_exist_ok=True, copy_function=copy_file)
