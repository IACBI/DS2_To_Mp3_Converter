"""Builders for small synthetic DS2 files used by the tests.

These are not real Olympus recordings. They only reproduce the container layout
(1536-byte header, 512-byte blocks with a 6-byte block header) so the demuxer and
decoder can be exercised with controlled frame counts and payloads.
"""

import random
import struct
from typing import Sequence, Tuple

from ds2_decoder import DS2_BLOCK_HEADER_SIZE, DS2_BLOCK_SIZE, DS2_HEADER_SIZE, DS2_MAGIC

BLOCK_PAYLOAD_SIZE = DS2_BLOCK_SIZE - DS2_BLOCK_HEADER_SIZE  # 506

SP_FORMAT = 0
QP_FORMAT = 6


def make_ds2(blocks: Sequence[Tuple[int, bytes]], format_type: int = SP_FORMAT,
             first_block_byte0: int = 0) -> bytes:
    """Build a DS2 byte string from (frame_count, payload) pairs, one per block.

    The payload must be at most 506 bytes and is zero-padded to that size.
    """
    header = bytearray(DS2_HEADER_SIZE)
    header[0:4] = DS2_MAGIC
    header[0x0C:0x0C + 9] = b'DPM 6000\x00'
    struct.pack_into('<H', header, 0x1C, 5018)
    header[0x26:0x32] = b'250101120000'
    header[0x32:0x3E] = b'250101120000'
    header[0x3E:0x44] = b'000100'

    out = bytearray(header)
    for i, (frame_count, payload) in enumerate(blocks):
        if len(payload) > BLOCK_PAYLOAD_SIZE:
            raise ValueError("payload larger than one block")
        block = bytearray(DS2_BLOCK_SIZE)
        block[0] = first_block_byte0 if i == 0 else 0
        block[1] = 0x03
        block[2] = frame_count
        block[4] = format_type
        block[DS2_BLOCK_HEADER_SIZE:DS2_BLOCK_HEADER_SIZE + len(payload)] = payload
        out.extend(block)
    return bytes(out)


def random_payload(seed: int, size: int = BLOCK_PAYLOAD_SIZE) -> bytes:
    return random.Random(seed).randbytes(size)
