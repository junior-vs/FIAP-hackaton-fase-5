"""Worker package for async RabbitMQ message processing."""

from __future__ import annotations

from ai_module.worker.consumer import MessageConsumer, ResultPublisher

__all__ = ["MessageConsumer", "ResultPublisher"]
