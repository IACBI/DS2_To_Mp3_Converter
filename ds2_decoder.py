#!/usr/bin/env python3
"""
DS2 Decoder Module — Core codec implementation
================================================
Decodes DS2 (Olympus DSS Pro) audio files to raw PCM, then encodes to MP3.

The DS2 codec was reverse-engineered from Olympus's DssDecoder.dll by
the hirparak/dss-codec project (MIT license). This implementation is
a clean-room Python/NumPy port with full type hints and documentation.

DS2 supports two modes:
  SP (Standard Play): 12000 Hz, mono, 14 reflection coefficients, 328-bit frames
  QP (Quality Play):  16000 Hz, mono, 16 reflection coefficients, 448-bit frames

Both use a CELP (Code-Excited Linear Prediction) architecture with:
  - Normalized lattice synthesis filter (NOT standard LPC)
  - Combinatorial codebook for sparse pulse excitation
  - Adaptive pitch excitation with gain
  - Quantized reflection coefficient codebooks extracted from DLL

Dependencies: numpy, lameenc, mutagen
"""

import math
import struct
import wave
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field

import numpy as np

# =============================================================================
# DS2 Format Constants
# =============================================================================

# --- File structure ---
DS2_MAGIC = b'\x03ds2'
DS2_HEADER_SIZE = 0x600  # 1536 bytes
DS2_BLOCK_SIZE = 512     # Each audio data block
DS2_BLOCK_HEADER_SIZE = 6  # Per-block header bytes

# --- SP Mode (Standard Play) constants ---
SP_SAMPLE_RATE = 12000
SP_NUM_COEFFS = 14       # Number of reflection coefficients
SP_NUM_SUBFRAMES = 4     # Subframes per frame
SP_SUBFRAME_SIZE = 72    # Samples per subframe
SP_SAMPLES_PER_FRAME = SP_NUM_SUBFRAMES * SP_SUBFRAME_SIZE  # 288
SP_FRAME_BITS = 328      # Total bits per compressed frame
SP_MIN_PITCH = 36
SP_MAX_PITCH = 186
SP_PITCH_RANGE = SP_MAX_PITCH - SP_MIN_PITCH + 1  # 151
SP_PITCH_DELTA_RANGE = 48
SP_EXCITATION_PULSES = 7
# Bit allocation for reflection coefficient indices
SP_REFL_BIT_ALLOC = [5, 5, 4, 4, 4, 4, 4, 4, 3, 3, 3, 3, 3, 3]  # sum=52
SP_PITCH_GAIN_BITS = 5
SP_GAIN_BITS = 6
SP_PULSE_BITS = 3
SP_COMBINED_PITCH_BITS = math.ceil(math.log2(
    SP_PITCH_RANGE * (SP_PITCH_DELTA_RANGE ** (SP_NUM_SUBFRAMES - 1))
))  # = 24
DSS_SP_PACKET_SIZE = 42  # Bytes per demuxed SP packet

# --- QP Mode (Quality Play) constants ---
QP_SAMPLE_RATE = 16000
QP_NUM_COEFFS = 16
QP_NUM_SUBFRAMES = 4
QP_SUBFRAME_SIZE = 64
QP_SAMPLES_PER_FRAME = QP_NUM_SUBFRAMES * QP_SUBFRAME_SIZE  # 256
QP_FRAME_BITS = 448
QP_MIN_PITCH = 45
QP_MAX_PITCH = 300
QP_PITCH_RANGE = QP_MAX_PITCH - QP_MIN_PITCH + 1  # 256
QP_PITCH_DELTA_RANGE = 256
QP_EXCITATION_PULSES = 11
QP_REFL_BIT_ALLOC = [7, 7, 6, 6, 5, 5, 5, 5, 5, 4, 4, 4, 4, 3, 3, 3]  # sum=76
QP_PITCH_GAIN_BITS = 6
QP_GAIN_BITS = 6
QP_PULSE_BITS = 3
QP_PITCH_BITS_PER_SUBFRAME = 8

# =============================================================================
# Quantization Tables (extracted from DssDecoder.dll via Ghidra)
# =============================================================================

# SP Pitch prediction gain (5-bit, 32 entries)
SP_PITCH_GAIN_TABLE: List[float] = [
    0.049805, 0.112793, 0.175781, 0.238281, 0.301270, 0.364258, 0.427246, 0.490234,
    0.553223, 0.615723, 0.678711, 0.741699, 0.804688, 0.867676, 0.930176, 0.993164,
    1.056152, 1.119141, 1.182129, 1.245117, 1.307617, 1.370605, 1.433594, 1.496582,
    1.559570, 1.622559, 1.685059, 1.748047, 1.811035, 1.874023, 1.937012, 2.000000,
]

