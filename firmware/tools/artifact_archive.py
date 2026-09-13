"""Deterministic ZIP bytes for an unchanged review tree, independent of file mtimes."""
import stat
import zipfile


def archive_tree(root, destination):
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob('*')):
            if path.is_symlink():
                raise ValueError('Review archives cannot contain symlinks')
            if not path.is_file():
                continue
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), date_time=(1980,1,1,0,0,0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes(), compresslevel=9)
