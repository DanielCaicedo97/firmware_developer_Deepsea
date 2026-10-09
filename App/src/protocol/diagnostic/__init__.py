"""Diagnostic domain: decodes reassembled identification strings into ``DiagnosticResult``."""

from protocol.diagnostic.decoder import decode_diagnostic
from protocol.diagnostic.models import DiagnosticResult

__all__ = ["DiagnosticResult", "decode_diagnostic"]
