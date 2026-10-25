# DS2 to MP3 Converter (Digital Speech Standard Pro)

A high-fidelity, dependency-free Python tool for converting proprietary Olympus/Philips .DS2 files to standard MP3 and WAV.

---

## 🇺🇸 English Version

### About
DS2 (Digital Speech Standard Pro) is a highly compressed speech format used by professional digital dictation devices. This project provides a native Python implementation of the **CELP (Code-Excited Linear Prediction)** decoder, reverse-engineered for bit-exact accuracy.

### Key Features
- **Bit-Exact Decoding**: Accurate reconstruction of speech with professional lattice synthesis filters.
- **Resampling**: Automatically resamples 12kHz/16kHz DS2 audio to **44.1kHz** for universal MP3 player compatibility.
- **Recording Pause Handling**: Correctly handles recording pauses and edits within the stream.
- **Zero Binaries**: No ffmpeg, libav, or DLLs required for the core decoding process.

### Installation
Ensure you have Python 3.12+ installed.
```bash
pip install -r requirements.txt
```

### Usage
**Batch Convert a Directory:**
```powershell
python ds2_to_mp3.py ./my_recordings/
```

**Convert a Single File:**
```powershell
python ds2_to_mp3.py recording.DS2
```

Run the tests with `pip install -r requirements-dev.txt` followed by `python -m pytest`.

---

## 🇹🇷 Türkçe Versiyon

### Hakkında
DS2 (Digital Speech Standard Pro), profesyonel dikte cihazları (Olympus, Philips vb.) tarafından kullanılan, yüksek sıkıştırmalı bir ses formatıdır. Bu proje, özel CELP kod çözücü mimarisini hiçbir dış kütüphaneye (ffmpeg vb.) ihtiyaç duymadan doğrudan Python üzerinden çalıştırır.

### Öne Çıkan Özellikler
- **Kusursuz Çeviri**: Profesyonel "lattice synthesis" filtreleri ile kayıpsız bir koda çözme işlemi.
- **Evrensel Uyumluluk**: 12kHz/16kHz ham ses verisini, tüm cihazların çalabileceği **44.1kHz** standardına yükseltir (MP3 için).
- **Kesinti Yönetimi**: Kayıt sırasında yapılan duraklatmaları fark eder ve sesi bozmadan birleştirir.
- **Kurulumsuz Kullanım**: Dışarıdan .exe veya .dll dosyası gerektirmez.

### Kurulum
Python 3.12 veya daha yeni bir sürümün yüklü olduğundan emin olun.
```bash
pip install -r requirements.txt
```

### Kullanım
**Tüm Klasörü Dönüştürmek İçin:**
```powershell
python ds2_to_mp3.py ./ses_kayitlarim/
```

**Tek Bir Dosyayı Dönüştürmek İçin:**
```powershell
python ds2_to_mp3.py kayit.DS2
```

Testleri çalıştırmak için `pip install -r requirements-dev.txt` ardından `python -m pytest` komutlarını kullanın.

---

## License
MIT License.
