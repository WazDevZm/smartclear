"""Build ocr_training/colab/nrc_rec_finetune.ipynb, the Colab notebook that fine-tunes PP-OCRv4.

    python ocr_training/colab/make_notebook.py

Upload ocr_rec.zip (from this folder) and run the notebook top to bottom on a GPU runtime.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": text.strip("\n").splitlines(True)}


CELLS = [
    md("""
# NRC text recognition: fine-tune PP-OCRv4 (English)

Fine-tunes the pretrained PP-OCRv4 English recognizer on the synthetic NRC text crops, then
reports per-field accuracy on the validation and test splits and exports an ONNX model.

Use a **GPU runtime** (Runtime > Change runtime type > T4 GPU). Upload `ocr_rec.zip` when asked.
Only synthetic data is used here. Do not upload real NRC scans to this notebook.
"""),
    code("""
!nvidia-smi --query-gpu=name,memory.total --format=csv
"""),
    md("## 1. Install PaddlePaddle (GPU) and PaddleOCR"),
    code("""
# Colab runs Python 3.13, and paddlepaddle 2.6.2 has no 3.13 build. This makes a separate
# Python 3.12 environment with uv and installs Paddle there (same versions as the local run).
!pip install -q uv
!uv venv --python 3.12 /content/py312
!uv pip install --python /content/py312/bin/python "numpy<2" setuptools paddlepaddle-gpu==2.6.2
!git clone -q --depth 1 --branch release/2.10 https://github.com/PaddlePaddle/PaddleOCR.git
%cd PaddleOCR
!uv pip install --python /content/py312/bin/python -r requirements.txt paddle2onnx
# The notebook's own Python (3.13) only needs these for the analysis cells.
!pip install -q onnxruntime rapidfuzz
PY = '/content/py312/bin/python'
!{PY} -c "import paddle, sys; print('python', sys.version.split()[0], '| paddle', paddle.__version__, '| cuda', paddle.device.is_compiled_with_cuda())"
"""),
    md("""
## 2. Data and pretrained weights

The data zip was split into five parts (each under 10 MB) and stored in the Drive folder
`smartclear_ocr`. This cell mounts Drive, joins the parts and unzips them.
"""),
    code("""
from google.colab import drive
drive.mount('/content/drive')
!cat "/content/drive/MyDrive/smartclear_ocr/ocr_rec.zip.part"* > /content/ocr_rec.zip
!python -c "import zipfile; print('zip ok:', zipfile.ZipFile('/content/ocr_rec.zip').testzip() is None)"
!unzip -q -o /content/ocr_rec.zip -d /content/data
!ls /content/data/ocr_rec
"""),
    code("""
!mkdir -p /content/pretrained && cd /content/pretrained && \\
  curl -sLO https://paddleocr.bj.bcebos.com/PP-OCRv4/english/en_PP-OCRv4_rec_train.tar && \\
  tar -xf en_PP-OCRv4_rec_train.tar
!ls /content/pretrained/en_PP-OCRv4_rec_train
"""),
    md("""
## 3. Training config

Changes from the stock config: GPU on, batch 128, 40 epochs, learning rate 2e-4 (fine-tuning),
and paths pointing at the unzipped data. The label files are the same ones the local run used.
"""),
    code("""
import yaml
cfg = yaml.safe_load(open('configs/rec/PP-OCRv4/en_PP-OCRv4_rec.yml'))
DATA = '/content/data/ocr_rec'
BATCH = 128
EPOCHS = 40
STEPS = 2405 // BATCH + 1

cfg['Global'].update({
    'use_gpu': True, 'distributed': False, 'epoch_num': EPOCHS,
    'save_model_dir': '/content/output/nrc_rec', 'save_epoch_step': 5,
    'eval_batch_step': [0, STEPS], 'pretrained_model': '/content/pretrained/en_PP-OCRv4_rec_train/best_accuracy',
    'character_dict_path': 'ppocr/utils/en_dict.txt', 'cal_metric_during_train': True,
})
cfg['Optimizer']['lr'].update({'learning_rate': 0.0002, 'warmup_epoch': 1})
cfg['Train']['dataset'].update({'data_dir': DATA, 'label_file_list': [f'{DATA}/train.txt']})
cfg['Train']['sampler'].update({'first_bs': BATCH, 'scales': [[320, 48]]})
cfg['Train']['loader'].update({'batch_size_per_card': BATCH, 'num_workers': 2})
cfg['Eval']['dataset'].update({'data_dir': DATA, 'label_file_list': [f'{DATA}/val.txt']})
cfg['Eval']['loader'].update({'batch_size_per_card': BATCH, 'num_workers': 2})
yaml.safe_dump(cfg, open('/content/nrc_rec.yml', 'w'), sort_keys=False, allow_unicode=True)
print('config written; steps per epoch ~', STEPS)
"""),
    md("## 4. Train (about 5 to 15 minutes on a T4 for 40 epochs)"),
    code("""
