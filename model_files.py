"""Bounded model file ownership; never traverse directory links."""
import os
import stat
from pathlib import Path


def linked(path):
    return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT) if os.name == "nt" else path.is_symlink()


def files_under(path):
    if not os.path.lexists(path):
        return
    if linked(path):
        raise OSError(f"Refusing to follow linked model path: {path}")
    if path.is_dir():
        for child in path.iterdir():
            yield from files_under(child)
    else:
        yield path


def remove_owned(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    if path == root or not path.is_relative_to(root):
        raise ValueError("Model path escaped its runtime directory")
    for ancestor in (root, *path.relative_to(root).parents):
        candidate = ancestor if ancestor.is_absolute() else root / ancestor
        if candidate.exists() and linked(candidate):
            raise OSError(f"Refusing linked model directory: {candidate}")
    if not os.path.lexists(path):
        return
    if linked(path):
        raise OSError(f"Refusing linked model path: {path}")
    if path.is_dir():
        for child in path.iterdir():
            remove_owned(child, root)
        path.rmdir()
    else:
        path.unlink()
