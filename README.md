<a id="top"></a>
# DS2 to MP3 Converter

Converts Olympus and Philips DS2 (DSS Pro) dictation files to MP3 or WAV in pure Python. No FFmpeg required.

[![CI](https://github.com/IACBI/DS2_To_Mp3_Converter/actions/workflows/ci.yml/badge.svg)](https://github.com/IACBI/DS2_To_Mp3_Converter/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Read this in:** [English](#english) · [Türkçe](#turkce)

---
<a id="english"></a>
## English

### Overview

DS2 (Digital Speech Standard Pro) is the compressed speech format written by Olympus and Philips digital dictation recorders. This tool decodes it with a CELP (code-excited linear prediction) decoder implemented in Python and NumPy, then writes MP3 or WAV. It does not call FFmpeg, libav or any other external binary.

The codec was reverse-engineered by the [hirparak/dss-codec](https://github.com/hirparak/dss-codec) project (MIT). The decoder here is a clean-room Python/NumPy implementation of that work.

### Features

- Decodes SP (12 kHz) and QP (16 kHz) recordings. The mode is read from the file, so no flag is needed.
- MP3 output is resampled to 44.1 kHz at 128 kbps by default. Change the bitrate with `-b`. WAV output keeps the file's native sample rate (12 kHz or 16 kHz) and is mono, 16-bit PCM.
- MP3 files get ID3 title, artist and date tags taken from the file header. WAV files have no tags.
- In QP recordings, pauses and edits are detected in the bitstream, and the codec state is reset at each one.
- Text from the header (device, author, date) is escaped before it is printed, so control and bidirectional-override characters show up as escape sequences.

### Requirements

- Python 3.12 or newer. CI runs the tests on Python 3.12, 3.13 and 3.14, on Ubuntu and Windows.
- Runtime dependencies, pinned in `requirements.txt`: numpy 2.5.4, lameenc 1.9.0 and mutagen 1.48.1.

### Installation

Create a virtual environment and install the pinned dependencies:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Usage

Convert a single file, or every DS2 file in a folder:

```bash
python ds2_to_mp3.py recording.DS2
python ds2_to_mp3.py ./recordings/
python ds2_to_mp3.py recording.DS2 -o ./output/
python ds2_to_mp3.py ./recordings/ -b 192
python ds2_to_mp3.py recording.DS2 --wav
```

| Option | Description |
|---|---|
| `input` | A DS2 file, or a folder containing DS2 files |
| `-o`, `--output OUTPUT` | Output folder. Default: the input folder (for a single file, the folder that holds it) |
| `-b`, `--bitrate BITRATE` | MP3 bitrate in kbps. Default: 128. Ignored with `--wav` |
| `--wav` | Write WAV instead of MP3 |
| `--codebook-dir CODEBOOK_DIR` | Folder containing the `.npz` codebook files. Default: the script's folder |
| `-h`, `--help` | Show help and exit |

Notes:

- Output is named `<name>_converted.mp3` (or `.wav`). The input file is never modified.
- An existing output file with the same name is replaced. The new file is written to a temporary file in the output folder and then renamed over the old one, so a failed conversion leaves the previous output in place.
- Folder mode does not descend into subfolders. It picks up `*.DS2` and `*.ds2` files.
- A file without a `.DS2` extension is still tried, with a warning.
- If a block header declares more frames than the file contains, decoding stops at the data that is present and a warning is printed.
- Files that declare more than 12 hours of audio are rejected with an error.
- A failed file does not stop the batch. The exit code is 0 only when every file converts, and 1 otherwise.

### Configuration

There are no configuration files or environment variables. The decoder loads `ds2_lsp_codebook.npz` (SP) and `ds2_qp_codebook.npz` (QP) from the script's folder by default. If they live elsewhere, pass their folder with `--codebook-dir`.

### Contributing

Issues and pull requests are welcome. Run the test suite before opening a pull request:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

For security problems, follow [SECURITY.md](SECURITY.md) instead of opening a public issue. Release notes are kept in [CHANGELOG.md](CHANGELOG.md).

### License

MIT License. See [LICENSE](LICENSE). Copyright (c) 2026 𝓐.𝓒.𝓑

[⬆ Back to top](#top)

---
<a id="turkce"></a>
## Türkçe

### Genel Bakış

DS2 (Digital Speech Standard Pro), Olympus ve Philips dikte cihazlarının kaydettiği sıkıştırılmış bir ses formatıdır. Bu araç, CELP (code-excited linear prediction) tabanlı bir kod çözücüyü Python ve NumPy ile çalıştırır ve sonucu MP3 ya da WAV olarak yazar. FFmpeg, libav veya başka bir harici program gerekmez.

Codec, [hirparak/dss-codec](https://github.com/hirparak/dss-codec) projesinde tersine mühendislikle çözülmüştür (MIT lisanslı). Buradaki kod çözücü, bu çalışmanın temiz oda (clean-room) Python/NumPy gerçeklemesidir.

### Özellikler

- SP (12 kHz) ve QP (16 kHz) kayıtlarını çözer. Mod dosyanın kendisinden okunur, bir bayrak gerekmez.
- MP3 çıktısı varsayılan olarak 44,1 kHz'e yeniden örneklenir ve 128 kbps olur. Bitrate'i `-b` ile değiştirebilirsiniz. WAV çıktısı dosyanın kendi örnekleme hızını (12 kHz ya da 16 kHz) korur; tek kanallı, 16 bit PCM'dir.
- MP3 dosyalarına başlık, sanatçı ve tarih ID3 etiketleri, dosya başlığındaki bilgilerden yazılır. WAV dosyalarında etiket bulunmaz.
- QP kayıtlarında duraklatma ve düzenleme noktaları bit akışından algılanır; her birinde kodlayıcının durumu sıfırlanır.
- Başlıktaki metinler (cihaz, yazar, tarih) ekrana yazılırken denetim ve yön değiştirici karakterler kaçış dizisine çevrilir.

### Gereksinimler

- Python 3.12 veya daha yeni bir sürüm. CI, testleri Ubuntu ve Windows üzerinde Python 3.12, 3.13 ve 3.14 ile çalıştırır.
- Çalışma zamanı bağımlılıkları `requirements.txt` içinde sabitlenmiştir: numpy 2.5.4, lameenc 1.9.0 ve mutagen 1.48.1.

### Kurulum

Bir sanal ortam oluşturun ve sabitlenmiş bağımlılıkları yükleyin:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Kullanım

Tek bir dosyayı ya da bir klasördeki tüm DS2 dosyalarını dönüştürün:

```bash
python ds2_to_mp3.py recording.DS2
python ds2_to_mp3.py ./recordings/
python ds2_to_mp3.py recording.DS2 -o ./output/
python ds2_to_mp3.py ./recordings/ -b 192
python ds2_to_mp3.py recording.DS2 --wav
```

| Seçenek | Açıklama |
|---|---|
| `input` | Bir DS2 dosyası ya da DS2 dosyaları içeren bir klasör |
| `-o`, `--output OUTPUT` | Çıktı klasörü. Varsayılan: girdinin bulunduğu klasör (tek dosyada, dosyanın klasörü) |
| `-b`, `--bitrate BITRATE` | MP3 bitrate değeri, kbps cinsinden. Varsayılan: 128. `--wav` ile yok sayılır |
| `--wav` | MP3 yerine WAV yazar |
| `--codebook-dir CODEBOOK_DIR` | `.npz` codebook dosyalarının bulunduğu klasör. Varsayılan: betiğin klasörü |
| `-h`, `--help` | Yardımı gösterir ve çıkar |

Notlar:

- Çıktı `<ad>_converted.mp3` (ya da `.wav`) adını alır. Girdi dosyası hiçbir zaman değiştirilmez.
- Aynı adda bir çıktı dosyası varsa değiştirilir. Yeni dosya önce çıktı klasöründe geçici bir dosyaya yazılır, sonra eskisinin üzerine taşınır. Dönüşüm başarısız olursa önceki çıktı yerinde kalır.
- Klasör modu alt klasörlere inmez. `*.DS2` ve `*.ds2` dosyalarını bulur.
- `.DS2` uzantısı olmayan bir dosya yine denenir, ama bir uyarı yazılır.
- Bir blok başlığı dosyada bulunandan fazla çerçeve bildiriyorsa çözme, mevcut veriyle sınırlanır ve bir uyarı yazılır.
- 12 saatten uzun ses bildiren dosyalar hata vererek reddedilir.
- Bir dosyadaki hata toplu işlemi durdurmaz. Çıkış kodu, yalnızca tüm dosyalar başarıyla dönüştüğünde 0, aksi halde 1 olur.

### Yapılandırma

Ayar dosyası ya da ortam değişkeni yoktur. Kod çözücü, `ds2_lsp_codebook.npz` (SP) ve `ds2_qp_codebook.npz` (QP) dosyalarını varsayılan olarak betiğin klasöründe arar. Bu dosyalar başka bir yerdeyse klasörünü `--codebook-dir` ile belirtin.

### Katkı

Issue ve pull request açabilirsiniz. Pull request açmadan önce test paketini çalıştırın:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Güvenlik sorunları için herkese açık bir issue açmak yerine [SECURITY.md](SECURITY.md) dosyasındaki adımları izleyin. Sürüm notları [CHANGELOG.md](CHANGELOG.md) dosyasında tutulur.

### Lisans

MIT Lisansı. Ayrıntılar için [LICENSE](LICENSE) dosyasına bakın. Telif: © 2026 𝓐.𝓒.𝓑

[⬆ Başa Dön](#top)
