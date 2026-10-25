# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Security

- DS2 frame counts from block headers are clamped to what the encoded payload can
  hold (plus one trailing partial frame), so work is proportional to the real
  payload rather than the declared count. A warning is printed when clamping happens.
- The 12-hour cap (`MAX_AUDIO_SECONDS`) limits the declared duration and so bounds
  decode work. Decoded samples go into one preallocated buffer sized to the clamped
  frame count, instead of per-frame chunks plus a concatenated copy.
- Output files (WAV and MP3) are written to a temporary file in the destination
  directory and renamed into place, so an existing symlink at the output path is
  replaced rather than written through.
- The temporary file is created with `O_EXCL` under a random name, so an existing
  file or symlink at that name is never opened. Its mode is `0666`, so the OS applies
  the umask as it does for any new file. The process umask is never read or changed.
  An existing regular file at the output path keeps its mode.
- Header strings (device, author, date, duration) and error messages are printed with
  control, format (bidi overrides, zero-width characters), line/paragraph separator,
  private-use and surrogate characters escaped. Tracebacks are printed sanitized too.
- Dependencies are pinned in `requirements.txt` and `requirements-dev.txt`.
- CI runs the test suite with read-only token permissions and without persisted
  checkout credentials. Dependabot checks pip and GitHub Actions monthly.
- Added `SECURITY.md` with the private reporting process.

### Changed

- **Behavior change:** block-header frame counts above what the payload can hold
  are clamped to the payload, with a warning. Valid files decode byte-identically.
- **Behavior change:** files longer than 12 hours are rejected.
- Minimum supported Python version is now 3.12.
- CI runs on Ubuntu and Windows across Python 3.12, 3.13 and 3.14.

### Fixed

- The CLI no longer crashes with `UnicodeEncodeError` when its output encoding
  cannot represent the banner characters (legacy Windows code pages, piped output
  with ASCII encoding). Unencodable characters are replaced instead.
