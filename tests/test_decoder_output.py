"""Decoded output for fixed synthetic inputs must not change.

The expected hashes were produced by the decoder before the frame budget and
chunked-output changes, so these fail if decoding math is altered by accident.
"""

import hashlib

import numpy as np

from ds2_decoder import DS2Decoder
from ds2_fixtures import QP_FORMAT, SP_FORMAT, make_ds2, random_payload

GOLDEN_SP_SHA256 = "c0ad4c93953a05573b1e810f4ba498d58a4834b4d2ad56f31b2465b5e8efa009"
GOLDEN_QP_SHA256 = "a5395061616928f197afcf412c171caaebb0fcf0ebed449cdf092ab8480fb038"


def decode_bytes(tmp_path, data: bytes) -> np.ndarray:
    path = tmp_path / "input.DS2"
    path.write_bytes(data)
    samples, _ = DS2Decoder().decode_file(str(path))
    return samples


def test_sp_output_matches_reference_hash(tmp_path):
    data = make_ds2([(12, random_payload(1)), (12, random_payload(2))], SP_FORMAT)

    samples = decode_bytes(tmp_path, data)

    assert samples.dtype == np.int16
    assert samples.shape == (24 * 288,)
    assert hashlib.sha256(samples.tobytes()).hexdigest() == GOLDEN_SP_SHA256


def test_qp_output_matches_reference_hash(tmp_path):
    data = make_ds2([(9, random_payload(3)), (9, random_payload(4))], QP_FORMAT)

    samples = decode_bytes(tmp_path, data)

    assert samples.dtype == np.int16
    assert samples.shape == (18 * 256,)
    assert hashlib.sha256(samples.tobytes()).hexdigest() == GOLDEN_QP_SHA256
