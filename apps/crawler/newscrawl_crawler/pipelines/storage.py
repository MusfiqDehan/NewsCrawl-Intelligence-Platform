"""Raw HTML storage: MinIO/S3 upload (raw HTML never touches PostgreSQL)."""

import asyncio
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from newscrawl_api.config import get_settings
from newscrawl_contracts.enums import UrlType
from scrapy import Spider

from newscrawl_crawler.items import PageItem


class RawHtmlStoragePipeline:
    """Uploads article HTML to object storage under a deterministic key.

    boto3 is synchronous; uploads run in a worker thread so the event loop
    never blocks on network I/O to MinIO.
    """

    def __init__(self) -> None:
        self._client: Any = None
        self.bucket: str = ""

    def open_spider(self, spider: Spider) -> None:
        settings = get_settings()
        self.bucket = settings.s3_bucket_raw_html
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=BotoConfig(connect_timeout=10, read_timeout=30, retries={"max_attempts": 3}),
        )
        # Defense in depth: ensure the raw-HTML bucket exists even if minio-init
        # was skipped (common cause of "crawlers run but no articles").
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception:  # noqa: BLE001 - botocore raises ClientError variants
            self._client.create_bucket(Bucket=self.bucket)

    async def process_item(self, item: PageItem, spider: Spider) -> PageItem:
        if item.url_type != UrlType.ARTICLE or not item.raw_html or item.not_modified:
            return item

        key = (
            f"raw/{item.source_slug}/{item.fetched_at:%Y/%m/%d}/"
            f"{item.url_id}-{item.fetched_at:%H%M%S}.html"
        )
        body = item.raw_html

        def upload() -> None:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType="text/html; charset=utf-8",
                Metadata={"url": item.normalized_url[:1024]},
            )

        await asyncio.to_thread(upload)
        item.raw_html_location = f"s3://{self.bucket}/{key}"
        item.raw_html = None  # free memory; downstream reads from object storage
        return item
