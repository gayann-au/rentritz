import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app

ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
ALLOWED_DOCUMENT_EXTENSIONS = {'pdf'}
MAX_IMAGE_BYTES = 5 * 1024 * 1024      # 5 MB
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB


def _base_upload_path():
    return current_app.config.get(
        'UPLOAD_FOLDER',
        os.path.join(current_app.root_path, '..', 'uploads'),
    )


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def allowed_image(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def allowed_document(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_DOCUMENT_EXTENSIONS


def save_lawyer_photo(file_storage, user_id):
    """
    Save a lawyer profile photo.
    Returns the relative path string to store in the database.
    Raises ValueError on invalid file.
    """
    if not allowed_image(file_storage.filename):
        raise ValueError('Invalid image format. Allowed: jpg, jpeg, png, webp')
    file_storage.seek(0, 2)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > MAX_IMAGE_BYTES:
        raise ValueError('Image must be under 5 MB')
    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    filename = f'profile_{uuid.uuid4().hex}.{ext}'
    folder = os.path.join(_base_upload_path(), 'lawyers', 'photos', str(user_id))
    _ensure_dir(folder)
    file_storage.save(os.path.join(folder, filename))
    # Return relative path — stored in DB.
    # To migrate to S3/R2: upload to bucket here, return the object URL instead.
    return os.path.join('lawyers', 'photos', str(user_id), filename)


def save_lawyer_licence(file_storage, user_id):
    """
    Save a lawyer licence PDF.
    Returns the relative path string to store in the database.
    Raises ValueError on invalid file.
    """
    if not allowed_document(file_storage.filename):
        raise ValueError('Invalid format. Only PDF allowed.')
    file_storage.seek(0, 2)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > MAX_DOCUMENT_BYTES:
        raise ValueError('Document must be under 10 MB')
    filename = f'licence_{uuid.uuid4().hex}.pdf'
    folder = os.path.join(_base_upload_path(), 'lawyers', 'licences', str(user_id))
    _ensure_dir(folder)
    file_storage.save(os.path.join(folder, filename))
    # Return relative path — stored in DB.
    # To migrate to S3/R2: upload to bucket here, return the object URL instead.
    return os.path.join('lawyers', 'licences', str(user_id), filename)


def delete_file(relative_path):
    """
    Delete a stored file by its relative path.
    Silently ignores missing files.
    """
    if not relative_path:
        return
    try:
        os.remove(os.path.join(_base_upload_path(), relative_path))
    except FileNotFoundError:
        pass


def get_upload_url(relative_path):
    """
    Convert a stored relative path to a URL the browser can load.
    To migrate to S3/R2: return the CDN/bucket URL here instead.
    """
    if not relative_path:
        return None
    return '/uploads/' + relative_path.replace(os.sep, '/')
