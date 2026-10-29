"""Unit tests use fixtures/fakes and must never claim physical MIDI ports."""
import pytest
from lcxl.device import Device
from lcxl.transport import WinMidi


@pytest.fixture(autouse=True)
def offline_midi(monkeypatch):
    monkeypatch.setattr(Device,'discover',staticmethod(lambda:[]))
    def forbidden(*args,**kwargs):
        raise AssertionError('Physical MIDI ports are forbidden in unit tests.')
    monkeypatch.setattr(WinMidi,'open',forbidden)