!{PY} tools/train.py -c /content/nrc_rec.yml 2>&1 | tee /content/train.log
"""),
    md("## 5. Evaluate on validation and test (exact-match accuracy)"),
    code("""
import subprocess
best = '/content/output/nrc_rec/best_accuracy'
for split in ['val', 'test']:
    print('=== ', split)
    subprocess.run([PY, 'tools/eval.py', '-c', '/content/nrc_rec.yml',
                    '-o', f'Global.checkpoints={best}',
                    f'Eval.dataset.label_file_list=[{DATA}/{split}.txt]'], check=False)
"""),
    md("""
## 6. Export for the app

Exports an inference model and converts it to ONNX, so the existing ONNX Runtime stack can
load it. Download `nrc_rec_onnx.zip` and send it back for integration.
"""),
    code("""
!{PY} tools/export_model.py -c /content/nrc_rec.yml -o Global.pretrained_model={best} \\
  Global.save_inference_dir=/content/inference/nrc_rec
!/content/py312/bin/paddle2onnx --model_dir /content/inference/nrc_rec \\
  --model_filename inference.pdmodel --params_filename inference.pdiparams \\
  --save_file /content/inference/nrc_rec.onnx --opset_version 11
!mkdir -p /content/inference && cp /content/nrc_rec.yml /content/inference/
!cd /content && zip -q -r nrc_rec_onnx.zip inference
from google.colab import files
files.download('/content/nrc_rec_onnx.zip')
"""),
    md("""
## 7. Training curves

Reads the training log and plots the loss, the training and validation accuracy, and the
validation edit distance. The dashed line marks the 90% target.
"""),
    code("""
import os, re
import matplotlib.pyplot as plt
os.makedirs('/content/results', exist_ok=True)

STEP = re.compile(r"epoch: \\[(\\d+)/(\\d+)\\], global_step: (\\d+), .*?acc: ([\\d.]+), norm_edit_dis: ([\\d.]+), "
                  r"CTCLoss: ([\\d.]+), NRTRLoss: ([\\d.]+), loss: ([\\d.]+)")
EVAL = re.compile(r"cur metric, acc: ([\\d.]+), norm_edit_dis: ([\\d.]+)")
steps, tr_acc, ctc, nrtr, total = [], [], [], [], []
ev_steps, ev_acc, ev_ned = [], [], []
last_step = 0
with open('/content/train.log', errors='ignore') as f:
    for line in f:
        m = STEP.search(line)
        if m:
            last_step = int(m.group(3))
            steps.append(last_step); tr_acc.append(float(m.group(4)))
            ctc.append(float(m.group(6))); nrtr.append(float(m.group(7))); total.append(float(m.group(8)))
            continue
        m = EVAL.search(line)
        if m:
            ev_steps.append(last_step); ev_acc.append(float(m.group(1))); ev_ned.append(float(m.group(2)))

ep = [s / STEPS for s in steps]
ev_ep = [s / STEPS for s in ev_steps]
print(f'training log lines parsed: {len(steps)} steps, {len(ev_steps)} validation evaluations')

fig, ax = plt.subplots(1, 3, figsize=(17, 4.5))
ax[0].plot(ep, total, label='total loss')
ax[0].plot(ep, ctc, label='CTC loss', alpha=.8)
ax[0].plot(ep, nrtr, label='NRTR loss', alpha=.8)
ax[0].set_title('Training loss'); ax[0].set_xlabel('epoch'); ax[0].legend()
ax[1].plot(ep, tr_acc, alpha=.5, label='train batch accuracy')
ax[1].plot(ev_ep, ev_acc, 'o-', label='validation accuracy')
ax[1].axhline(0.9, ls='--', color='gray', label='90% target')
ax[1].set_ylim(0, 1.02); ax[1].set_title('Exact-match accuracy'); ax[1].set_xlabel('epoch'); ax[1].legend()
ax[2].plot(ev_ep, ev_ned, 'o-', color='tab:green')
ax[2].set_title('Validation normalised edit distance (higher is better)'); ax[2].set_xlabel('epoch')
plt.tight_layout(); plt.savefig('/content/results/training_curves.png', dpi=120); plt.show()
"""),
    md("""
