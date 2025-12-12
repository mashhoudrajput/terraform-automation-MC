import logging
import os
import shutil
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Optional
from google.cloud import storage
from src.config.settings import settings

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_sync_thread: Optional[threading.Thread] = None


def _get_blob():
    if not settings.database_backup_bucket:
        return None
    try:
        client = storage.Client()
        bucket = client.bucket(settings.database_backup_bucket)
        return bucket.blob(settings.database_backup_object)
    except Exception as e:
        logger.error(f"Failed to get GCS blob: {e}")
        return None


def download_db_snapshot():
    blob = _get_blob()
    if not blob:
        logger.info("DB backup bucket not configured; skipping download")
        return
    
    if not blob.exists():
        logger.info("No DB snapshot found in GCS; skipping download")
        return

    dest = Path(settings.database_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_suffix(dest.suffix + ".download")
    
    try:
        blob.download_to_filename(tmp_path)
        shutil.move(tmp_path, dest)
        logger.info(f"Downloaded database snapshot from GCS to {dest}")
    except Exception as e:
        logger.error(f"Failed to download database snapshot: {e}")
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _create_sqlite_backup(src: Path) -> Optional[Path]:
    if not src.exists():
        return None

    fd, tmp_name = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    tmp_path = Path(tmp_name)
    
    try:
        with sqlite3.connect(src) as conn_src, sqlite3.connect(tmp_path) as conn_dst:
            conn_src.backup(conn_dst)
        return tmp_path
    except Exception as exc:
        logger.warning(f"Failed to create SQLite backup copy: {exc}")
        tmp_path.unlink(missing_ok=True)
        return None


def upload_db_snapshot():
    blob = _get_blob()
    if not blob:
        return

    db_path = Path(settings.database_path)
    copy_path = _create_sqlite_backup(db_path)
    
    if not copy_path:
        logger.info("Local DB not found; skipping upload")
        return

    try:
        blob.upload_from_filename(copy_path)
        logger.info(f"Uploaded database snapshot to gs://{blob.bucket.name}/{blob.name}")
    except Exception as exc:
        logger.warning(f"Failed to upload DB snapshot: {exc}")
    finally:
        copy_path.unlink(missing_ok=True)


def _sync_loop():
    interval = max(60, settings.database_backup_interval_seconds)
    while not _stop_event.wait(interval):
        try:
            upload_db_snapshot()
        except Exception as exc:
            logger.warning(f"Background DB sync failed: {exc}")


def start_periodic_backup():
    global _sync_thread
    if not settings.database_backup_bucket:
        logger.info("DB backup bucket not configured; periodic sync disabled")
        return
    
    if _sync_thread and _sync_thread.is_alive():
        return
    
    _stop_event.clear()
    _sync_thread = threading.Thread(target=_sync_loop, daemon=True)
    _sync_thread.start()
    logger.info(
        f"Started periodic DB sync to gs://{settings.database_backup_bucket}/{settings.database_backup_object} every {settings.database_backup_interval_seconds}s"
    )


def stop_periodic_backup(run_final_upload: bool = True):
    if _sync_thread and _sync_thread.is_alive():
        _stop_event.set()
        _sync_thread.join(timeout=5)
    
    if run_final_upload:
        try:
            upload_db_snapshot()
        except Exception as exc:
            logger.warning(f"Final DB upload failed: {exc}")
