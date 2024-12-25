import os
import shutil
import zipfile
from fnmatch import fnmatch

def zip_with_ignore(src_paths, dest_zip, ignore_patterns=None):
    """
    Zips files and directories while ignoring specified patterns.
    
    :param src_paths: List of file or folder paths to include in the zip.
    :param dest_zip: Path to the output zip file.
    :param ignore_patterns: List of patterns to ignore (e.g., ['*.tmp', '__pycache__']).
    """
    if ignore_patterns is None:
        ignore_patterns = []

    def should_ignore(path):
        """Determines if a path should be ignored based on patterns."""
        for pattern in ignore_patterns:
            if fnmatch(os.path.basename(path), pattern) or fnmatch(path, pattern):
                return True
        return False

    with zipfile.ZipFile(dest_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for src_path in src_paths:
            if not os.path.exists(src_path):
                print(f"Warning: {src_path} does not exist.")
                continue

            if os.path.isfile(src_path) and not should_ignore(src_path):
                zipf.write(src_path, os.path.relpath(src_path, os.path.dirname(src_paths[0])))
            elif os.path.isdir(src_path):
                for root, dirs, files in os.walk(src_path):
                    # Filter directories to ignore
                    dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d))]
                    for file in files:
                        file_path = os.path.join(root, file)
                        if not should_ignore(file_path):
                            arcname = os.path.relpath(file_path, os.path.dirname(src_paths[0]))
                            zipf.write(file_path, arcname)

# Example Usage
src_paths = [
    'src',
    'setup.py',
    'pyproject.toml',
]
dest_zip = 'output.zip'
ignore_patterns = ['__pycache__', '*.egg-info']

zip_with_ignore(src_paths, dest_zip, ignore_patterns)
print(f"Zip archive created at: {dest_zip}")
