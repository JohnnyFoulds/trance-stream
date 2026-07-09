# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for --stream mode in trance_stream_v3.

All tests mock sounddevice so no audio hardware is required.

Key invariants verified:
1. Streaming audio is sample-identical to batch rendering (same seed).
2. WAV written bar-by-bar during streaming is valid and matches batch WAV.
3. No files are created when no paths are passed.
4. Files are created only when paths are explicitly provided.
5. Partial stream (KeyboardInterrupt mid-way) returns clean partial audio.
6. stream.write() is called once per bar (no merged/split writes that would
   cause silence gaps between bars on real hardware).
7. OutputStream is created WITHOUT a large blocksize (blocksize=spb would
   cause underruns — PortAudio would silence-fill before the next bar arrives).
"""

from __future__ import annotations

import sys
import pathlib
import wave
import unittest.mock as mock

import numpy as np
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

SR = 44100
BPM = 140.0
SPB = int(SR * 4 * 60 / BPM)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_renderer(seed: str = 'sunrise', n_bars: int = 8):
    from song.builder import build_song
    from song.renderer import SongRenderer
    song = build_song(seed, mood='uplifting', bpm=BPM, total_bars=n_bars)
    return SongRenderer(song), song


class _FakeStream:
    """Minimal sounddevice.OutputStream stand-in that captures written blocks."""
    def __init__(self, **kwargs):
        self.blocks = []
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        pass

    def write(self, data):
        self.blocks.append(data.copy())


def _mock_sd(fake_stream: _FakeStream):
    """Return a mock sounddevice module backed by the given fake stream."""
    sd = mock.MagicMock()
    sd.OutputStream.return_value = fake_stream
    return sd


def _captured_outputstream_kwargs(fake_stream: _FakeStream, mock_sd) -> dict:
    """Return the kwargs passed to sd.OutputStream(...)."""
    return mock_sd.OutputStream.call_args.kwargs


# ---------------------------------------------------------------------------
# OutputStream configuration — these catch the silence-between-bars bug
# ---------------------------------------------------------------------------

def test_outputstream_not_created_with_large_blocksize():
    """OutputStream must NOT be created with blocksize=spb.

    With blocksize=spb PortAudio drains its buffer then silence-fills while
    the next bar is being rendered — audible as a split-second of silence
    between every bar.  The fix is to omit blocksize (defaults to ~10ms)
    so stream.write() blocks until data is consumed.
    """
    from trance_stream_v3 import _stream_bars

    renderer, _ = _make_renderer('sunrise', n_bars=2)
    mock_sd = _mock_sd(_FakeStream())
    fake_stream = mock_sd.OutputStream.return_value

    with mock.patch.dict('sys.modules', {'sounddevice': mock_sd}):
        _stream_bars(renderer, 2, volume=1.0, wav_path=None)

    kwargs = mock_sd.OutputStream.call_args.kwargs
    blocksize = kwargs.get('blocksize', None)
    # Either not passed at all, or explicitly 0 (PortAudio default).
    assert blocksize is None or blocksize == 0, (
        f"OutputStream created with blocksize={blocksize}. "
        f"A large blocksize causes silence gaps between bars — must be 0 or omitted."
    )


def test_stream_write_called_once_per_bar():
    """stream.write() must be called exactly once per bar.

    Multiple write() calls per bar would break timing. Merging bars into a
    single write() would delay the start of audio by the full render time.
    """
    from trance_stream_v3 import _stream_bars

    n_bars = 4
    renderer, _ = _make_renderer('sunrise', n_bars=n_bars)
    fake_stream = _FakeStream()
    with mock.patch.dict('sys.modules', {'sounddevice': _mock_sd(fake_stream)}):
        _stream_bars(renderer, n_bars, volume=1.0, wav_path=None)

    assert len(fake_stream.blocks) == n_bars, (
        f"stream.write() called {len(fake_stream.blocks)} times for {n_bars} bars. "
        f"Must be called exactly once per bar."
    )


# ---------------------------------------------------------------------------
# Core correctness: streaming == batch
# ---------------------------------------------------------------------------

def test_stream_audio_matches_batch_render(tmp_path):
    """Audio produced by _stream_bars must be sample-identical to render_bars."""
    from trance_stream_v3 import _stream_bars

    # Batch render
    renderer_batch, _ = _make_renderer('sunrise', n_bars=8)
    l_batch, r_batch = renderer_batch.render_bars(8)

    # Stream render (same seed → same song)
    renderer_stream, _ = _make_renderer('sunrise', n_bars=8)
    fake_stream = _FakeStream()
    with mock.patch.dict('sys.modules', {'sounddevice': _mock_sd(fake_stream)}):
        l_stream, r_stream = _stream_bars(renderer_stream, 8, volume=1.0,
                                          wav_path=None)

    assert np.array_equal(l_batch, l_stream), \
        "Left channel differs between batch and stream render"
    assert np.array_equal(r_batch, r_stream), \
        "Right channel differs between batch and stream render"


def test_stream_blocks_sum_to_full_audio(tmp_path):
    """Blocks written to the audio device must reconstruct the full audio."""
    from trance_stream_v3 import _stream_bars

    renderer, _ = _make_renderer('forest', n_bars=6)
    fake_stream = _FakeStream()
    with mock.patch.dict('sys.modules', {'sounddevice': _mock_sd(fake_stream)}):
        l_out, r_out = _stream_bars(renderer, 6, volume=1.0, wav_path=None)

    # Each block is shape (SPB, 2) — L and R interleaved
    assert len(fake_stream.blocks) == 6, \
        f"Expected 6 blocks written to stream, got {len(fake_stream.blocks)}"

    reconstructed = np.concatenate(fake_stream.blocks, axis=0)
    assert np.array_equal(reconstructed[:, 0], l_out), \
        "Reconstructed L channel from stream blocks doesn't match returned L"
    assert np.array_equal(reconstructed[:, 1], r_out), \
        "Reconstructed R channel from stream blocks doesn't match returned R"


def test_stream_volume_applied():
    """Volume != 1.0 must scale the output uniformly."""
    from trance_stream_v3 import _stream_bars

    renderer_1, _ = _make_renderer('sunrise', n_bars=4)
    renderer_half, _ = _make_renderer('sunrise', n_bars=4)
    fake_1    = _FakeStream()
    fake_half = _FakeStream()

    with mock.patch.dict('sys.modules', {'sounddevice': _mock_sd(fake_1)}):
        l1, _ = _stream_bars(renderer_1,    4, volume=1.0, wav_path=None)
    with mock.patch.dict('sys.modules', {'sounddevice': _mock_sd(fake_half)}):
        lh, _ = _stream_bars(renderer_half, 4, volume=0.5, wav_path=None)

    np.testing.assert_allclose(lh, l1 * 0.5, rtol=1e-5,
                               err_msg="volume=0.5 did not halve the output")


# ---------------------------------------------------------------------------
# WAV output
# ---------------------------------------------------------------------------

def test_stream_writes_valid_wav_when_path_given(tmp_path):
    """_stream_bars must write a valid 16-bit stereo WAV when wav_path is set."""
    from trance_stream_v3 import _stream_bars

    wav_path = str(tmp_path / "stream_out.wav")
    renderer, song = _make_renderer('sunrise', n_bars=4)
    fake_stream = _FakeStream()
    with mock.patch.dict('sys.modules', {'sounddevice': _mock_sd(fake_stream)}):
        _stream_bars(renderer, 4, volume=1.0, wav_path=wav_path)

    assert pathlib.Path(wav_path).exists(), "WAV file not created"
    with wave.open(wav_path) as wf:
        assert wf.getnchannels() == 2,       "WAV must be stereo"
        assert wf.getframerate() == SR,       f"WAV sample rate must be {SR}"
        assert wf.getsampwidth() == 2,        "WAV must be 16-bit"
        assert wf.getnframes() == 4 * SPB,    \
            f"WAV frame count {wf.getnframes()} != {4 * SPB}"


def test_stream_wav_matches_batch_wav(tmp_path):
    """WAV written during streaming must be sample-equivalent to batch write_wav."""
    from trance_stream_v3 import _stream_bars

    # Batch path
    renderer_b, _ = _make_renderer('sunrise', n_bars=8)
    renderer_b.render_bars(8)
    batch_wav = str(tmp_path / "batch.wav")
    renderer_b.write_wav(batch_wav)

    # Stream path
    renderer_s, _ = _make_renderer('sunrise', n_bars=8)
    stream_wav = str(tmp_path / "stream.wav")
    fake_stream = _FakeStream()
    with mock.patch.dict('sys.modules', {'sounddevice': _mock_sd(fake_stream)}):
        _stream_bars(renderer_s, 8, volume=1.0, wav_path=stream_wav)

    # Compare raw PCM bytes
    with wave.open(batch_wav) as wf:
        batch_pcm = wf.readframes(wf.getnframes())
    with wave.open(stream_wav) as wf:
        stream_pcm = wf.readframes(wf.getnframes())

    assert batch_pcm == stream_pcm, \
        "Streaming WAV differs from batch WAV (same seed should be identical)"


def test_stream_wav_matches_batch_wav_with_volume(tmp_path):
    """WAV written during streaming at volume=0.7 must match batch WAV at volume=0.7.

    This catches a bug where batch write_wav() ignores volume because it reads
    from renderer._audio_l (unscaled), while stream WAV writes scaled audio.
    Both paths must produce the same output.
    """
    from trance_stream_v3 import _stream_bars
    import trance_stream_v3 as v3
    import wave as _wave

    n_bars = 4
    volume = 0.7

    # Batch path via main() so volume is applied to _audio_l before write_wav
    batch_wav = str(tmp_path / "batch_vol.wav")
    monkeypatch_sys = mock.patch.object(
        sys, 'argv',
        ['trance_stream_v3.py', '--bars', str(n_bars), '--seed', 'sunrise',
         '--volume', str(volume), '--wav', batch_wav]
    )
    with monkeypatch_sys:
        v3.main()

    # Stream path
    renderer_s, _ = _make_renderer('sunrise', n_bars=n_bars)
    stream_wav = str(tmp_path / "stream_vol.wav")
    fake_stream = _FakeStream()
    with mock.patch.dict('sys.modules', {'sounddevice': _mock_sd(fake_stream)}):
        _stream_bars(renderer_s, n_bars, volume=volume, wav_path=stream_wav)

    with _wave.open(batch_wav) as wf:
        batch_pcm = wf.readframes(wf.getnframes())
    with _wave.open(stream_wav) as wf:
        stream_pcm = wf.readframes(wf.getnframes())

    assert batch_pcm == stream_pcm, (
        "Batch WAV and stream WAV differ at volume != 1.0. "
        "write_wav() must use the volume-scaled audio."
    )


def test_stream_blocks_sent_to_device_match_wav(tmp_path):
    """Audio blocks sent to the sound device must be identical to what's in the WAV.

    The device gets float32 stereo; the WAV gets int16 stereo from the same data.
    Reconstructing float32 from the WAV PCM must match the device blocks.
    """
    from trance_stream_v3 import _stream_bars
    import wave as _wave

    n_bars = 3
    wav_path = str(tmp_path / "device_vs_wav.wav")
    renderer, _ = _make_renderer('sunrise', n_bars=n_bars)
    fake_stream = _FakeStream()
    with mock.patch.dict('sys.modules', {'sounddevice': _mock_sd(fake_stream)}):
        _stream_bars(renderer, n_bars, volume=1.0, wav_path=wav_path)

    # Reconstruct from WAV
    with _wave.open(wav_path) as wf:
        raw = wf.readframes(wf.getnframes())
    pcm = np.frombuffer(raw, dtype=np.int16).reshape(-1, 2).astype(np.float32) / 32767.0

    # Reconstruct from device blocks
    device = np.concatenate(fake_stream.blocks, axis=0)  # shape (N, 2)

    # PCM quantises to int16, so allow ±1 LSB tolerance
    tolerance = 1.0 / 32767.0
    diff = np.abs(pcm - device).max()
    assert diff <= tolerance, (
        f"Max difference between device audio and WAV audio: {diff:.6f} "
        f"(tolerance {tolerance:.6f}). What you hear must equal what's in the WAV."
    )


def test_stream_no_wav_when_no_path(tmp_path):
    """No WAV file must be written when wav_path=None."""
    from trance_stream_v3 import _stream_bars

    renderer, _ = _make_renderer('sunrise', n_bars=4)
    fake_stream = _FakeStream()
    with mock.patch.dict('sys.modules', {'sounddevice': _mock_sd(fake_stream)}):
        _stream_bars(renderer, 4, volume=1.0, wav_path=None)

    wav_files = list(tmp_path.glob("*.wav"))
    assert wav_files == [], f"Unexpected WAV files created: {wav_files}"


# ---------------------------------------------------------------------------
# Partial stream (KeyboardInterrupt)
# ---------------------------------------------------------------------------

def test_stream_keyboard_interrupt_returns_partial_audio():
    """KeyboardInterrupt mid-stream must return partial audio cleanly (no crash)."""
    from trance_stream_v3 import _stream_bars

    n_bars = 8
    interrupt_after = 3  # interrupt after 3 bars

    renderer, _ = _make_renderer('sunrise', n_bars=n_bars)

    call_count = [0]
    original_render_bar = renderer._render_bar

    def patched_render_bar():
        call_count[0] += 1
        if call_count[0] > interrupt_after:
            raise KeyboardInterrupt
        return original_render_bar()

    renderer._render_bar = patched_render_bar

    fake_stream = _FakeStream()
    with mock.patch.dict('sys.modules', {'sounddevice': _mock_sd(fake_stream)}):
        l_out, r_out = _stream_bars(renderer, n_bars, volume=1.0, wav_path=None)

    assert len(l_out) == interrupt_after * SPB, \
        f"Partial audio length {len(l_out)} != {interrupt_after * SPB}"
    assert fake_stream.stopped, "Stream must be stopped after KeyboardInterrupt"


def test_stream_keyboard_interrupt_closes_wav(tmp_path):
    """A partial stream must still produce a valid (partial) WAV file."""
    from trance_stream_v3 import _stream_bars

    wav_path = str(tmp_path / "partial.wav")
    interrupt_after = 2

    renderer, _ = _make_renderer('sunrise', n_bars=8)
    call_count = [0]
    original = renderer._render_bar

    def patched():
        call_count[0] += 1
        if call_count[0] > interrupt_after:
            raise KeyboardInterrupt
        return original()

    renderer._render_bar = patched

    fake_stream = _FakeStream()
    with mock.patch.dict('sys.modules', {'sounddevice': _mock_sd(fake_stream)}):
        _stream_bars(renderer, 8, volume=1.0, wav_path=wav_path)

    assert pathlib.Path(wav_path).exists(), "Partial WAV not written on interrupt"
    with wave.open(wav_path) as wf:
        assert wf.getnchannels() == 2
        assert wf.getnframes() == interrupt_after * SPB, \
            f"Partial WAV has {wf.getnframes()} frames, expected {interrupt_after * SPB}"


# ---------------------------------------------------------------------------
# sounddevice unavailable fallback
# ---------------------------------------------------------------------------

def test_stream_fallback_when_sounddevice_missing():
    """If sounddevice is not installed, _stream_bars must fall back gracefully."""
    from trance_stream_v3 import _stream_bars

    renderer, _ = _make_renderer('sunrise', n_bars=4)

    # Simulate sounddevice not installed by raising ImportError on import
    with mock.patch.dict('sys.modules', {'sounddevice': None}):
        l_out, r_out = _stream_bars(renderer, 4, volume=1.0, wav_path=None)

    assert len(l_out) == 4 * SPB, \
        f"Fallback render returned wrong length: {len(l_out)}"
    assert l_out.dtype == np.float32


# ---------------------------------------------------------------------------
# CLI argument behaviour (no audio device needed)
# ---------------------------------------------------------------------------

def test_cli_stream_no_default_files(tmp_path, monkeypatch):
    """Running --stream must not write any files unless --wav/--out-midi given."""
    import trance_stream_v3 as v3

    written_paths = []

    def fake_stream_bars(renderer, n_bars, volume, wav_path):
        if wav_path:
            written_paths.append(wav_path)
        l = np.zeros(n_bars * SPB, dtype=np.float32)
        r = np.zeros(n_bars * SPB, dtype=np.float32)
        renderer._audio_l = [l[i*SPB:(i+1)*SPB] for i in range(n_bars)]
        renderer._audio_r = [r[i*SPB:(i+1)*SPB] for i in range(n_bars)]
        return l, r

    monkeypatch.setattr(v3, '_stream_bars', fake_stream_bars)
    monkeypatch.setattr(sys, 'argv', [
        'trance_stream_v3.py', '--stream', '--bars', '4', '--seed', 'sunrise'
    ])

    v3.main()

    assert written_paths == [], \
        f"--stream without --wav must not write files; got {written_paths}"


def test_cli_stream_writes_wav_when_requested(tmp_path, monkeypatch):
    """Running --stream --wav <path> must pass that path to _stream_bars."""
    import trance_stream_v3 as v3

    captured_wav = []

    def fake_stream_bars(renderer, n_bars, volume, wav_path):
        captured_wav.append(wav_path)
        l = np.zeros(n_bars * SPB, dtype=np.float32)
        r = np.zeros(n_bars * SPB, dtype=np.float32)
        renderer._audio_l = [l[i*SPB:(i+1)*SPB] for i in range(n_bars)]
        renderer._audio_r = [r[i*SPB:(i+1)*SPB] for i in range(n_bars)]
        return l, r

    wav_out = str(tmp_path / "out.wav")
    monkeypatch.setattr(v3, '_stream_bars', fake_stream_bars)
    monkeypatch.setattr(sys, 'argv', [
        'trance_stream_v3.py', '--stream', '--bars', '4',
        '--seed', 'sunrise', '--wav', wav_out
    ])

    v3.main()

    assert captured_wav == [wav_out], \
        f"Expected wav_path={wav_out!r}, got {captured_wav}"


def test_cli_no_stream_writes_default_wav(tmp_path, monkeypatch):
    """Non-stream mode must write WAV to /tmp/trance_v3.wav by default."""
    import trance_stream_v3 as v3

    written = []
    original_write_wav = None

    from song.renderer import SongRenderer

    orig_init = SongRenderer.__init__

    def patched_init(self, song):
        orig_init(self, song)
        self._test_written = written

    def patched_write_wav(self, path):
        written.append(path)

    monkeypatch.setattr(SongRenderer, 'write_wav', patched_write_wav)
    monkeypatch.setattr(sys, 'argv', [
        'trance_stream_v3.py', '--bars', '4', '--seed', 'sunrise'
    ])

    v3.main()

    assert any(p == '/tmp/trance_v3.wav' for p in written), \
        f"Expected default WAV path '/tmp/trance_v3.wav' in {written}"