## 8. Evaluate the exported ONNX model

Runs the exported model on every validation and test crop, with the same decoding the app
will use. Reports accuracy per field, the character-level confusion matrix, and the
mistakes. The **test split is scored here once for the report**; use the validation numbers
to decide what to change.
"""),
    code("""
import re, math, json, csv
import numpy as np
import onnxruntime as ort
from PIL import Image
from collections import Counter, defaultdict
from rapidfuzz.distance import Levenshtein
import pandas as pd

sess = ort.InferenceSession('/content/inference/nrc_rec.onnx', providers=['CPUExecutionProvider'])
inp_name = sess.get_inputs()[0].name
C = sess.get_outputs()[0].shape[-1]
dict_chars = [l.rstrip('\\r\\n') for l in open('/content/PaddleOCR/ppocr/utils/en_dict.txt', encoding='utf-8')]
CHARS = ['blank'] + dict_chars
if ' ' not in CHARS:
    CHARS.append(' ')
print('model classes', C, '| dictionary entries', len(CHARS))
if len(CHARS) != C:
    print('WARNING: dictionary size does not match the model output; check before trusting results')

H, W_MAX = 48, 320
def predict(img):
    im = img.convert('RGB')
    w, h = im.size
    nw = min(W_MAX, max(1, int(math.ceil(H * w / h))))
    a = np.asarray(im.resize((nw, H), Image.BILINEAR)).astype(np.float32)[:, :, ::-1]  # BGR, as in training
    a = (a / 255.0 - 0.5) / 0.5
    x = np.zeros((1, 3, H, W_MAX), np.float32)
    x[0, :, :, :nw] = a.transpose(2, 0, 1)
    out = sess.run(None, {inp_name: x})[0][0]          # [T, C]
    text, prev = [], -1
    for i in out.argmax(-1):
        if i != prev and i != 0 and i < len(CHARS):    # CTC: collapse repeats, drop blank
            text.append(CHARS[i])
        prev = i
    return ''.join(text).strip()

def read_split(split):
    rows = []
    for line in open(f'/content/data/ocr_rec/{split}.txt', encoding='utf-8'):
        rel, text = line.rstrip('\\r\\n').split('\\t', 1)
        field = re.search(r'_(front|back)_(.+)\\.png$', rel).group(2)
        rows.append((rel, field, text))
    return rows

results = {}
for split in ['val', 'test']:
    recs = []
    for rel, field, truth in read_split(split):
        pred = predict(Image.open(f'/content/data/ocr_rec/{rel}'))
        recs.append(dict(split=split, crop=rel, field=field, truth=truth, pred=pred,
                         correct=pred.replace(' ', '') == truth.replace(' ', '')))
    results[split] = recs
    print(split, 'crops', len(recs), 'exact', round(np.mean([r['correct'] for r in recs]), 4))
"""),
    code("""
def summarise(recs):
    fields = defaultdict(lambda: [0, 0, 0.0])
    for r in recs:
        f = fields[r['field']]
        f[0] += 1; f[1] += int(r['correct'])
        f[2] += 1 - Levenshtein.distance(r['pred'], r['truth']) / max(len(r['pred']), len(r['truth']), 1)
    per = {k: {'n': v[0], 'exact': round(v[1] / v[0], 4), 'similarity': round(v[2] / v[0], 4)}
           for k, v in sorted(fields.items())}
    return {'crops': len(recs), 'exact': round(np.mean([r['correct'] for r in recs]), 4), 'per_field': per}

metrics = {s: summarise(results[s]) for s in results}
for s in metrics:
    print(f"\\n{s}: overall exact match = {metrics[s]['exact']:.3f} over {metrics[s]['crops']} crops")
    print(pd.DataFrame(metrics[s]['per_field']).T.to_string())

