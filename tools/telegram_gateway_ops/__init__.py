"""Telegram Gateway observability helpers."""

from .status import build_gateway_ops_status, collect_gateway_ops

__all__ = ["build_gateway_ops_status", "collect_gateway_ops"]
