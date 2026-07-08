import librosa
import numpy as np
import soundfile as sf

VECTOR_BIN_SEG = 3.0
_CHROMA_HOP = 2048


def extraer_vector_track(filepath: str, bin_seg: float = VECTOR_BIN_SEG) -> list[dict]:
    data, sr_native = sf.read(filepath)
    y = data.mean(axis=1).astype(np.float32) if data.ndim > 1 else data.astype(np.float32)

    duration = len(y) / sr_native
    n_bins = int(duration // bin_seg)
    if n_bins == 0:
        return []

    block = int(sr_native)
    freqs = np.fft.rfftfreq(block, d=1.0 / sr_native)
    n_secs = (len(y) - block) // block

    rms_full = np.zeros(n_secs)
    sc_full = np.zeros(n_secs)
    onset_full = np.zeros(n_secs)
    mag_prev = None
    for i in range(n_secs):
        seg = y[i * block:(i + 1) * block]
        rms_full[i] = np.sqrt(np.mean(seg ** 2))
        mag = np.abs(np.fft.rfft(seg))
        mag_sum = mag.sum()
        sc_full[i] = (np.dot(freqs, mag) / mag_sum) if mag_sum > 1e-10 else 0.0
        onset_full[i] = np.sum(np.maximum(0.0, mag - mag_prev)) if mag_prev is not None else 0.0
        mag_prev = mag

    chroma = librosa.feature.chroma_stft(y=y, sr=sr_native, hop_length=_CHROMA_HOP)
    frame_times = librosa.frames_to_time(
        np.arange(chroma.shape[1]), sr=sr_native, hop_length=_CHROMA_HOP
    )

    bins = []
    for i in range(n_bins):
        t0, t1 = i * bin_seg, (i + 1) * bin_seg
        s0, s1 = int(t0), min(int(t1), n_secs)

        rms_bin = float(np.mean(rms_full[s0:s1])) if s1 > s0 else 0.0
        onset_bin = float(np.mean(onset_full[s0:s1])) if s1 > s0 else 0.0
        sc_bin = float(np.mean(sc_full[s0:s1])) if s1 > s0 else 0.0

        mask = (frame_times >= t0) & (frame_times < t1)
        chroma_bin = chroma[:, mask].mean(axis=1) if mask.any() else np.zeros(12)
        norm = np.linalg.norm(chroma_bin)
        if norm > 0:
            chroma_bin = chroma_bin / norm

        bins.append({
            "t_start": round(t0, 2),
            "t_end": round(t1, 2),
            "rms": round(rms_bin, 5),
            "onset": round(onset_bin, 3),
            "spectral_centroid": round(sc_bin, 1),
            "chroma": [round(float(c), 4) for c in chroma_bin],
        })
    return bins