# SP Excitation gain (6-bit, 64 entries)
SP_EXCITATION_GAIN_TABLE: List[float] = [
       0,    4,    8,   13,   17,   22,   26,   31,   35,   40,
      44,   48,   53,   58,   63,   69,   76,   83,   91,   99,
     109,  119,  130,  142,  155,  170,  185,  203,  222,  242,
     265,  290,  317,  346,  378,  414,  452,  494,  540,  591,
     646,  706,  771,  843,  922, 1007, 1101, 1204, 1316, 1438,
    1572, 1719, 1879, 2053, 2244, 2453, 2682, 2931, 3204, 3502,
    3828, 4184, 4574, 5000,
]

# SP/QP shared pulse amplitude table (3-bit, 8 entries)
PULSE_AMP_TABLE: List[float] = [
    -0.951599, -0.679718, -0.407837, -0.135956,
     0.135956,  0.407837,  0.679718,  0.951599,
]

# QP Pitch prediction gain (6-bit, 64 entries)
QP_PITCH_GAIN_TABLE: List[float] = [
    0.004913, 0.056367, 0.102669, 0.145092, 0.184286, 0.220170, 0.252640, 0.281841,
    0.308202, 0.332237, 0.354531, 0.375491, 0.395460, 0.414675, 0.433337, 0.451622,
    0.469648, 0.487486, 0.505255, 0.523016, 0.540824, 0.558764, 0.576890, 0.595276,
    0.613963, 0.632917, 0.652245, 0.671900, 0.691902, 0.712322, 0.733015, 0.753909,
    0.774967, 0.796116, 0.817233, 0.838156, 0.858900, 0.879346, 0.899405, 0.919040,
    0.938366, 0.957462, 0.976668, 0.996526, 1.017693, 1.041066, 1.066882, 1.095219,
    1.126158, 1.159959, 1.196753, 1.236515, 1.279487, 1.325996, 1.376201, 1.429902,
    1.487140, 1.548301, 1.613491, 1.682657, 1.755914, 1.833605, 1.914886, 1.999406,
]

# QP Excitation gain (6-bit, 64 entries)
QP_EXCITATION_GAIN_TABLE: List[float] = [
      3.928,   7.069,  10.993,  16.465,  23.856,  32.753,  42.893,  54.076,
     66.160,  79.016,  92.493, 106.558, 121.106, 136.128, 151.663, 167.700,
    184.251, 201.424, 219.212, 237.740, 257.014, 277.134, 298.164, 320.054,
    342.913, 366.849, 391.851, 418.102, 445.564, 474.334, 504.476, 536.280,
    569.771, 604.926, 642.050, 681.112, 722.397, 766.071, 812.234, 861.189,
    913.161, 968.356, 1027.220, 1089.687, 1156.595, 1228.228, 1305.279, 1387.811,
    1476.597, 1572.636, 1675.856, 1789.017, 1911.832, 2045.863, 2194.195, 2360.133,
    2545.084, 2752.592, 2991.921, 3271.340, 3603.855, 4004.808, 4476.587, 4970.296,
]

# QP Pulse amplitude table (3-bit, 8 entries) — asymmetric, differs from SP
QP_PULSE_AMP_TABLE: List[float] = [
    -0.921705, -0.628998, -0.397315, -0.140886,
     0.206959,  0.433678,  0.652927,  0.931249,
]


# =============================================================================
# DS2 Header Parser
# =============================================================================

@dataclass
class DS2Header:
    """Parsed DS2 file header metadata."""
    magic: bytes
    device_model: str
    file_id: int
    creation_timestamp: str
    modification_timestamp: str
    duration_str: str
    duration_seconds: int
    serial_number: str
    author: str
    work_type: str
    memo: str
    codec_mode: int  # 0=SP, 6=QP
    sample_rate: int
    total_frames: int
    audio_data_offset: int = DS2_HEADER_SIZE
    audio_data_size: int = 0

    @property
    def creation_datetime(self) -> str:
        """Parse YYMMDDHHMMSS to readable format."""
        try:
            ts = self.creation_timestamp
            return f"20{ts[0:2]}-{ts[2:4]}-{ts[4:6]} {ts[6:8]}:{ts[8:10]}:{ts[10:12]}"
        except (IndexError, ValueError):
            return self.creation_timestamp


