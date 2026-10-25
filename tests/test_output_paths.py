"""Output files are replaced via rename, never written through a pre-existing symlink."""

import os
import stat
import wave

import numpy as np
import pytest

import ds2_decoder as dec


SAMPLES = np.arange(-100, 100, dtype=np.int16)


def make_symlink_or_skip(link, target):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable on this platform: {exc}")


def leftover_temp_files(directory):
    return [name for name in os.listdir(directory) if name.endswith('.tmp')]


def test_write_wav_writes_readable_mono_file(tmp_path):
    out = tmp_path / "out.wav"

    dec.write_wav(str(out), SAMPLES, 12000)

    with wave.open(str(out), 'rb') as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 12000
        assert w.getnframes() == len(SAMPLES)
    assert leftover_temp_files(tmp_path) == []


def test_write_wav_replaces_symlink_instead_of_following_it(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("original")
    link = tmp_path / "out.wav"
    make_symlink_or_skip(str(link), str(target))

    dec.write_wav(str(link), SAMPLES, 12000)

    assert target.read_text() == "original"
    assert not os.path.islink(link)
    with wave.open(str(link), 'rb') as w:
        assert w.getnframes() == len(SAMPLES)


def test_encode_mp3_replaces_symlink_instead_of_following_it(tmp_path):
    pytest.importorskip("lameenc")
    pytest.importorskip("mutagen")
    target = tmp_path / "target.txt"
    target.write_text("original")
    link = tmp_path / "out_converted.mp3"
    make_symlink_or_skip(str(link), str(target))

    dec.encode_pcm_to_mp3(SAMPLES, 12000, str(link), metadata={'title': 'test'})

    assert target.read_text() == "original"
    assert not os.path.islink(link)
    assert os.path.getsize(link) > 0
    assert leftover_temp_files(tmp_path) == []


def test_failed_write_removes_temp_file_and_leaves_no_output(tmp_path, monkeypatch):
    out = tmp_path / "out.wav"

    def failing_replace(src, dst):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(dec.os, "replace", failing_replace)

    with pytest.raises(OSError, match="simulated"):
        dec.write_wav(str(out), SAMPLES, 12000)

    assert not out.exists()
    assert leftover_temp_files(tmp_path) == []


@pytest.fixture
def restore_umask():
    previous = os.umask(0o022)
    yield
    os.umask(previous)


def test_existing_output_mode_is_none_for_missing_path(tmp_path):
    assert dec._existing_output_mode(str(tmp_path / "new.wav")) is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_existing_output_mode_reports_regular_file_mode(tmp_path):
    existing = tmp_path / "out.wav"
    existing.write_bytes(b"old")
    os.chmod(existing, 0o640)

    assert dec._existing_output_mode(str(existing)) == 0o640


def test_existing_output_mode_ignores_symlink_target_mode(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("original")
    os.chmod(target, 0o600)
    link = tmp_path / "out.wav"
    make_symlink_or_skip(str(link), str(target))

    assert dec._existing_output_mode(str(link)) is None


def test_create_temp_beside_makes_new_unique_file_in_destination_dir(tmp_path):
    fd, first = dec._create_temp_beside(str(tmp_path / "out.wav"))
    os.close(fd)
    fd, second = dec._create_temp_beside(str(tmp_path / "out.wav"))
    os.close(fd)

    assert os.path.dirname(first) == str(tmp_path)
    assert first != second
    assert first.endswith('.tmp') and second.endswith('.tmp')


def test_create_temp_beside_retries_when_name_is_taken(tmp_path, monkeypatch):
    taken = tmp_path / ".ds2-aaaaaaaaaaaaaaaa.tmp"
    taken.write_bytes(b"not ours")
    tokens = iter(["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"])
    monkeypatch.setattr(dec.secrets, "token_hex", lambda n: next(tokens))

    fd, path = dec._create_temp_beside(str(tmp_path / "out.wav"))
    os.close(fd)

    assert path == str(tmp_path / ".ds2-bbbbbbbbbbbbbbbb.tmp")
    assert taken.read_bytes() == b"not ours"


def test_create_temp_beside_never_opens_an_existing_symlink(tmp_path, monkeypatch):
    target = tmp_path / "target.txt"
    target.write_text("original")
    planted = tmp_path / ".ds2-aaaaaaaaaaaaaaaa.tmp"
    make_symlink_or_skip(str(planted), str(target))
    tokens = iter(["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"])
    monkeypatch.setattr(dec.secrets, "token_hex", lambda n: next(tokens))

    fd, path = dec._create_temp_beside(str(tmp_path / "out.wav"))
    os.close(fd)

    assert target.read_text() == "original"
    assert path != str(planted)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_write_wav_new_file_gets_umask_default(tmp_path, restore_umask):
    os.umask(0o027)
    out = tmp_path / "out.wav"

    dec.write_wav(str(out), SAMPLES, 12000)

    assert stat.S_IMODE(os.stat(out).st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_write_wav_replacing_existing_file_keeps_its_mode(tmp_path, restore_umask):
    os.umask(0o077)
    out = tmp_path / "out.wav"
    out.write_bytes(b"old")
    os.chmod(out, 0o664)

    dec.write_wav(str(out), SAMPLES, 12000)

    assert stat.S_IMODE(os.stat(out).st_mode) == 0o664


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_encode_mp3_new_file_gets_umask_default(tmp_path, restore_umask):
    pytest.importorskip("lameenc")
    pytest.importorskip("mutagen")
    os.umask(0o027)
    out = tmp_path / "out_converted.mp3"

    dec.encode_pcm_to_mp3(SAMPLES, 12000, str(out), metadata={'title': 'test'})

    assert stat.S_IMODE(os.stat(out).st_mode) == 0o640
