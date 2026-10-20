"""CoreAudio input devices and their hardware input gain (macOS, ctypes, no compile step).

Gain = the device's input volume control (`kAudioDevicePropertyVolumeScalar`, 0.0-1.0), the same
slider as System Settings > Sound > Input. Devices without a settable control (many USB mics with a
hardware knob) report `gain_elements == []`; callers must not fake gain by amplifying afterwards.
"""
from __future__ import annotations

import ctypes
import struct
from dataclasses import dataclass, field

_CA = ctypes.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
_CF = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")


def _fourcc(code: str) -> int:
    return int.from_bytes(code.encode(), "big")


SYSTEM_OBJECT = 1
DEVICES = _fourcc("dev#")
DEFAULT_INPUT = _fourcc("dIn ")
NAME = _fourcc("lnam")
UID = _fourcc("uid ")
STREAM_CONFIGURATION = _fourcc("slay")
VOLUME_SCALAR = _fourcc("volm")
VOLUME_DECIBELS = _fourcc("vold")
SCOPE_GLOBAL = _fourcc("glob")
SCOPE_INPUT = _fourcc("inpt")
ELEMENT_MAIN = 0
UTF8 = 0x08000100


class _Address(ctypes.Structure):
    _fields_ = [("selector", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("element", ctypes.c_uint32)]


_u32p = ctypes.POINTER(ctypes.c_uint32)
_CA.AudioObjectHasProperty.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Address)]
_CA.AudioObjectHasProperty.restype = ctypes.c_uint8
_CA.AudioObjectIsPropertySettable.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Address), ctypes.POINTER(ctypes.c_uint8)]
_CA.AudioObjectGetPropertyDataSize.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Address), ctypes.c_uint32,
                                               ctypes.c_void_p, _u32p]
_CA.AudioObjectGetPropertyData.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Address), ctypes.c_uint32,
                                           ctypes.c_void_p, _u32p, ctypes.c_void_p]
_CA.AudioObjectSetPropertyData.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Address), ctypes.c_uint32,
                                           ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
for _fn in ("AudioObjectIsPropertySettable", "AudioObjectGetPropertyDataSize", "AudioObjectGetPropertyData",
            "AudioObjectSetPropertyData"):
    getattr(_CA, _fn).restype = ctypes.c_int32
_CF.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
_CF.CFStringGetCString.restype = ctypes.c_bool
_CF.CFRelease.argtypes = [ctypes.c_void_p]


class CoreAudioError(RuntimeError):
    pass


def _get_bytes(obj: int, selector: int, scope: int = SCOPE_GLOBAL, element: int = ELEMENT_MAIN) -> bytes:
    address = _Address(selector, scope, element)
    size = ctypes.c_uint32(0)
    status = _CA.AudioObjectGetPropertyDataSize(obj, ctypes.byref(address), 0, None, ctypes.byref(size))
    if status:
        raise CoreAudioError(f"size of {selector:#x} on {obj}: status {status}")
    buffer = ctypes.create_string_buffer(size.value)
    status = _CA.AudioObjectGetPropertyData(obj, ctypes.byref(address), 0, None, ctypes.byref(size), buffer)
    if status:
        raise CoreAudioError(f"read {selector:#x} on {obj}: status {status}")
    return buffer.raw[:size.value]


def _get_string(obj: int, selector: int) -> str:
    ref = ctypes.c_void_p()
    address = _Address(selector, SCOPE_GLOBAL, ELEMENT_MAIN)
    size = ctypes.c_uint32(ctypes.sizeof(ref))
    status = _CA.AudioObjectGetPropertyData(obj, ctypes.byref(address), 0, None, ctypes.byref(size), ctypes.byref(ref))
    if status or not ref.value:
        return ""
    try:
        buffer = ctypes.create_string_buffer(1024)
        return buffer.value.decode() if _CF.CFStringGetCString(ref, buffer, 1024, UTF8) else ""
    finally:
        _CF.CFRelease(ref)


def _float(obj: int, selector: int, element: int) -> float:
    return struct.unpack("f", _get_bytes(obj, selector, SCOPE_INPUT, element))[0]


def _input_channels(obj: int) -> int:
    try:
        raw = _get_bytes(obj, STREAM_CONFIGURATION, SCOPE_INPUT)
    except CoreAudioError:
        return 0
    # AudioBufferList: UInt32 count, padding to 8, then 16-byte AudioBuffers starting with mNumberChannels.
    count = struct.unpack_from("I", raw)[0] if raw else 0
    return sum(struct.unpack_from("I", raw, 8 + 16 * index)[0] for index in range(count))


def _settable_volume(obj: int, element: int) -> bool:
    address = _Address(VOLUME_SCALAR, SCOPE_INPUT, element)
    if not _CA.AudioObjectHasProperty(obj, ctypes.byref(address)):
        return False
    settable = ctypes.c_uint8(0)
    return not _CA.AudioObjectIsPropertySettable(obj, ctypes.byref(address), ctypes.byref(settable)) and bool(settable.value)


@dataclass
class Device:
    id: int
    name: str
    uid: str
    channels: int
    # Main element if it carries the control, otherwise every channel element that does.
    gain_elements: list[int] = field(default_factory=list)

    @property
    def gain_supported(self) -> bool:
        return bool(self.gain_elements)

    def gains(self) -> dict[int, float]:
        return {element: _float(self.id, VOLUME_SCALAR, element) for element in self.gain_elements}

    def gain(self) -> float | None:
        values = list(self.gains().values())
        return sum(values) / len(values) if values else None

    def gain_db(self) -> float | None:
        """Device-reported dB for the current scalar (scalar-to-dB mapping is device-specific)."""
        try:
            values = [_float(self.id, VOLUME_DECIBELS, element) for element in self.gain_elements]
        except CoreAudioError:
            return None
        return sum(values) / len(values) if values else None

    def set_gains(self, values: dict[int, float]) -> None:
        for element, value in values.items():
            data = ctypes.c_float(min(1.0, max(0.0, value)))
            address = _Address(VOLUME_SCALAR, SCOPE_INPUT, element)
            status = _CA.AudioObjectSetPropertyData(self.id, ctypes.byref(address), 0, None, 4, ctypes.byref(data))
            if status:
                raise CoreAudioError(f"set gain on {self.name} element {element}: status {status}")

    def set_gain(self, value: float) -> float:
        if not self.gain_supported:
            raise CoreAudioError(f"{self.name} has no software-settable input gain (hardware knob or fixed level)")
        self.set_gains({element: value for element in self.gain_elements})
        return self.gain()


def _device(obj: int) -> Device:
    channels = _input_channels(obj)
    if _settable_volume(obj, ELEMENT_MAIN):
        elements = [ELEMENT_MAIN]
    else:
        elements = [element for element in range(1, channels + 1) if _settable_volume(obj, element)]
    return Device(obj, _get_string(obj, NAME), _get_string(obj, UID), channels, elements)


def input_devices() -> list[Device]:
    raw = _get_bytes(SYSTEM_OBJECT, DEVICES)
    ids = struct.unpack(f"{len(raw) // 4}I", raw)
    return [device for device in map(_device, ids) if device.channels > 0]


def default_input() -> Device:
    (obj,) = struct.unpack("I", _get_bytes(SYSTEM_OBJECT, DEFAULT_INPUT))
    return _device(obj)


def by_uid(uid: str) -> Device:
    for device in input_devices():
        if device.uid == uid:
            return device
    raise CoreAudioError(f"input device with uid {uid} is no longer connected")
