"""Frame counts in block headers are clamped to what the payload can hold."""

import time

import pytest

import ds2_decoder as dec
from ds2_decoder import DS2Decoder
from ds2_fixtures import BLOCK_PAYLOAD_SIZE, QP_FORMAT, SP_FORMAT, make_ds2, random_payload


def write_ds2(tmp_path, data: bytes) -> str:
    path = tmp_path / "input.DS2"
    path.write_bytes(data)
    return str(path)


def test_sp_frame_count_255_in_one_small_block_is_clamped(tmp_path, capsys):
    # 506 payload bytes plus one partial 42-byte packet hold 13 SP frames.
    data = make_ds2([(255, random_payload(1))], SP_FORMAT)

    start = time.perf_counter()
    samples, _ = DS2Decoder().decode_file(write_ds2(tmp_path, data))
    elapsed = time.perf_counter() - start

    assert samples.shape == (13 * dec.SP_SAMPLES_PER_FRAME,)
    assert elapsed < 2.0
    assert "declares 255 frames but the payload holds 13" in capsys.readouterr().out


def test_sp_counts_that_are_plausible_per_block_but_overflow_in_total_are_clamped(tmp_path, capsys):
    # 5 blocks x 13 frames = 65 declared; the 2530-byte payload holds 62 frames.
    data = make_ds2([(13, random_payload(i)) for i in range(5)], SP_FORMAT)

    samples, _ = DS2Decoder().decode_file(write_ds2(tmp_path, data))

    assert samples.shape == (62 * dec.SP_SAMPLES_PER_FRAME,)
    assert "declares 65 frames but the payload holds 62" in capsys.readouterr().out


def test_sp_counts_within_payload_decode_without_warning(tmp_path, capsys):
    data = make_ds2([(12, random_payload(1))], SP_FORMAT)

    samples, header = DS2Decoder().decode_file(write_ds2(tmp_path, data))

    assert samples.shape == (12 * dec.SP_SAMPLES_PER_FRAME,)
    assert header.total_frames == 12
    assert capsys.readouterr().out == ""


def test_sp_counts_within_payload_decode(tmp_path):
    data = make_ds2([(12, random_payload(1))], SP_FORMAT)

    samples, header = DS2Decoder().decode_file(write_ds2(tmp_path, data))

    assert samples.shape == (12 * dec.SP_SAMPLES_PER_FRAME,)
    assert header.total_frames == 12


def test_sp_one_trailing_partial_frame_is_tolerated(tmp_path):
    # 13 frames need 534 bytes; one block holds 506, so the last frame is partial.
    data = make_ds2([(13, random_payload(1))], SP_FORMAT)

    samples, _ = DS2Decoder().decode_file(write_ds2(tmp_path, data))

    assert samples.shape == (13 * dec.SP_SAMPLES_PER_FRAME,)


def test_qp_frame_count_255_in_one_small_block_is_clamped(tmp_path, capsys):
    # 506 payload bytes plus one partial 56-byte frame hold 10 QP frames.
    data = make_ds2([(255, random_payload(1))], QP_FORMAT)

    samples, _ = DS2Decoder().decode_file(write_ds2(tmp_path, data))

    assert samples.shape == (10 * dec.QP_SAMPLES_PER_FRAME,)
    assert "declares 255 frames but the payload holds 10" in capsys.readouterr().out


def test_qp_counts_within_payload_decode(tmp_path):
    data = make_ds2([(9, random_payload(1))], QP_FORMAT)

    samples, _ = DS2Decoder().decode_file(write_ds2(tmp_path, data))

    assert samples.shape == (9 * dec.QP_SAMPLES_PER_FRAME,)