def parse_ds2_header(data: bytes) -> DS2Header:
    """
    Parse the 1536-byte DS2 file header.

    Header layout (based on binary analysis):
      0x0000: 03 64 73 32   — Magic bytes (\\x03ds2)
      0x0004: 02 00 03 00   — Version/sub-version
      0x0008: 03 00 00 00   — Unknown
      0x000C: Device model   — Null-terminated string (e.g., "DPM 6000")
      0x001C: File ID        — 2-byte LE (e.g., 5018)
      0x0026: Creation TS    — 12 ASCII digits YYMMDDHHMMSS
      0x0032: Modification TS — 12 ASCII digits YYMMDDHHMMSS
      0x003E: Duration       — 6 ASCII digits HHMMSS
      0x0200: Second header section
      0x0202: 2-byte LE      — Related to sample rate (6000 for device)
      0x0204: Serial number  — 12 ASCII bytes
      0x0210: Codec info byte
      0x0212: 4-byte LE      — Total duration in ms (approx)
      0x0240: Author         — Null-terminated, 32-byte slot
      0x025E: Device ID      — Null-terminated, 32-byte slot
      0x027C: Work type      — Null-terminated, 32-byte slot
      0x029A: Memo           — Null-terminated, 32-byte slot
      0x0600: Audio data starts
    """
    if len(data) < DS2_HEADER_SIZE:
        raise ValueError(f"File too small for DS2 header: {len(data)} bytes")

    magic = data[:4]
    if magic != DS2_MAGIC:
        raise ValueError(f"Invalid DS2 magic: {magic.hex()} (expected 03647332)")

    def read_null_str(offset: int, max_len: int) -> str:
        """Read a null-terminated string from offset."""
        end = data.index(0, offset, offset + max_len) if 0 in data[offset:offset + max_len] else offset + max_len
        return data[offset:end].decode('ascii', errors='replace').strip('\x00\xff')

    device_model = read_null_str(0x0C, 16)
    file_id = struct.unpack_from('<H', data, 0x1C)[0]
    creation_ts = data[0x26:0x32].decode('ascii', errors='replace')
    modification_ts = data[0x32:0x3E].decode('ascii', errors='replace')
    duration_str = data[0x3E:0x44].decode('ascii', errors='replace')

    # Parse duration HHMMSS
    try:
        hh, mm, ss = int(duration_str[0:2]), int(duration_str[2:4]), int(duration_str[4:6])
        duration_secs = hh * 3600 + mm * 60 + ss
    except (ValueError, IndexError):
        duration_secs = 0

    serial = data[0x204:0x210].decode('ascii', errors='replace')
    author = read_null_str(0x240, 30)
    work_type = read_null_str(0x27C, 30)
    memo = read_null_str(0x29A, 30)

    # Detect codec mode from first audio block header byte 4
    codec_mode = data[DS2_HEADER_SIZE + 4] if len(data) > DS2_HEADER_SIZE + 5 else 0
    sample_rate = QP_SAMPLE_RATE if codec_mode >= 6 else SP_SAMPLE_RATE

    # Count total frames from all block headers
    num_blocks = (len(data) - DS2_HEADER_SIZE) // DS2_BLOCK_SIZE
    total_frames = 0
    for bi in range(num_blocks):
        block_offset = DS2_HEADER_SIZE + bi * DS2_BLOCK_SIZE
        if block_offset + 3 <= len(data):
            total_frames += data[block_offset + 2]

    audio_data_size = len(data) - DS2_HEADER_SIZE

    return DS2Header(
        magic=magic,
        device_model=device_model,
        file_id=file_id,
        creation_timestamp=creation_ts,
        modification_timestamp=modification_ts,
        duration_str=duration_str,
        duration_seconds=duration_secs,
        serial_number=serial,
        author=author,
        work_type=work_type,
        memo=memo,
        codec_mode=codec_mode,
        sample_rate=sample_rate,
        total_frames=total_frames,
        audio_data_size=audio_data_size,
    )


# =============================================================================
# Bitstream Reader
# =============================================================================

class BitstreamReader:
    """
    MSB-first bitstream reader for 16-bit little-endian words.

    This matches the DssDecoder.dll function FUN_10017460:
    - Read 16-bit words in little-endian byte order
    - Within each word, consume bits from MSB (bit 15) to LSB (bit 0)
    - Fields span word boundaries seamlessly

    Both SP and QP codecs use this same bitstream reader.
    """

    def __init__(self, data: bytes) -> None:
        self.data: bytes = data
        self.word_index: int = 0  # Index of next 16-bit word to load
        self.mask: int = 0        # Current bit mask within word (0 = need new word)
        self.current_word: int = 0

    def _load_next_word(self) -> None:
        """Load the next 16-bit word in little-endian order."""
        offset = self.word_index * 2
        if offset + 1 < len(self.data):
            # Little-endian: low byte first
            self.current_word = self.data[offset] | (self.data[offset + 1] << 8)
        else:
            self.current_word = 0
        self.word_index += 1

    def read_bits(self, n: int) -> int:
        """
        Read n bits from the bitstream, MSB first.

        Returns an integer with the read bits right-aligned.
        """
        if n <= 0:
            return 0

        result = 0
        result_mask = 1 << (n - 1)  # Start writing from MSB of result

        for _ in range(n):
            # Advance to next bit position
            if self.mask == 0:
                # Need to load first word
                self.mask = 0x8000
                self._load_next_word()
            else:
                self.mask >>= 1
                if self.mask == 0:
                    # Word exhausted, load next
                    self.mask = 0x8000
                    self._load_next_word()

            # Read current bit
            if self.current_word & self.mask:
                result |= result_mask
            result_mask >>= 1

        return result


