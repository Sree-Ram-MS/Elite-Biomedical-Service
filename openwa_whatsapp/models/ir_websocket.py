# -*- coding: utf-8 -*-
import logging
from odoo import models

_logger = logging.getLogger(__name__)


class IrWebsocket(models.AbstractModel):
    _inherit = 'ir.websocket'

    def _build_bus_channel_list(self, channels):
        channels = list(channels)
        for channel in list(channels):
            if isinstance(channel, str) and channel.startswith('openwa_channel'):
                # Check if it matches 'openwa_channel_<user_id>' where <user_id> is current user's ID
                # or if it's the general 'openwa_channel' (which doesn't contain sensitive user-specific data)
                if channel == 'openwa_channel':
                    # Check if user is logged in
                    if not self.env.uid:
                        channels.remove(channel)
                elif channel.startswith('openwa_channel_'):
                    try:
                        channel_uid = int(channel.split('_')[-1])
                        if channel_uid != self.env.uid:
                            channels.remove(channel)
                    except ValueError:
                        channels.remove(channel)
                else:
                    channels.remove(channel)
        return super()._build_bus_channel_list(channels)
