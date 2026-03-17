#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COS File Migration Script (V2 - Optimized)
Migrate from tamprod-1258344699 to rumprod-1258344699
and write file info to taw_project_release_file table.

Optimizations over v1:
  1. Server-side copy (copy_object) instead of download+upload
  2. Multi-threaded concurrent processing
  3. Pre-load existing files in new bucket to skip HEAD per file
  4. Batch DB inserts (with rate limiting to avoid DB pressure)
"""

# Compatibility patch
try:
    import urllib3.packages.six as six
except ImportError:
    import six
    import urllib3
    urllib3.packages.six = six

import os
import re
import hashlib
import logging
import sys
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from qcloud_cos import CosConfig, CosS3Client
import pymysql
from dotenv import load_dotenv

# ========== Load .env ==========
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=env_path)

# ========== Configuration ==========

COS_SECRET_ID = os.environ.get('COS_SECRET_ID')
COS_SECRET_KEY = os.environ.get('COS_SECRET_KEY')
COS_REGION = os.environ.get('COS_REGION', 'ap-guangzhou')

OLD_BUCKET = os.environ.get('OLD_BUCKET', 'tamprod-1258344699')
# Keep consistent with v1: default to gray-scale prefix, change to 'sourcemap/' for full migration
OLD_PREFIX = os.environ.get('OLD_PREFIX', 'sourcemap/')
NEW_BUCKET = os.environ.get('NEW_BUCKET', 'rumprod-1258344699')

OLD_DB_CONFIG = {
    'host': os.environ.get('OLD_DB_HOST', '127.0.0.1'),
    'port': int(os.environ.get('OLD_DB_PORT', '3306')),
    'user': os.environ.get('OLD_DB_USER', 'root'),
    'password': os.environ.get('OLD_DB_PASSWORD', ''),
    'database': os.environ.get('OLD_DB_NAME', 'tam'),
    'charset': 'utf8mb4'
}

NEW_DB_CONFIG = {
    'host': os.environ.get('NEW_DB_HOST', '127.0.0.1'),
    'port': int(os.environ.get('NEW_DB_PORT', '3306')),
    'user': os.environ.get('NEW_DB_USER', 'root'),
    'password': os.environ.get('NEW_DB_PASSWORD', ''),
    'database': os.environ.get('NEW_DB_NAME', 'taw'),
    'charset': 'utf8mb4'
}

# Concurrency: number of worker threads for COS operations
WORKER_COUNT = int(os.environ.get('WORKER_COUNT', '20'))

# Batch DB insert size (keep small to limit DB pressure)
DB_BATCH_SIZE = int(os.environ.get('DB_BATCH_SIZE', '50'))

# Sleep interval (seconds) between batch DB inserts to limit pressure
DB_BATCH_INTERVAL = float(os.environ.get('DB_BATCH_INTERVAL', '0.1'))

# ========== Logging ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(threadName)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('cos_migrate_v2.log')
    ]
)
logger = logging.getLogger()


# ========== Utility Functions ==========

def parse_old_file_path(file_key):
    """
    Parse old bucket file path.
    Format: sourcemap/{project_key}/{file_name}[time_{timestamp}]
    """
    pattern = r'^sourcemap/([^/]+)/(.+?)\[time_(\d+)\]$'
    match = re.match(pattern, file_key)
    if match:
        return match.group(1), match.group(2), match.group(3), '1.0.0'

    pattern2 = r'^sourcemap/([^/]+)/(.+)$'
    match2 = re.match(pattern2, file_key)
    if match2:
        return match2.group(1), match2.group(2), '0', '1.0.0'

    return None, None, None, None


def generate_new_file_key(project_id, version, timestamp, file_name):
    return f"{project_id}-{version}-{timestamp}-{file_name}"


def create_db_connection(config):
    """Create a new database connection (thread-safe: each thread gets its own)."""
    return pymysql.connect(
        host=config['host'],
        port=config['port'],
        user=config['user'],
        password=config['password'],
        database=config['database'],
        charset=config['charset'],
        connect_timeout=30,
        read_timeout=30,
        write_timeout=30,
        autocommit=True,
        ssl_disabled=True
    )


class COSMigratorV2:
    def __init__(self):
        config = CosConfig(Region=COS_REGION, SecretId=COS_SECRET_ID, SecretKey=COS_SECRET_KEY)
        self.cos_client = CosS3Client(config)

        # project_key -> project_id cache (thread-safe with lock)
        self.project_cache = {}
        self.project_cache_lock = threading.Lock()

        # Dedicated DB connection for project_id queries (protected by lock)
        self._old_db_lock = threading.Lock()
        self.old_db = None

        # Pre-loaded set of existing keys in new bucket
        self.existing_keys = set()

        # Thread-safe counters
        self._lock = threading.Lock()
        self.total_count = 0
        self.success_count = 0
        self.skip_count = 0
        self.fail_count = 0

        # DB insert buffer (single writer thread flushes to DB)
        self._db_lock = threading.Lock()
        self._db_buffer = []
        self._db_insert_count = 0
        self._db_fail_count = 0

    # ---------- DB ----------
    def connect_db(self):
        """Connect old DB for project_id lookups."""
        try:
            self.old_db = create_db_connection(OLD_DB_CONFIG)
            logger.info("Connected to old database")
        except Exception as e:
            logger.error(f"Failed to connect old database: {e}")
            raise

    def close_db(self):
        if self.old_db:
            self.old_db.close()

    def get_project_id(self, project_key):
        """Query project_id from old DB (thread-safe with lock)."""
        # Check cache first (read lock)
        with self.project_cache_lock:
            if project_key in self.project_cache:
                return self.project_cache[project_key]

        # Query DB with lock (pymysql is not thread-safe)
        with self._old_db_lock:
            # Double-check cache after acquiring lock
            with self.project_cache_lock:
                if project_key in self.project_cache:
                    return self.project_cache[project_key]
            try:
                with self.old_db.cursor() as cursor:
                    cursor.execute("SELECT id FROM tam_project WHERE project_key = %s", (project_key,))
                    result = cursor.fetchone()
                    pid = result[0] if result else None
                    with self.project_cache_lock:
                        self.project_cache[project_key] = pid
                    if pid is None:
                        logger.warning(f"No project found for project_key: {project_key}")
                    return pid
            except Exception as e:
                logger.error(f"Failed to query project_id for {project_key}: {e}")
                # Try to reconnect
                try:
                    self.old_db = create_db_connection(OLD_DB_CONFIG)
                    logger.info("Reconnected to old database")
                except Exception:
                    pass
                return None

    def _buffer_db_insert(self, record):
        """Buffer a record and flush when batch size is reached."""
        flush_batch = None
        with self._db_lock:
            self._db_buffer.append(record)
            if len(self._db_buffer) >= DB_BATCH_SIZE:
                flush_batch = self._db_buffer[:]
                self._db_buffer = []
        if flush_batch:
            self._flush_db(flush_batch)

    def _flush_db(self, batch):
        """Batch insert records to DB using a dedicated connection."""
        if not batch:
            return
        conn = None
        try:
            conn = create_db_connection(NEW_DB_CONFIG)
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO taw_project_release_file
                    (project_id, project_key, version, file_key, file_name, file_size, file_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    file_size = VALUES(file_size),
                    file_hash = VALUES(file_hash)
                """
                cursor.executemany(sql, batch)
            conn.commit()
            self._db_insert_count += len(batch)
            logger.info(f"Batch inserted {len(batch)} records to DB (total inserted: {self._db_insert_count})")
            # Rate limiting: sleep briefly to avoid DB pressure
            time.sleep(DB_BATCH_INTERVAL)
        except Exception as e:
            logger.error(f"Batch DB insert failed ({len(batch)} records): {e}")
            self._db_fail_count += len(batch)
            # Fallback: try inserting one by one
            if conn:
                for record in batch:
                    try:
                        with conn.cursor() as cursor:
                            sql = """
                                INSERT INTO taw_project_release_file
                                (project_id, project_key, version, file_key, file_name, file_size, file_hash)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE
                                file_size = VALUES(file_size),
                                file_hash = VALUES(file_hash)
                            """
                            cursor.execute(sql, record)
                        conn.commit()
                    except Exception as e2:
                        logger.error(f"Single DB insert also failed: {e2}")
        finally:
            if conn:
                conn.close()

    def flush_remaining_db(self):
        """Flush any remaining records in buffer."""
        with self._db_lock:
            batch = self._db_buffer[:]
            self._db_buffer = []
        self._flush_db(batch)

    # ---------- COS ----------
    def preload_existing_keys(self):
        """
        Pre-load all existing file keys in the new bucket.
        This avoids per-file HEAD requests.
        """
        logger.info("Pre-loading existing keys from new bucket (this may take a while)...")
        marker = ''
        count = 0
        while True:
            kwargs = {'Bucket': NEW_BUCKET, 'MaxKeys': 1000}
            if marker:
                kwargs['Marker'] = marker
            response = self.cos_client.list_objects(**kwargs)
            contents = response.get('Contents', [])
            if not contents:
                break
            for item in contents:
                self.existing_keys.add(item['Key'])
                count += 1
            if count % 10000 == 0:
                logger.info(f"  Pre-loaded {count} existing keys...")
            if not response.get('IsTruncated', False):
                break
            marker = response.get('NextMarker', contents[-1]['Key'])

        logger.info(f"Pre-loaded {count} existing keys from new bucket")

    def _get_real_file_hash(self, old_key):
        """
        Get the real MD5 hash of the source file via HEAD request on the old bucket.
        COS ETag for non-multipart uploads is the file's MD5 (with surrounding quotes).
        For multipart uploads, ETag has a '-N' suffix — in that case, fall back to
        downloading the file content to compute the real MD5.
        """
        try:
            head_resp = self.cos_client.head_object(Bucket=OLD_BUCKET, Key=old_key)
            etag = head_resp.get('ETag', '').strip('"')
            if etag and '-' not in etag:
                # Standard ETag = MD5 hex digest
                return etag
            # Multipart upload: ETag is not a pure MD5, need to download and compute
            logger.info(f"Multipart ETag detected for {old_key}, downloading to compute MD5")
            response = self.cos_client.get_object(Bucket=OLD_BUCKET, Key=old_key)
            content = response['Body'].get_raw_stream().read()
            return hashlib.md5(content).hexdigest()
        except Exception as e:
            logger.warning(f"Failed to get real hash for {old_key}: {e}, using key-based hash as fallback")
            return hashlib.md5(old_key.encode()).hexdigest()

    def server_side_copy(self, old_key, new_key, file_size):
        """
        Use COS server-side copy instead of download+upload.
        Much faster - data stays within COS, no bandwidth cost.
        Gets the real file MD5 hash via HEAD request on source file.
        """
        try:
            # Get real file hash first (lightweight HEAD request, no download needed for most files)
            file_hash = self._get_real_file_hash(old_key)

            # Use dict format for CopySource (more reliable than string format,
            # avoids parsing issues with long keys or special characters)
            copy_source = {
                'Bucket': OLD_BUCKET,
                'Key': old_key,
                'Region': COS_REGION,
            }

            self.cos_client.copy_object(
                Bucket=NEW_BUCKET,
                Key=new_key,
                CopySource=copy_source,
            )
            return file_size, file_hash
        except Exception as e:
            logger.error(f"Server-side copy failed {old_key} -> {new_key}: {e}")
            return None, None

    # ---------- Worker ----------
    def _process_file(self, old_key, file_size_from_list, dry_run):
        """Process a single file (called from thread pool)."""
        project_key, file_name, timestamp, version = parse_old_file_path(old_key)

        if not project_key:
            with self._lock:
                self.skip_count += 1
            return

        project_id = self.get_project_id(project_key)
        if not project_id:
            with self._lock:
                self.skip_count += 1
            return

        new_key = generate_new_file_key(project_id, version, timestamp, file_name)

        if dry_run:
            logger.info(f"[DRY RUN] {old_key} -> {new_key}")
            with self._lock:
                self.success_count += 1
            return

        # Check if already exists (from pre-loaded set, no network call)
        if new_key in self.existing_keys:
            with self._lock:
                self.skip_count += 1
            return

        # Server-side copy
        file_size, file_hash = self.server_side_copy(old_key, new_key, file_size_from_list)
        if file_size is None:
            with self._lock:
                self.fail_count += 1
            return

        # Buffer DB insert
        self._buffer_db_insert((project_id, project_key, version, new_key, file_name, file_size, file_hash))

        with self._lock:
            self.success_count += 1

    # ---------- Main ----------
    def migrate(self, dry_run=False):
        start_time = time.time()
        self.connect_db()

        # Pre-load existing keys to skip already migrated files
        if not dry_run:
            self.preload_existing_keys()

        marker = ''
        logger.info(f"Starting migration from prefix: {OLD_PREFIX} (workers={WORKER_COUNT})")

        try:
            with ThreadPoolExecutor(max_workers=WORKER_COUNT, thread_name_prefix='migrator') as executor:
                while True:
                    kwargs = {'Bucket': OLD_BUCKET, 'Prefix': OLD_PREFIX, 'MaxKeys': 1000}
                    if marker:
                        kwargs['Marker'] = marker
                    response = self.cos_client.list_objects(**kwargs)

                    contents = response.get('Contents', [])
                    if not contents:
                        break

                    # Submit batch to thread pool
                    futures = []
                    for item in contents:
                        with self._lock:
                            self.total_count += 1
                        f = executor.submit(
                            self._process_file,
                            item['Key'],
                            int(item.get('Size', 0)),
                            dry_run
                        )
                        futures.append(f)

                    # Wait for this batch to complete before listing next
                    for f in as_completed(futures):
                        try:
                            f.result()
                        except Exception as e:
                            logger.error(f"Worker exception: {e}")
                            with self._lock:
                                self.fail_count += 1

                    # Progress log
                    elapsed_so_far = time.time() - start_time
                    speed = self.total_count / elapsed_so_far if elapsed_so_far > 0 else 0
                    logger.info(
                        f"Progress: total={self.total_count}, "
                        f"success={self.success_count}, skip={self.skip_count}, "
                        f"fail={self.fail_count}, speed={speed:.1f} files/sec"
                    )

                    if not response.get('IsTruncated', False):
                        break
                    marker = response.get('NextMarker', contents[-1]['Key'])

            # Flush remaining DB records
            self.flush_remaining_db()

        finally:
            self.close_db()

        elapsed = time.time() - start_time
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)

        logger.info("=" * 60)
        logger.info("Migration completed!")
        logger.info(f"Time elapsed: {hours}h {minutes}m {seconds}s")
        logger.info(f"Total:      {self.total_count}")
        logger.info(f"Success:    {self.success_count}")
        logger.info(f"Skipped:    {self.skip_count}")
        logger.info(f"Failed:     {self.fail_count}")
        logger.info(f"DB inserted:{self._db_insert_count}")
        logger.info(f"DB failed:  {self._db_fail_count}")
        if elapsed > 0:
            logger.info(f"Speed:      {self.total_count / elapsed:.1f} files/sec")
        logger.info("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='COS File Migration Tool (V2 Optimized)')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    parser.add_argument('--workers', type=int, default=None, help='Number of concurrent workers (default: 20)')
    args = parser.parse_args()

    if args.workers:
        global WORKER_COUNT
        WORKER_COUNT = args.workers

    migrator = COSMigratorV2()
    migrator.migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
