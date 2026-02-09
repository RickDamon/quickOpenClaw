#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COS 文件迁移脚本
从 tamprod-1258344699 迁移到 rumprod-1258344699
同时将文件信息写入 taw_project_release_file 表
"""

# 兼容性补丁：修复 urllib3.packages.six 问题
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
from pathlib import Path
from qcloud_cos import CosConfig, CosS3Client
import pymysql
from dotenv import load_dotenv

# ========== 加载 .env 文件 ==========
# 优先从脚本同目录下的 .env 加载，也支持从项目根目录加载
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=env_path)

# ========== 配置区域（从 .env 读取） ==========

# COS 配置
COS_SECRET_ID = os.environ.get('COS_SECRET_ID')
COS_SECRET_KEY = os.environ.get('COS_SECRET_KEY')
COS_REGION = os.environ.get('COS_REGION', 'ap-guangzhou')

# 旧桶（源）
OLD_BUCKET = os.environ.get('OLD_BUCKET', 'tamprod-1258344699')
# 灰度测试：只迁移指定 project_key 的文件，全量迁移时改回 'sourcemap/'
OLD_PREFIX = os.environ.get('OLD_PREFIX', 'sourcemap/AVwtPZpAWCxjRrneGB/')

# 新桶（目标）
NEW_BUCKET = os.environ.get('NEW_BUCKET', 'rumprod-1258344699')

# 旧数据库（taw_project 表所在）
OLD_DB_CONFIG = {
    'host': os.environ.get('OLD_DB_HOST', '127.0.0.1'),
    'port': int(os.environ.get('OLD_DB_PORT', '3306')),
    'user': os.environ.get('OLD_DB_USER', 'root'),
    'password': os.environ.get('OLD_DB_PASSWORD', ''),
    'database': os.environ.get('OLD_DB_NAME', 'tam'),
    'charset': 'utf8mb4'
}

# 新数据库（taw_project_release_file 表所在）
NEW_DB_CONFIG = {
    'host': os.environ.get('NEW_DB_HOST', '127.0.0.1'),
    'port': int(os.environ.get('NEW_DB_PORT', '3306')),
    'user': os.environ.get('NEW_DB_USER', 'root'),
    'password': os.environ.get('NEW_DB_PASSWORD', ''),
    'database': os.environ.get('NEW_DB_NAME', 'taw'),
    'charset': 'utf8mb4'
}

# 批量处理大小
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '100'))

# ========== 日志配置 ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('cos_migrate.log')
    ]
)
logger = logging.getLogger()

# ========== 工具函数 ==========

def parse_old_file_path(file_key):
    """
    解析旧桶文件路径
    格式: sourcemap/{project_key}/{file_name}[time_{timestamp}]
    示例: sourcemap/AVwtPZpAWCxjRrneGB/AccountAuthorization-Byid4Ami.js.map[time_1769506362004]
    返回: (project_key, file_name, timestamp, version)
    """
    # 匹配格式: sourcemap/{project_key}/{file_name}[time_{timestamp}]
    pattern = r'^sourcemap/([^/]+)/(.+?)\[time_(\d+)\]$'
    match = re.match(pattern, file_key)
    
    if match:
        project_key = match.group(1)
        file_name = match.group(2)
        timestamp = match.group(3)
        version = '1.0.0'
        return project_key, file_name, timestamp, version
    
    # 尝试没有时间戳的格式
    pattern2 = r'^sourcemap/([^/]+)/(.+)$'
    match2 = re.match(pattern2, file_key)
    if match2:
        project_key = match2.group(1)
        file_name = match2.group(2)
        timestamp = '0'
        version = '1.0.0'
        return project_key, file_name, timestamp, version
    
    return None, None, None, None


def generate_new_file_key(project_id, version, timestamp, file_name):
    """
    生成新桶文件路径
    格式: {project_id}-{version}-{timestamp}-{file_name}
    示例: 124464-180-1766048942465-app.0c91ca2b.js.map
    """
    return f"{project_id}-{version}-{timestamp}-{file_name}"


def get_file_hash(content):
    """计算文件 MD5 hash"""
    return hashlib.md5(content).hexdigest()


class COSMigrator:
    def __init__(self):
        # 初始化 COS 客户端
        config = CosConfig(Region=COS_REGION, SecretId=COS_SECRET_ID, SecretKey=COS_SECRET_KEY)
        self.cos_client = CosS3Client(config)
        
        # 数据库连接
        self.old_db = None
        self.new_db = None
        
        # 缓存 project_key -> project_id 映射
        self.project_cache = {}
    
    def connect_db(self):
        """连接数据库"""
        try:
            self.old_db = pymysql.connect(
                host=OLD_DB_CONFIG['host'],
                port=OLD_DB_CONFIG['port'],
                user=OLD_DB_CONFIG['user'],
                password=OLD_DB_CONFIG['password'],
                database=OLD_DB_CONFIG['database'],
                charset=OLD_DB_CONFIG['charset'],
                connect_timeout=30,
                read_timeout=30,
                write_timeout=30,
                autocommit=True,
                ssl_disabled=True
            )
            logger.info("Connected to old database")
        except Exception as e:
            logger.error(f"Failed to connect old database: {e}")
            raise
        
        try:
            self.new_db = pymysql.connect(
                host=NEW_DB_CONFIG['host'],
                port=NEW_DB_CONFIG['port'],
                user=NEW_DB_CONFIG['user'],
                password=NEW_DB_CONFIG['password'],
                database=NEW_DB_CONFIG['database'],
                charset=NEW_DB_CONFIG['charset'],
                connect_timeout=30,
                read_timeout=30,
                write_timeout=30,
                autocommit=True,
                ssl_disabled=True
            )
            logger.info("Connected to new database")
        except Exception as e:
            logger.error(f"Failed to connect new database: {e}")
            raise
    
    def close_db(self):
        """关闭数据库连接"""
        if self.old_db:
            self.old_db.close()
        if self.new_db:
            self.new_db.close()
    
    def get_project_id(self, project_key):
        """从旧数据库查询 project_id"""
        if project_key in self.project_cache:
            return self.project_cache[project_key]
        
        if not self.old_db:
            logger.error(f"Old database not connected, cannot query project_id for {project_key}")
            return None
            
        try:
            with self.old_db.cursor() as cursor:
                sql = "SELECT id FROM taw_project WHERE project_key = %s"
                cursor.execute(sql, (project_key,))
                result = cursor.fetchone()
                if result:
                    project_id = result[0]
                    self.project_cache[project_key] = project_id
                    logger.info(f"Found project_id: {project_key} -> {project_id}")
                    return project_id
                else:
                    logger.warning(f"No project found for project_key: {project_key}")
        except Exception as e:
            logger.error(f"Failed to query project_id for {project_key}: {e}")
        
        return None
    
    def insert_release_file(self, project_id, project_key, version, file_key, file_name, file_size, file_hash):
        """插入文件记录到新数据库"""
        if not self.new_db:
            logger.error("New database not connected, cannot insert release file")
            return False
            
        try:
            with self.new_db.cursor() as cursor:
                sql = """
                    INSERT INTO taw_project_release_file 
                    (project_id, project_key, version, file_key, file_name, file_size, file_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    file_size = VALUES(file_size),
                    file_hash = VALUES(file_hash)
                """
                cursor.execute(sql, (project_id, project_key, version, file_key, file_name, file_size, file_hash))
            self.new_db.commit()
            logger.info(f"Inserted to DB: project_id={project_id}, file_key={file_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to insert release file: {e}")
            self.new_db.rollback()
            return False
    
    def copy_file(self, old_key, new_key):
        """复制文件从旧桶到新桶"""
        try:
            # 下载文件
            response = self.cos_client.get_object(Bucket=OLD_BUCKET, Key=old_key)
            content = response['Body'].get_raw_stream().read()
            file_size = len(content)
            file_hash = get_file_hash(content)
            
            # 上传到新桶
            self.cos_client.put_object(
                Bucket=NEW_BUCKET,
                Key=new_key,
                Body=content
            )
            
            return file_size, file_hash
        except Exception as e:
            logger.error(f"Failed to copy file {old_key} -> {new_key}: {e}")
            return None, None
    
    def migrate(self, dry_run=False):
        """执行迁移"""
        self.connect_db()
        
        marker = ''
        total_count = 0
        success_count = 0
        skip_count = 0
        fail_count = 0
        
        logger.info(f"Migrating files from prefix: {OLD_PREFIX}")
        
        try:
            while True:
                # 列出旧桶文件
                if marker:
                    response = self.cos_client.list_objects(
                        Bucket=OLD_BUCKET, Prefix=OLD_PREFIX, Marker=marker
                    )
                else:
                    response = self.cos_client.list_objects(
                        Bucket=OLD_BUCKET, Prefix=OLD_PREFIX
                    )
                
                contents = response.get('Contents', [])
                if not contents:
                    break
                
                logger.info(f"Processing batch of {len(contents)} files...")
                
                for item in contents:
                    total_count += 1
                    old_key = item['Key']
                    file_size_from_list = item.get('Size', 0)
                    
                    # 解析旧文件路径
                    project_key, file_name, timestamp, version = parse_old_file_path(old_key)
                    
                    if not project_key:
                        logger.warning(f"Skip: Cannot parse file path: {old_key}")
                        skip_count += 1
                        continue
                    
                    # 查询 project_id
                    project_id = self.get_project_id(project_key)
                    if not project_id:
                        logger.warning(f"Skip: project_key not found in database: {project_key}")
                        skip_count += 1
                        continue
                    
                    # 生成新文件路径
                    new_key = generate_new_file_key(project_id, version, timestamp, file_name)
                    
                    if dry_run:
                        logger.info(f"[DRY RUN] {old_key} -> {new_key}")
                        success_count += 1
                        continue
                    
                    # 复制文件
                    file_size, file_hash = self.copy_file(old_key, new_key)
                    if file_size is None:
                        fail_count += 1
                        continue
                    
                    # 写入数据库
                    if self.insert_release_file(
                        project_id, project_key, version, new_key, file_name, file_size, file_hash
                    ):
                        success_count += 1
                        logger.info(f"Migrated: {old_key} -> {new_key}")
                    else:
                        fail_count += 1
                    
                    # 每处理100个打印进度
                    if total_count % 100 == 0:
                        logger.info(f"Progress: {total_count} processed, {success_count} success, {skip_count} skip, {fail_count} fail")
                
                # 检查是否还有更多
                if not response.get('IsTruncated', False):
                    break
                marker = response.get('NextMarker', contents[-1]['Key'])
        
        finally:
            self.close_db()
        
        logger.info("=" * 50)
        logger.info(f"Migration completed!")
        logger.info(f"Total: {total_count}")
        logger.info(f"Success: {success_count}")
        logger.info(f"Skipped: {skip_count}")
        logger.info(f"Failed: {fail_count}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='COS File Migration Tool')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode, do not actually migrate')
    args = parser.parse_args()
    
    migrator = COSMigrator()
    migrator.migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
