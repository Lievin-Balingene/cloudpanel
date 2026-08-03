from __future__ import annotations

from django.urls import path

from apps.files.views import (
    FileChmodView,
    FileCompressView,
    FileCopyView,
    FileCreateView,
    FileDecompressView,
    FileDeleteView,
    FileDownloadView,
    FileListView,
    FileMkdirView,
    FileMoveView,
    FilePreviewView,
    FileReadView,
    FileRenameView,
    FileSearchView,
    FileUploadView,
    FileWriteView,
)

urlpatterns = [
    path("", FileListView.as_view(), name="files-list"),
    path("mkdir/", FileMkdirView.as_view(), name="files-mkdir"),
    path("create/", FileCreateView.as_view(), name="files-create"),
    path("read/", FileReadView.as_view(), name="files-read"),
    path("write/", FileWriteView.as_view(), name="files-write"),
    path("delete/", FileDeleteView.as_view(), name="files-delete"),
    path("rename/", FileRenameView.as_view(), name="files-rename"),
    path("copy/", FileCopyView.as_view(), name="files-copy"),
    path("move/", FileMoveView.as_view(), name="files-move"),
    path("chmod/", FileChmodView.as_view(), name="files-chmod"),
    path("compress/", FileCompressView.as_view(), name="files-compress"),
    path("decompress/", FileDecompressView.as_view(), name="files-decompress"),
    path("search/", FileSearchView.as_view(), name="files-search"),
    path("upload/", FileUploadView.as_view(), name="files-upload"),
    path("download/", FileDownloadView.as_view(), name="files-download"),
    path("preview/", FilePreviewView.as_view(), name="files-preview"),
]