# per-field accuracy chart
fields = sorted(metrics['val']['per_field'])
fig, ax = plt.subplots(figsize=(13, 4.5))
xs = np.arange(len(fields)); w = 0.38
ax.bar(xs - w/2, [metrics['val']['per_field'][f]['exact'] for f in fields], w, label='validation')
ax.bar(xs + w/2, [metrics['test']['per_field'][f]['exact'] for f in fields], w, label='test (report only)')
ax.axhline(0.9, ls='--', color='gray', label='90% target')
ax.set_xticks(xs); ax.set_xticklabels(fields, rotation=30); ax.set_ylim(0, 1.05)
ax.set_ylabel('exact match'); ax.set_title('Per-field accuracy'); ax.legend()
plt.tight_layout(); plt.savefig('/content/results/per_field_accuracy.png', dpi=120); plt.show()
"""),
    code("""
# character-level confusions: which true character is read as which
conf = Counter(); kinds = Counter()
for split in results:
    for r in results[split]:
        if r['correct']:
            continue
        for op in Levenshtein.editops(r['truth'], r['pred']):
            if op.tag == 'replace':
                conf[(r['truth'][op.src_pos], r['pred'][op.dest_pos])] += 1; kinds['substitution'] += 1
            elif op.tag == 'delete':
                conf[(r['truth'][op.src_pos], '(missing)')] += 1; kinds['deletion (char dropped)'] += 1
            elif op.tag == 'insert':
                conf[('(extra)', r['pred'][op.dest_pos])] += 1; kinds['insertion (extra char)'] += 1

print('error types:', dict(kinds))
print('top confusions (true -> read as: count):')
for (t, p), n in conf.most_common(20):
    print(f'  {t!r:>10} -> {p!r:<12} {n}')

top = conf.most_common(30)
labels = sorted({t for (t, p), _ in top} | {p for (t, p), _ in top})
M = np.zeros((len(labels), len(labels)))
for (t, p), n in conf.items():
    if t in labels and p in labels:
        M[labels.index(t), labels.index(p)] = n
fig, ax = plt.subplots(figsize=(9, 8))
im = ax.imshow(M, cmap='Blues')
ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, rotation=90)
ax.set_yticks(range(len(labels))); ax.set_yticklabels(labels)
ax.set_xlabel('read as (prediction)'); ax.set_ylabel('true character')
ax.set_title('Character confusions (top 30 pairs)')
for i in range(len(labels)):
    for j in range(len(labels)):
        if M[i, j]:
            ax.text(j, i, int(M[i, j]), ha='center', va='center', fontsize=7,
                    color='white' if M[i, j] > M.max() / 2 else 'black')
plt.colorbar(im); plt.tight_layout(); plt.savefig('/content/results/confusion_matrix.png', dpi=120); plt.show()

# save everything for the report
for split in results:
    pd.DataFrame(results[split]).to_csv(f'/content/results/predictions_{split}.csv', index=False)
pd.DataFrame([{'truth': t, 'read_as': p, 'count': n} for (t, p), n in conf.most_common()]).to_csv(
    '/content/results/confusions.csv', index=False)
json.dump({'metrics': metrics, 'error_types': dict(kinds)}, open('/content/results/metrics.json', 'w'), indent=2)
print('saved predictions, confusions, metrics.json and charts to /content/results')
"""),
    md("""
## 9. Save the run to Google Drive

Copies the log, the config, the charts, the metrics, the best checkpoint and the ONNX model
into a timestamped folder in `smartclear_ocr`, so they survive when the Colab session ends.
"""),
    code("""
import datetime, shutil, os
dest = f"/content/drive/MyDrive/smartclear_ocr/run_{datetime.datetime.now():%Y%m%d_%H%M}"
os.makedirs(dest + '/checkpoint', exist_ok=True)
for f in ['/content/train.log', '/content/nrc_rec.yml', '/content/nrc_rec_onnx.zip']:
    if os.path.exists(f):
        shutil.copy(f, dest)
shutil.copytree('/content/results', dest + '/results', dirs_exist_ok=True)
shutil.copytree('/content/inference', dest + '/inference', dirs_exist_ok=True)
for f in os.listdir('/content/output/nrc_rec'):
    if f.startswith('best_accuracy') or f.startswith('latest'):
        shutil.copy(os.path.join('/content/output/nrc_rec', f), dest + '/checkpoint')
print('saved to', dest)
"""),
]


def main() -> None:
    nb = {
        "cells": CELLS,
        "metadata": {"accelerator": "GPU", "colab": {"provenance": []},
                     "kernelspec": {"display_name": "Python 3", "name": "python3"}},
        "nbformat": 4, "nbformat_minor": 0,
    }
    out = HERE / "nrc_rec_finetune.ipynb"
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
