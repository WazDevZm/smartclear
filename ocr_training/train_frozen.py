"""Train PP-OCRv4 with the backbone frozen: only the neck and heads are updated.

Same arguments as PaddleOCR's tools/train.py. Run it from the PaddleOCR folder:

    python /path/to/train_frozen.py -c config.yml -o Global.pretrained_model=...

The backbone (the convolutional feature extractor) keeps its pretrained weights. The
optimizer only receives parameters that are still trainable, so the backbone is
never updated. Batch-norm statistics in the backbone still update in train mode.
"""
import sys
from pathlib import Path

import numpy as np

REPO = Path.cwd()  # run from the PaddleOCR folder
sys.path.insert(0, str(REPO))

import tools.train as T  # noqa: E402
from tools import program  # noqa: E402

_build_optimizer = T.build_optimizer


def build_optimizer_frozen(config, epochs, step_each_epoch, model):
    frozen, trainable = 0, 0
    for name, p in model.named_parameters():
        n = int(np.prod(p.shape))
        if name.startswith("backbone."):
            p.trainable = False
            p.stop_gradient = True
            frozen += n
        else:
            trainable += n
    print(f"[freeze] backbone frozen: {frozen:,} parameters | still trainable: {trainable:,}", flush=True)
    if frozen == 0:
        raise RuntimeError("No backbone parameters found to freeze; check the parameter names.")
    return _build_optimizer(config, epochs, step_each_epoch, model)


T.build_optimizer = build_optimizer_frozen

if __name__ == "__main__":
    config, device, logger, vdl_writer = program.preprocess(is_train=True)
    seed = config["Global"]["seed"] if "seed" in config["Global"] else 1024
    T.set_seed(seed)
    T.main(config, device, logger, vdl_writer, seed)