def test_qp_overflow_in_a_later_segment_is_clamped_per_segment(tmp_path, capsys):
    # Each block starts with byte1 == 0x03 after a non-0x04 block, so every block
    # becomes its own segment. The first holds 5 frames; the second declares 255
    # in 506 bytes and is clamped to 10.
    data = make_ds2([(5, random_payload(1)), (255, random_payload(2))], QP_FORMAT)

    samples, _ = DS2Decoder().decode_file(write_ds2(tmp_path, data))

    assert samples.shape == ((5 + 10) * dec.QP_SAMPLES_PER_FRAME,)
    assert "declares 260 frames but the payload holds 15" in capsys.readouterr().out


def test_qp_clamp_warns_once_when_decoder_starts_in_other_mode(tmp_path, capsys):
    # DS2Decoder() starts in SP mode, so a QP file triggers a mode switch.
    data = make_ds2([(255, random_payload(1))], QP_FORMAT)

    DS2Decoder().decode_file(write_ds2(tmp_path, data))

    assert capsys.readouterr().out.count("Warning") == 1


def test_sp_supported_frames_is_the_largest_count_that_fits():
    for first_swap in (0, 1):
        for available in range(0, 300):
            limit = available + dec.DSS_SP_PACKET_SIZE
            expected = max(n for n in range(0, 200) if dec._sp_packet_bytes(n, first_swap) <= limit)

            assert dec._sp_frames_supported(available, first_swap) == expected


def test_duration_cap_rejects_long_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(dec, "MAX_AUDIO_SECONDS", 0.01)
    data = make_ds2([(12, random_payload(1))], SP_FORMAT)

    with pytest.raises(ValueError, match="decode limit"):
        DS2Decoder().decode_file(write_ds2(tmp_path, data))


def test_zero_frame_file_decodes_to_empty_audio(tmp_path):
    data = make_ds2([(0, random_payload(1))], SP_FORMAT)

    samples, _ = DS2Decoder().decode_file(write_ds2(tmp_path, data))

    assert samples.dtype.name == "int16"
    assert samples.shape == (0,)


@pytest.mark.parametrize("first_swap", [0, 1])
@pytest.mark.parametrize("total_frames", range(0, 21))
def test_sp_packet_bytes_matches_demuxer_consumption(first_swap, total_frames):
    swap = first_swap
    consumed = 0
    for _ in range(total_frames):
        consumed += 40 if swap else 42
        swap ^= 1

    assert dec._sp_packet_bytes(total_frames, first_swap) == consumed


def _count_read_bits(monkeypatch):
    counted = {"bits": 0}
    original = dec.BitstreamReader.read_bits

    def counting_read_bits(self, n):
        counted["bits"] += max(n, 0)
        return original(self, n)

    monkeypatch.setattr(dec.BitstreamReader, "read_bits", counting_read_bits)
    return counted


def test_sp_frame_reads_exactly_frame_bits(monkeypatch):
    counted = _count_read_bits(monkeypatch)

    DS2Decoder("sp")._decode_sp_frames([bytes(dec.DSS_SP_PACKET_SIZE)], 1)

    assert counted["bits"] == dec.SP_FRAME_BITS


def test_qp_frame_reads_exactly_frame_bits(monkeypatch):
    counted = _count_read_bits(monkeypatch)

    DS2Decoder("qp")._decode_qp_frames([(bytes(506), 1)], 1)

    assert counted["bits"] == dec.QP_FRAME_BITS


@pytest.mark.parametrize("first_swap", [0, 1])
def test_sp_demux_accepts_every_count_at_the_payload_boundary(first_swap):
    # Sweeps counts up to the tolerance edge, where the last frame may start past
    # the end of the payload. The demuxer must still produce one packet per frame.
    limit = BLOCK_PAYLOAD_SIZE + dec.DSS_SP_PACKET_SIZE
    checked = 0
    for n in range(1, 40):
        if dec._sp_packet_bytes(n, first_swap) > limit:
            break
        data = make_ds2([(n, random_payload(n))], SP_FORMAT, first_block_byte0=first_swap << 7)

        frames, total, mode = dec.demux_ds2(data)

        assert (len(frames), total, mode) == (n, n, "sp")
        checked += 1
    assert checked > 0
