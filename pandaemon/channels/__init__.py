"""Chat channels module with plugin architecture."""

from pandaemon.channels.base import BaseChannel
from pandaemon.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
