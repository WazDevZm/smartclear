"""Write the PP-OCRv4 English recognition fine-tune config for the NRC crops.

Starts from the stock PaddleOCR config and changes only what this dataset needs:
- data paths -> data/ocr_rec (made by backend/scripts/prepare_ocr_data.py)
- pretrained weights -> ocr_training/pretrained/en_PP-OCRv4_rec_train
- CPU training, smaller batch, fewer epochs, lower learning rate for fine-tuning

Run from the project root with the training venv:
    .venv_paddle/Scripts/python ocr_training/make_config.py
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "ocr_training" / "PaddleOCR" / "configs" / "rec" / "PP-OCRv4" / "en_PP-OCRv4_rec.yml"
OUT = ROOT / "ocr_training" / "configs" / "en_PP-OCRv4_rec_nrc.yml"
DATA = (ROOT / "data" / "ocr_rec").as_posix()
PRETRAINED = (ROOT / "ocr_training" / "pretrained" / "en_PP-OCRv4_rec_train").as_posix()
DICT = (ROOT / "ocr_training" / "PaddleOCR" / "ppocr" / "utils" / "en_dict.txt").as_posix()

BATCH = 64
EPOCHS = 30
STEPS_PER_EPOCH = 38  # 2405 train crops / 64, rounded up


def main() -> None:
    cfg = yaml.safe_load(BASE.read_text(encoding="utf-8"))
    g = cfg["Global"]
    g.update({
        "use_gpu": False,
        "distributed": False,
        "epoch_num": EPOCHS,
        "save_model_dir": (ROOT / "ocr_training" / "output" / "nrc_rec").as_posix(),
        "save_epoch_step": 5,
        "eval_batch_step": [0, STEPS_PER_EPOCH],
        "pretrained_model": PRETRAINED,
        "character_dict_path": DICT,
        "print_batch_step": 10,
        "cal_metric_during_train": True,
    })

    cfg["Optimizer"]["lr"].update({"learning_rate": 0.0002, "warmup_epoch": 1})

    tr = cfg["Train"]
    tr["dataset"]["data_dir"] = DATA
    tr["dataset"]["label_file_list"] = [f"{DATA}/train.txt"]
    tr["sampler"]["first_bs"] = BATCH
    tr["sampler"]["scales"] = [[320, 48]]  # single scale: all crops are resized to 48x320
    tr["loader"].update({"batch_size_per_card": BATCH, "num_workers": 0})

    ev = cfg["Eval"]
    ev["dataset"]["data_dir"] = DATA
    ev["dataset"]["label_file_list"] = [f"{DATA}/val.txt"]
    ev["loader"].update({"batch_size_per_card": BATCH, "num_workers": 0})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
