"""Protocol layer: decodes complete messages into typed results, by message domain.

Each domain package (``telemetry``, ``fault``, ``diagnostic``) owns its decoder
and its result models. A decoder takes a complete ``Message`` and returns its
result, or raises ``protocol.common.ProtocolDecodeError`` when the message is
invalid. Decoders never route, touch sockets or transport state, update
application state, print, or serialize output.
"""
