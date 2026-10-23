from django.conf import settings
from django.core.files.storage import FileSystemStorage


def private_storage():
    """Web sunucusunun SUNMADIĞI klasör. Dosyalar yalnızca yetkili görünümle indirilir."""
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)
