"""Fault domain: decodes fault code messages into ``FaultResult``."""

from protocol.fault.decoder import decode_fault
from protocol.fault.models import FaultCode, FaultResult

__all__ = ["FaultCode", "FaultResult", "decode_fault"]
