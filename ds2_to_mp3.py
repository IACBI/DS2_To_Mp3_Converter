#!/usr/bin/env python3
"""
DS2 to MP3 Converter — Command-Line Interface
===============================================
Converts Olympus DS2 (Digital Speech Standard Pro) files to MP3.

The DS2 codec is a CELP (Code-Excited Linear Prediction) speech codec
reverse-engineered from Olympus's DssDecoder.dll. This tool decodes
the audio natively in Python/NumPy without any dependency on ffmpeg,
libav, or external audio conversion binaries.

Usage:
    ds2_to_mp3.py <input.DS2>                   # Convert single file
    ds2_to_mp3.py <input_dir>                   # Convert all DS2 in directory
    ds2_to_mp3.py <input.DS2> -o <output_dir>   # Specify output directory
    ds2_to_mp3.py <input_dir> -b 192            # Set MP3 bitrate (kbps)

Dependencies: numpy, lameenc, mutagen
"""

import argparse
import os
import sys
import time
import glob
from pathlib import Path
from typing import List, Optional

# Import the decoder module (must be in same directory or on PYTHONPATH)
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from ds2_decoder import (
    DS2Decoder, DS2Header, parse_ds2_header, encode_pcm_to_mp3,
    DS2_MAGIC, DS2_HEADER_SIZE
)


def find_ds2_files(path: str) -> List[str]:
    """
    Find all DS2 files from a path (file or directory).
    
    Handles both .DS2 and .ds2 extensions, deduplicating on
    case-insensitive filesystems like Windows.
    """
    path = os.path.abspath(path)
    
    if os.path.isfile(path):
        if path.upper().endswith('.DS2'):
            return [path]
        else:
            print(f"Warning: {path} does not have .DS2 extension")
            return [path]
    elif os.path.isdir(path):
        files = glob.glob(os.path.join(path, '*.DS2'))
        files += glob.glob(os.path.join(path, '*.ds2'))
        # Deduplicate (Windows is case-insensitive)
        seen = set()
        unique = []
        for f in sorted(files):
            key = os.path.normcase(os.path.abspath(f))
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique
    else:
        print(f"Error: {path} does not exist")
        return []