# =============================================================================
# DS2 Demuxer
# =============================================================================

def demux_ds2(data: bytes) -> Tuple[Any, int, str]:
    """
    Read DS2 file and extract audio frame data.

    SP mode (codec byte 0-1): Uses byte-swap alternation demuxing.
      Returns list of 42-byte packets, one per frame.

    QP mode (codec byte 6-7): Continuous bitstream.
      Returns single bytes object containing concatenated 506-byte payloads.

    Returns:
        (frame_data, total_frames, mode_str)
        - mode_str is 'sp' or 'qp'
    """
    if data[:4] != DS2_MAGIC:
        raise ValueError(f"Not a DS2 file (magic: {data[:4].hex()})")

    num_blocks = (len(data) - DS2_HEADER_SIZE) // DS2_BLOCK_SIZE
    if num_blocks <= 0:
        raise ValueError("DS2 file has no audio data blocks")

    # Detect format from first block header byte 4
    format_type = data[DS2_HEADER_SIZE + 4]

    # Count total frames from all block headers (byte 2 of each block)
    total_frames = 0
    for bi in range(num_blocks):
        total_frames += data[DS2_HEADER_SIZE + bi * DS2_BLOCK_SIZE + 2]

    if format_type >= 6:
        # QP mode: continuous bitstream, segmented by recording pauses
        segments = []
        current_stream = bytearray()
        current_frames = 0
        prev_byte1 = -1
        
        for bi in range(num_blocks):
            bstart = DS2_HEADER_SIZE + bi * DS2_BLOCK_SIZE
            b1 = data[bstart + 1]
            b2 = data[bstart + 2]
            
            # A new cycle starts with byte1 = 0x03. If the previous block wasn't
            # the natural end of a cycle (0x04), a pause/edit occurred.
            if current_stream and b1 == 0x03 and prev_byte1 != 0x04:
                segments.append((bytes(current_stream), current_frames))
                current_stream = bytearray()
                current_frames = 0
                
            current_stream.extend(data[bstart + DS2_BLOCK_HEADER_SIZE : bstart + DS2_BLOCK_SIZE])
            current_frames += b2
            prev_byte1 = b1
            
        if current_stream:
            segments.append((bytes(current_stream), current_frames))
            
        return segments, total_frames, 'qp'
    else:
        # SP mode: byte-swap alternation demuxing
        
        stream = bytearray()
        for bi in range(num_blocks):
            bstart = DS2_HEADER_SIZE + bi * DS2_BLOCK_SIZE
            stream.extend(data[bstart + DS2_BLOCK_HEADER_SIZE : bstart + DS2_BLOCK_SIZE])
            
        # Initialize swap state from bit 7 of first block's byte0
        swap = (data[DS2_HEADER_SIZE] >> 7) & 1
        swap_byte = 0
        pos = 0
        frame_packets: List[bytes] = []

        for fi in range(total_frames):
            pkt = bytearray(DSS_SP_PACKET_SIZE + 1)

            if swap:
                # Swap frame: read 40 bytes into pkt[3..43],
                # then shift even-indexed bytes
                read_size = 40
                end = min(pos + read_size, len(stream))
                pkt[3:3 + (end - pos)] = stream[pos:end]
                pos += read_size

                # Shift even-indexed bytes: pkt[i] = pkt[i+4] for i in 0,2,4,...,40
                for i in range(0, DSS_SP_PACKET_SIZE - 2, 2):
                    pkt[i] = pkt[i + 4]
                pkt[DSS_SP_PACKET_SIZE] = 0
                pkt[1] = swap_byte
            else:
                # No-swap frame: read 42 bytes directly
                read_size = DSS_SP_PACKET_SIZE
                end = min(pos + read_size, len(stream))
                pkt[:end - pos] = stream[pos:end]
                pos += read_size
                swap_byte = pkt[DSS_SP_PACKET_SIZE - 2]

            # Zero out byte at position 40 before decoding
            pkt[DSS_SP_PACKET_SIZE - 2] = 0
            swap ^= 1
            frame_packets.append(bytes(pkt[:DSS_SP_PACKET_SIZE]))

        return frame_packets, total_frames, 'sp'


# =============================================================================
# Codec Algorithms
# =============================================================================

def load_codebook(path: str, num_coeffs: int) -> List[np.ndarray]:
    """
    Load per-coefficient reflection codebook vectors from .npz file.

    Each codebook[i] is a 1D array of f64 values. The index read from
    the bitstream selects one entry as the dequantized reflection coefficient.
    """
    data = np.load(path)
    codebook = [data[f'coeff_{i}'] for i in range(num_coeffs)]

    # SP coeff_13 fix: the DLL only has 4 entries but we need 8 (3-bit index)
    # Use the FFmpeg DSS SP row 13 table as fallback
    if num_coeffs == 14 and len(codebook[13]) < 8:
        ffmpeg_row13 = np.array(
            [-11239, -7220, -4040, -1406, 971, 3321, 6006, 9697],
            dtype=np.float64
        ) / 32768
        codebook[13] = ffmpeg_row13

    return codebook


