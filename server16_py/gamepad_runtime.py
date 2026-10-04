from __future__ import annotations

import ctypes
from dataclasses import dataclass


XINPUT_GAMEPAD_DPAD_UP = 0x0001
XINPUT_GAMEPAD_DPAD_DOWN = 0x0002
XINPUT_GAMEPAD_DPAD_LEFT = 0x0004
XINPUT_GAMEPAD_DPAD_RIGHT = 0x0008
XINPUT_GAMEPAD_START = 0x0010
XINPUT_GAMEPAD_BACK = 0x0020
XINPUT_SUCCESS = 0


class _XInputGamepad(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class _XInputState(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.c_ulong),
        ("Gamepad", _XInputGamepad),
    ]


@dataclass(frozen=True)
class GamepadSample:
    index: int
    buttons: int
    left_x: int
    left_y: int


class XInputGamepadReader:
    """Small optional XInput reader used by the crowd-volume shortcut.

    It does not create a virtual controller, install a driver, or capture
    FIFA's input.  It only reads the state of the first connected XInput pad,
    so the existing gamepad and keyboard behavior remains untouched.
    """

    def __init__(self) -> None:
        self._get_state = None
        win_dll = getattr(ctypes, "WinDLL", None)
        if win_dll is None:
            return
        for dll_name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
            try:
                dll = win_dll(dll_name)
                get_state = dll.XInputGetState
                get_state.argtypes = [ctypes.c_uint, ctypes.POINTER(_XInputState)]
                get_state.restype = ctypes.c_uint
                self._get_state = get_state
                break
            except (AttributeError, OSError):
                continue

    @property
    def available(self) -> bool:
        return self._get_state is not None

    def poll(self) -> GamepadSample | None:
        if self._get_state is None:
            return None
        for index in range(4):
            state = _XInputState()
            try:
                result = int(self._get_state(index, ctypes.byref(state)))
            except Exception:
                continue
            if result != XINPUT_SUCCESS:
                continue
            return GamepadSample(
                index=index,
                buttons=int(state.Gamepad.wButtons),
                left_x=int(state.Gamepad.sThumbLX),
                left_y=int(state.Gamepad.sThumbLY),
            )
        return None
