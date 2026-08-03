"""
Preprocess media: OCR for images (easyocr), ASR for voice notes (faster-whisper).
Writes a cache file code/media_text.json so the main pipeline is fast and does
not depend on these libraries at run time (it degrades gracefully if absent).

Usage:
    python preprocess_media.py --dataset <path to dataset dir>
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
MEDIA_TEXT = os.path.join(ROOT, "media_text.json")


def ocr_images(dataset_dir):
    out = {}
    try:
        import easyocr
        import pandas as pd
    except Exception as e:
        print("easyocr unavailable, skipping image OCR:", e)
        return out
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    img = pd.read_csv(os.path.join(dataset_dir, "images.csv"))
    for _, r in img.iterrows():
        p = os.path.join(dataset_dir, str(r["file_path"]))
        if not os.path.exists(p):
            out[r["image_id"]] = ""
            continue
        try:
            res = reader.readtext(p, detail=0, paragraph=True)
            out[r["image_id"]] = " ".join(res)
        except Exception as e:
            out[r["image_id"]] = ""
            print("OCR error", r["image_id"], e)
    return out


def transcribe_voice(dataset_dir):
    out = {}
    try:
        from faster_whisper import WhisperModel
        import pandas as pd
    except Exception as e:
        print("faster-whisper unavailable, skipping ASR:", e)
        return out
    model = WhisperModel("base", device="cpu", compute_type="int8")
    vn = pd.read_csv(os.path.join(dataset_dir, "voice_notes.csv"))
    for _, r in vn.iterrows():
        p = os.path.join(dataset_dir, str(r["file_path"]))
        if not os.path.exists(p):
            out[r["voice_note_id"]] = ""
            continue
        try:
            segments, _ = model.transcribe(p)
            out[r["voice_note_id"]] = " ".join(s.text.strip() for s in segments)
        except Exception as e:
            out[r["voice_note_id"]] = ""
            print("ASR error", r["voice_note_id"], e)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=os.path.join(ROOT, "..", "dataset"))
    args = ap.parse_args()
    data = {
        "images": ocr_images(args.dataset),
        "voice": transcribe_voice(args.dataset),
    }
    with open(MEDIA_TEXT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("cached", {k: len(v) for k, v in data.items()})


if __name__ == "__main__":
    main()
