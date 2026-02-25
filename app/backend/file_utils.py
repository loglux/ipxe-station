# file_utils.py

import os


def list_files(directory):
    """
    Return a list of filenames in the given directory.
    """
    try:
        return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    except Exception:
        return []


def save_uploaded_file(file_obj, directory):
    """
    Save an uploaded file-like object into the target directory.
    Returns the full path of the saved file.
    """
    os.makedirs(directory, exist_ok=True)
    target_path = os.path.join(directory, file_obj.name)
    with open(target_path, "wb") as out_file:
        out_file.write(file_obj.read())
    return target_path


def delete_file(filename, directory):
    """
    Delete a file by name in the target directory.
    Returns True if deleted, False otherwise.
    """
    try:
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
            return True
    except Exception:
        pass
    return False
