"""Scrapers cho các nguồn BĐS khác nhau."""

from .batdongsan import BatDongSanScraper
from .nhatot import NhaTotScraper
from .alonhadat import AloNhaDatScraper

__all__ = ["BatDongSanScraper", "NhaTotScraper", "AloNhaDatScraper"]
