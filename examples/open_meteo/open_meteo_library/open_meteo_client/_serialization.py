"""Serialization wiring (msgspec)."""

from unihttp.serializers.msgspec import MsgspecDumper, MsgspecLoader

from open_meteo_client._forward_refs import resolve_forward_refs

resolve_forward_refs()

request_dumper = MsgspecDumper()
response_loader = MsgspecLoader()