def dequantize_reflection_coeffs(indices: List[int], codebook: List[np.ndarray],
                                  num_coeffs: int) -> np.ndarray:
    """Look up reflection coefficients from codebook indices."""
    coeffs = np.zeros(num_coeffs, dtype=np.float64)
    for i in range(num_coeffs):
        idx = indices[i]
        cb = codebook[i]
        coeffs[i] = cb[min(idx, len(cb) - 1)]
    return coeffs


def lattice_synthesis(excitation: np.ndarray, coeffs: np.ndarray,
                      state: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Normalized lattice synthesis filter.

    Matches DssDecoder.dll FUN_10019d40. This is NOT a standard LPC filter —
    it operates directly on reflection coefficients using a lattice structure.

    The lattice filter processes the excitation signal through P stages,
    where P is the number of reflection coefficients. Each stage applies:
      acc = acc - state[k] * coeffs[k]
      state[k+1] = coeffs[k] * acc + state[k]

    Args:
        excitation: Input excitation signal (subframe_size samples)
        coeffs: Reflection coefficients (P values)
        state: Persistent filter state (P values, modified in-place conceptually)

    Returns:
        (output, new_state): Filtered output samples and updated state
    """
    P = len(coeffs)
    temp = state.copy()
    output = np.zeros(len(excitation), dtype=np.float64)

    for n in range(len(excitation)):
        # Start with excitation minus last stage contribution
        acc = excitation[n] - temp[P - 1] * coeffs[P - 1]
        # Process lattice stages from P-2 down to 0
        for k in range(P - 2, -1, -1):
            acc -= temp[k] * coeffs[k]
            temp[k + 1] = coeffs[k] * acc + temp[k]
        temp[0] = acc
        output[n] = acc

    return output, temp.copy()


def decode_combined_pitch(combined: int, pitch_range: int, min_pitch: int,
                          delta_range: int, num_subframes: int) -> List[int]:
    """
    Decode SP combined pitch value into per-subframe pitch lags.

    The 24-bit combined pitch encodes 4 subframe pitch lags using a
    mixed-radix number system: first subframe is absolute, rest are deltas.

    Decoding:
      p0_idx = combined % pitch_range  → pitch[0] = p0_idx + min_pitch
      For each subsequent subframe:
        delta = (combined // ...) % delta_range
        base = max(min_pitch, prev - half_delta)  [clamped to valid range]
        pitch[i] = base + delta
    """
    p0_idx = combined % pitch_range
    remaining = combined // pitch_range

    deltas = []
    for i in range(num_subframes - 2):
        deltas.append(remaining % delta_range)
        remaining //= delta_range
    deltas.append(min(remaining, delta_range - 1))

    pitches = [p0_idx + min_pitch]
    for delta_idx in deltas:
        prev = pitches[-1]
        half_delta = delta_range // 2 - 1
        upper_limit = min_pitch + pitch_range - 1 - half_delta
        if prev > upper_limit:
            base = upper_limit - half_delta
        else:
            base = max(min_pitch, prev - half_delta)
        pitches.append(base + delta_idx)

    return pitches


def decode_combinatorial_index(index: int, n: int, k: int) -> List[int]:
    """
    Decode a combinatorial number system index to k positions from {0..n-1}.

    The combinatorial number system represents a k-subset of {0..n-1} as
    a unique integer. This function reverses that encoding.

    Positions are returned in DESCENDING order (do NOT sort!) — this matches
    the DLL's behavior and affects the pulse excitation pattern.
    """
    positions = []
    remaining = index
    for i in range(k, 0, -1):
        v = i - 1
        while v + 1 < n and math.comb(v + 1, i) <= remaining:
            v += 1
        positions.append(v)
        remaining -= math.comb(v, i)
    return positions


# =============================================================================
# DS2 Decoder Class
# =============================================================================

class DS2Decoder:
    """
    Complete DS2 audio decoder supporting both SP and QP modes.

    Usage:
        decoder = DS2Decoder()
        pcm_samples = decoder.decode_file('recording.DS2')
        # pcm_samples is a numpy int16 array at the native sample rate
    """

    def __init__(self, mode: str = 'sp', codebook_dir: Optional[str] = None) -> None:
        """
        Initialize decoder for given mode.

        Args:
            mode: 'sp' for Standard Play (12kHz) or 'qp' for Quality Play (16kHz)
            codebook_dir: Directory containing ds2_lsp_codebook.npz and
                          ds2_qp_codebook.npz files. Defaults to script directory.
        """
        self.mode = mode

        if codebook_dir is None:
            codebook_dir = os.path.dirname(os.path.abspath(__file__))

        if mode == 'sp':
            self.sample_rate = SP_SAMPLE_RATE
            self.num_coeffs = SP_NUM_COEFFS
            self.num_subframes = SP_NUM_SUBFRAMES
            self.subframe_size = SP_SUBFRAME_SIZE
            self.samples_per_frame = SP_SAMPLES_PER_FRAME
            self.min_pitch = SP_MIN_PITCH
            self.max_pitch = SP_MAX_PITCH
            self.pitch_range = SP_PITCH_RANGE
            self.pitch_delta_range = SP_PITCH_DELTA_RANGE
            self.excitation_pulses = SP_EXCITATION_PULSES
            self.refl_bit_alloc = SP_REFL_BIT_ALLOC
            self.pitch_gain_bits = SP_PITCH_GAIN_BITS
            self.gain_bits = SP_GAIN_BITS
            self.pulse_bits = SP_PULSE_BITS
            self.combined_pitch_bits = SP_COMBINED_PITCH_BITS
            self.pitch_gain_table = SP_PITCH_GAIN_TABLE
            self.excitation_gain_table = SP_EXCITATION_GAIN_TABLE
            self.pulse_amp_table = PULSE_AMP_TABLE
            self.frame_bits = SP_FRAME_BITS
            self.codebook = load_codebook(
                os.path.join(codebook_dir, 'ds2_lsp_codebook.npz'),
                SP_NUM_COEFFS
            )
        else:
            self.sample_rate = QP_SAMPLE_RATE
            self.num_coeffs = QP_NUM_COEFFS
            self.num_subframes = QP_NUM_SUBFRAMES
            self.subframe_size = QP_SUBFRAME_SIZE
            self.samples_per_frame = QP_SAMPLES_PER_FRAME
            self.min_pitch = QP_MIN_PITCH
            self.max_pitch = QP_MAX_PITCH
            self.pitch_range = QP_PITCH_RANGE
            self.pitch_delta_range = QP_PITCH_DELTA_RANGE
            self.excitation_pulses = QP_EXCITATION_PULSES
            self.refl_bit_alloc = QP_REFL_BIT_ALLOC
            self.pitch_gain_bits = QP_PITCH_GAIN_BITS
            self.gain_bits = QP_GAIN_BITS
            self.pulse_bits = QP_PULSE_BITS
            self.pitch_gain_table = QP_PITCH_GAIN_TABLE
            self.excitation_gain_table = QP_EXCITATION_GAIN_TABLE
            self.pulse_amp_table = QP_PULSE_AMP_TABLE
            self.frame_bits = QP_FRAME_BITS
            self.codebook = load_codebook(
                os.path.join(codebook_dir, 'ds2_qp_codebook.npz'),
                QP_NUM_COEFFS
            )

        # Persistent decoder state (maintained across frames)
        self.lattice_state = np.zeros(self.num_coeffs, dtype=np.float64)
        self.pitch_memory = np.zeros(self.max_pitch + self.subframe_size, dtype=np.float64)

    def reset(self) -> None:
        """Reset decoder state for a new file."""
        self.lattice_state = np.zeros(self.num_coeffs, dtype=np.float64)
        self.pitch_memory = np.zeros(self.max_pitch + self.subframe_size, dtype=np.float64)

    def decode_file(self, ds2_path: str) -> Tuple[np.ndarray, DS2Header]:
        """
        Decode a DS2 file to PCM samples.

        Returns:
            (samples, header): int16 numpy array and parsed header
        """
        with open(ds2_path, 'rb') as f:
            data = f.read()

        header = parse_ds2_header(data)
        frame_data, total_frames, detected_mode = demux_ds2(data)

        # Switch mode if file doesn't match
        if detected_mode != self.mode:
            self.__init__(detected_mode,
                         os.path.dirname(os.path.abspath(__file__)))
            frame_data, total_frames, detected_mode = demux_ds2(data)

        self.reset()

        # Decode all frames
        if self.mode == 'qp':
            all_samples = self._decode_qp_frames(frame_data, total_frames)
        else:
            all_samples = self._decode_sp_frames(frame_data, total_frames)

        samples_arr = np.array(all_samples, dtype=np.float64)

        # QP mode: apply de-emphasis filter y[n] = x[n] + 0.1*y[n-1]
        if self.mode == 'qp':
            alpha = 0.1
            for i in range(1, len(samples_arr)):
                samples_arr[i] += alpha * samples_arr[i - 1]

        # Convert to int16 via truncation (matching DLL's cvttsd2si instruction)
        samples_16 = np.clip(samples_arr, -32768, 32767).astype(np.int16)

        return samples_16, header

    def _decode_sp_frames(self, frame_packets: List[bytes],
                          total_frames: int) -> List[float]:
        """Decode SP frames from byte-swap demuxed packets."""
        all_samples: List[float] = []
        cb_bits = math.ceil(math.log2(
            math.comb(self.subframe_size, self.excitation_pulses)
        ))

        for fi in range(total_frames):
            try:
                reader = BitstreamReader(frame_packets[fi])

                # Read reflection coefficient indices
                refl_indices = [reader.read_bits(b) for b in self.refl_bit_alloc]

                # Read per-subframe parameters
                subframe_data = []
                for sf in range(self.num_subframes):
                    pg_idx = reader.read_bits(self.pitch_gain_bits)
                    cb_idx = reader.read_bits(cb_bits)
                    gain_idx = reader.read_bits(self.gain_bits)
                    pulses = [reader.read_bits(self.pulse_bits)
                              for _ in range(self.excitation_pulses)]
                    subframe_data.append({
                        'pitch_gain_idx': pg_idx,
                        'cb_index': cb_idx,
                        'gain_idx': gain_idx,
                        'pulses': pulses,
                    })

                # Read combined pitch (24 bits, at end of frame)
                combined_pitch = reader.read_bits(self.combined_pitch_bits)

                # Decode speech
                pitches = decode_combined_pitch(
                    combined_pitch, self.pitch_range, self.min_pitch,
                    self.pitch_delta_range, self.num_subframes
                )
                samples = self._synthesize_frame(refl_indices, subframe_data, pitches)
                all_samples.extend(samples)
            except Exception as e:
                # On frame error, output silence for this frame
                all_samples.extend([0.0] * self.samples_per_frame)

        return all_samples

    def _decode_qp_frames(self, segments: List[Tuple[bytes, int]], total_frames: int) -> List[float]:
        """Decode QP frames from continuous bitstream segments."""
        all_samples: List[float] = []
        cb_bits = math.ceil(math.log2(
            math.comb(self.subframe_size, self.excitation_pulses)
        ))

        for stream, seg_frames in segments:
            reader = BitstreamReader(stream)
            # Reset codec state for each segment (e.g. after a recording pause)
            self.reset()
            
            for fi in range(seg_frames):
                try:
                    refl_indices = [reader.read_bits(b) for b in self.refl_bit_alloc]

                    subframe_data = []
                    pitches = []
                    for sf in range(self.num_subframes):
                        pitch_idx = reader.read_bits(8)
                        pg_idx = reader.read_bits(self.pitch_gain_bits)
                        cb_idx = reader.read_bits(cb_bits)
                        gain_idx = reader.read_bits(self.gain_bits)
                        pulses = [reader.read_bits(self.pulse_bits)
                                  for _ in range(self.excitation_pulses)]
                        pitches.append(pitch_idx + self.min_pitch)
                        subframe_data.append({
                            'pitch_gain_idx': pg_idx,
                            'cb_index': cb_idx,
                            'gain_idx': gain_idx,
                            'pulses': pulses,
                        })

                    samples = self._synthesize_frame(refl_indices, subframe_data, pitches)
                    all_samples.extend(samples)
                except Exception as e:
                    all_samples.extend([0.0] * self.samples_per_frame)

        return all_samples

    def _synthesize_frame(self, refl_indices: List[int],
                          subframe_data: List[Dict], pitches: List[int]) -> List[float]:
        """
        Synthesize one speech frame from decoded parameters.

        For each subframe:
          1. Build adaptive excitation from pitch memory
          2. Build fixed (sparse pulse) excitation from combinatorial codebook
          3. Combine: excitation = pitch_gain * adaptive + fixed
          4. Filter through lattice synthesis filter
          5. Update pitch memory with excitation
        """
        coeffs = dequantize_reflection_coeffs(
            refl_indices, self.codebook, self.num_coeffs
        )

        all_output: List[float] = []
        for sf in range(self.num_subframes):
            sd = subframe_data[sf]
            pitch = pitches[sf]

            # --- Adaptive excitation (pitch prediction) ---
            gp = self.pitch_gain_table[sd['pitch_gain_idx']]
            adaptive_exc = np.zeros(self.subframe_size, dtype=np.float64)
            for i in range(self.subframe_size):
                if pitch < self.subframe_size:
                    # Pitch shorter than subframe: wrap within pitch period
                    mem_idx = len(self.pitch_memory) - pitch + (i % pitch)
                else:
                    mem_idx = len(self.pitch_memory) - pitch + i
                if 0 <= mem_idx < len(self.pitch_memory):
                    adaptive_exc[i] = self.pitch_memory[mem_idx]

            # --- Fixed excitation (sparse pulse codebook) ---
            gc = float(self.excitation_gain_table[sd['gain_idx']])
            positions = decode_combinatorial_index(
                sd['cb_index'], self.subframe_size, self.excitation_pulses
            )
            fixed_exc = np.zeros(self.subframe_size, dtype=np.float64)
            for pi, pos in enumerate(positions):
                if pos < self.subframe_size:
                    amp = self.pulse_amp_table[sd['pulses'][pi]] * gc
                    fixed_exc[pos] += amp

            # --- Combine excitation ---
            excitation = gp * adaptive_exc + fixed_exc

            # --- Lattice synthesis filter ---
            output, self.lattice_state = lattice_synthesis(
                excitation, coeffs, self.lattice_state
            )

            # --- Update pitch memory ---
            self.pitch_memory = np.roll(self.pitch_memory, -self.subframe_size)
            self.pitch_memory[-self.subframe_size:] = excitation

            all_output.extend(output.tolist())

        return all_output


# =============================================================================
# MP3 Encoding
# =============================================================================

def encode_pcm_to_mp3(pcm_samples: np.ndarray, sample_rate: int,
                       output_path: str, bitrate: int = 128,
                       metadata: Optional[Dict[str, str]] = None) -> None:
    """
    Encode PCM samples to MP3 using lameenc.
    Uses 44.1kHz output for maximum compatibility.

    Args:
        pcm_samples: int16 numpy array
        sample_rate: Input sample rate in Hz (12000 or 16000)
        output_path: Path for output MP3 file
        bitrate: MP3 bitrate in kbps (default 128)
        metadata: Optional dict with 'title', 'artist', 'date' keys
    """
    import lameenc

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bitrate)
    encoder.set_in_sample_rate(sample_rate)
    # Force 44.1kHz output for universal compatibility (resampling handled by LAME)
    encoder.set_out_sample_rate(44100)
    encoder.set_channels(1)
    # encoder.set_mode(lameenc.Mono) # Some versions use this
    encoder.set_quality(2)  # 2 = high quality

    # Encode PCM to MP3
    mp3_data = encoder.encode(pcm_samples.tobytes())
    mp3_data += encoder.flush()

    with open(output_path, 'wb') as f:
        f.write(mp3_data)

    # Write ID3 tags if metadata provided
    if metadata:
        try:
            from mutagen.mp3 import MP3
            from mutagen.id3 import ID3, TIT2, TPE1, TDRC, TCOM

            audio = MP3(output_path)
            if audio.tags is None:
                audio.add_tags()

            if 'title' in metadata:
                audio.tags.add(TIT2(encoding=3, text=[metadata['title']]))
            if 'artist' in metadata:
                audio.tags.add(TPE1(encoding=3, text=[metadata['artist']]))
            if 'date' in metadata:
                audio.tags.add(TDRC(encoding=3, text=[metadata['date']]))

            audio.save()
        except Exception as e:
            print(f"  Warning: Could not write ID3 tags: {e}")


def decode_ds2_to_wav(ds2_path: str, wav_path: str,
                      codebook_dir: Optional[str] = None) -> Tuple[np.ndarray, DS2Header]:
    """
    Convenience function: decode DS2 to WAV file.

    Returns (pcm_samples, header).
    """
    decoder = DS2Decoder(codebook_dir=codebook_dir)
    samples, header = decoder.decode_file(ds2_path)

    with wave.open(wav_path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(decoder.sample_rate)
        w.writeframes(samples.tobytes())

    return samples, header


def decode_ds2_to_mp3(ds2_path: str, mp3_path: str, bitrate: int = 128,
                      codebook_dir: Optional[str] = None) -> DS2Header:
    """
    Convenience function: decode DS2 directly to MP3.

    Returns the parsed DS2 header.
    """
    decoder = DS2Decoder(codebook_dir=codebook_dir)
    samples, header = decoder.decode_file(ds2_path)

    # Build metadata from header
    metadata = {
        'title': f"{header.device_model} - {header.file_id}",
        'artist': header.author if header.author else header.device_model,
        'date': header.creation_datetime,
    }

    encode_pcm_to_mp3(
        samples, decoder.sample_rate, mp3_path,
        bitrate=bitrate, metadata=metadata
    )

    duration = len(samples) / decoder.sample_rate
    print(f"  Decoded: {header.total_frames} frames → {duration:.2f}s "
          f"at {decoder.sample_rate}Hz → {mp3_path}")

    return header


# =============================================================================
# CLI for standalone use
# =============================================================================

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: ds2_decoder.py <input.DS2> [output.mp3|output.wav]")
        print("       Output format determined by extension (.mp3 or .wav)")
        sys.exit(1)

    ds2_path = sys.argv[1]
    if len(sys.argv) > 2:
        out_path = sys.argv[2]
    else:
        out_path = str(Path(ds2_path).with_suffix('.mp3'))

    if out_path.lower().endswith('.wav'):
        samples, header = decode_ds2_to_wav(ds2_path, out_path)
    else:
        header = decode_ds2_to_mp3(ds2_path, out_path)

    print(f"Done: {out_path}")