def format_duration(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def convert_file(ds2_path: str, output_dir: str, bitrate: int = 128,
                 codebook_dir: Optional[str] = None) -> Optional[str]:
    """
    Convert a single DS2 file to MP3.
    
    Args:
        ds2_path: Path to input DS2 file
        output_dir: Directory for output MP3
        bitrate: MP3 bitrate in kbps
        codebook_dir: Directory containing codebook .npz files
    
    Returns:
        Path to output MP3, or None on failure
    """
    filename = os.path.basename(ds2_path)
    mp3_name = Path(filename).stem + '_converted.mp3'
    mp3_path = os.path.join(output_dir, mp3_name)
    
    try:
        # Quick header check
        with open(ds2_path, 'rb') as f:
            magic = f.read(4)
        if magic != DS2_MAGIC:
            print(f"  ✗ {filename}: Not a valid DS2 file (magic: {magic.hex()})")
            return None
        
        # Parse header for info
        with open(ds2_path, 'rb') as f:
            data = f.read()
        header = parse_ds2_header(data)
        file_size = len(data)
        
        mode_str = "QP" if header.codec_mode >= 6 else "SP"
        print(f"  → {filename}")
        print(f"    Device: {header.device_model} | Author: {header.author or 'N/A'}")
        print(f"    Date: {header.creation_datetime} | Duration: {header.duration_str}")
        print(f"    Mode: {mode_str} ({header.sample_rate}Hz) | Frames: {header.total_frames}")
        print(f"    Size: {file_size:,} bytes | Bitrate: ~{file_size * 8 / max(header.duration_seconds, 1) / 1000:.1f} kbps")
        
        # Decode
        t0 = time.time()
        decoder = DS2Decoder(codebook_dir=codebook_dir)
        samples, header = decoder.decode_file(ds2_path)
        decode_time = time.time() - t0
        
        duration = len(samples) / decoder.sample_rate
        
        # Encode to MP3
        t1 = time.time()
        metadata = {
            'title': f"{header.device_model} - Recording {header.file_id}",
            'artist': header.author if header.author else header.device_model,
            'date': header.creation_datetime,
        }
        encode_pcm_to_mp3(samples, decoder.sample_rate, mp3_path,
                          bitrate=bitrate, metadata=metadata)
        encode_time = time.time() - t1
        
        mp3_size = os.path.getsize(mp3_path)
        total_time = decode_time + encode_time
        
        print(f"    ✓ Decoded {header.total_frames} frames → {format_duration(duration)} "
              f"({len(samples):,} samples)")
        print(f"    ✓ Encoded to MP3 ({bitrate}kbps, 44.1kHz) → {mp3_size:,} bytes")
        print(f"    ✓ Time: {total_time:.1f}s (decode={decode_time:.1f}s, encode={encode_time:.1f}s)")
        print(f"    ✓ Output: {mp3_path}")
        
        return mp3_path
        
    except Exception as e:
        print(f"  ✗ {filename}: ERROR - {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(
        description='DS2 to MP3 Converter — Convert Olympus DS2 dictation files to MP3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s recording.DS2               Convert single file
    %(prog)s ./recordings/               Convert all DS2 files in directory
    %(prog)s recording.DS2 -o ./output/  Convert to specific output directory
    %(prog)s ./recordings/ -b 192        Convert with 192kbps bitrate
    %(prog)s recording.DS2 --wav         Output as WAV instead of MP3
        """
    )
    
    parser.add_argument('input', help='Input DS2 file or directory containing DS2 files')
    parser.add_argument('-o', '--output', default=None,
                       help='Output directory (default: same as input)')
    parser.add_argument('-b', '--bitrate', type=int, default=128,
                       help='MP3 bitrate in kbps (default: 128)')
    parser.add_argument('--wav', action='store_true',
                       help='Output as WAV format instead of MP3')
    parser.add_argument('--codebook-dir', default=None,
                       help='Directory containing codebook .npz files (default: script dir)')
    
    args = parser.parse_args()
    
    # Find DS2 files
    ds2_files = find_ds2_files(args.input)
    
    if not ds2_files:
        print("No DS2 files found.")
        sys.exit(1)
    
    # Determine output directory
    if args.output:
        output_dir = os.path.abspath(args.output)
    elif os.path.isfile(args.input):
        output_dir = os.path.dirname(os.path.abspath(args.input))
    else:
        output_dir = os.path.abspath(args.input)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Determine codebook directory
    codebook_dir = args.codebook_dir or script_dir
    
    # Verify codebook files exist
    sp_cb = os.path.join(codebook_dir, 'ds2_lsp_codebook.npz')
    qp_cb = os.path.join(codebook_dir, 'ds2_qp_codebook.npz')
    if not os.path.exists(sp_cb):
        print(f"Error: SP codebook not found: {sp_cb}")
        print(f"Please ensure ds2_lsp_codebook.npz is in: {codebook_dir}")
        sys.exit(1)
    
    # Print banner
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║          DS2 → MP3 Converter                             ║")
    print("║   Olympus Digital Speech Standard Pro Decoder             ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print(f"  Input:    {args.input}")
    print(f"  Output:   {output_dir}")
    print(f"  Files:    {len(ds2_files)} DS2 file(s) found")
    print(f"  Bitrate:  {args.bitrate} kbps")
    print(f"  Format:   {'WAV' if args.wav else 'MP3'}")
    print()
    
    # Process files
    start_time = time.time()
    results = []
    
    for i, ds2_path in enumerate(ds2_files, 1):
        print(f"\n[{i}/{len(ds2_files)}] Processing...")
        
        if args.wav:
            import wave as wave_mod
            filename = os.path.basename(ds2_path)
            wav_name = Path(filename).stem + '_converted.wav'
            wav_path = os.path.join(output_dir, wav_name)
            
            try:
                decoder = DS2Decoder(codebook_dir=codebook_dir)
                samples, header = decoder.decode_file(ds2_path)
                with wave_mod.open(wav_path, 'w') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(decoder.sample_rate)
                    w.writeframes(samples.tobytes())
                print(f"  ✓ {filename} → {wav_name}")
                results.append(wav_path)
            except Exception as e:
                print(f"  ✗ {filename}: {e}")
        else:
            result = convert_file(ds2_path, output_dir, args.bitrate, codebook_dir)
            if result:
                results.append(result)
    
    # Print summary
    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  CONVERSION COMPLETE")
    print(f"{'='*60}")
    print(f"  Processed: {len(ds2_files)} file(s)")
    print(f"  Succeeded: {len(results)} file(s)")
    print(f"  Failed:    {len(ds2_files) - len(results)} file(s)")
    print(f"  Total time: {total_time:.1f}s")
    if results:
        print(f"  Output directory: {output_dir}")
    print()
    
    sys.exit(0 if len(results) == len(ds2_files) else 1)


if __name__ == '__main__':
    main()
