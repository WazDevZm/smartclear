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


# The frozen-backbone training wrapper is written into the notebook from the same file.
WRAPPER_SRC = (HERE.parent / 'train_frozen.py').read_text(encoding='utf-8')
NL = chr(10)
WRITE_WRAPPER = ('WRAPPER_SRC = ' + repr(WRAPPER_SRC) + NL +
                 "open('/content/train_frozen.py', 'w').write(WRAPPER_SRC)" + NL +
                 "print('frozen-backbone training script written')" + NL)

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
# The Paddle GPU wheel is about 1 GB; the default 30 s download timeout is too short.
import os
os.environ['UV_HTTP_TIMEOUT'] = '600'
!uv venv --python 3.12 /content/py312
!uv pip install --python /content/py312/bin/python "numpy<2" setuptools paddlepaddle-gpu==2.6.2
!git clone -q --depth 1 --branch release/2.10 https://github.com/PaddlePaddle/PaddleOCR.git
%cd PaddleOCR
# Keep numpy 1.x and OpenCV 4.10 (Paddle 2.6 was built against numpy 1.x). Without these pins
# the PaddleOCR requirements upgrade numpy to 2.x and break Paddle.
!printf "numpy==1.26.4\\nopencv-python==4.10.0.84\\nopencv-python-headless==4.10.0.84\\nopencv-contrib-python==4.10.0.84\\n" > /content/constraints.txt
!uv pip install --python /content/py312/bin/python -r requirements.txt -c /content/constraints.txt
# Export and ONNX conversion use Paddle 3.1.1 with paddle2onnx 2.1.0. paddle2onnx 2.x needs
# Paddle 3.x, and the 2.6 checkpoints load fine in 3.1.1 (checked on the stock weights).
!uv venv --python 3.12 /content/py312_export
!uv pip install --python /content/py312_export/bin/python -r requirements.txt -c /content/constraints.txt setuptools paddlepaddle==3.1.1 paddle2onnx==2.1.0
PY_EXPORT = '/content/py312_export/bin/python'
!{PY_EXPORT} -c "import paddle, paddle2onnx; print('export env: paddle', paddle.__version__, '| paddle2onnx', paddle2onnx.__version__)"
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
import glob
drive.mount('/content/drive', force_remount=True)   # refresh a mount left over from an earlier run
parts =sorted(glob.glob('/content/drive/MyDrive/smartclear_ocr/ocr_rec.zip.part*'))
if not parts:
    raise SystemExit(
        "The data parts are not in My Drive. The folder was shared with you, so it sits under "
        "'Shared with me'. In Google Drive, open 'Shared with me', right-click the smartclear_ocr "
        "folder, choose 'Add shortcut to Drive' and put it in My Drive. Then run this cell again.")
print(len(parts), 'parts found')
!cat {' '.join(parts)} > /content/ocr_rec.zip
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
BATCH = 64
EPOCHS = 30
# Steps per epoch from the real training file (ceiling division), so validation runs once per epoch.
N_TRAIN = sum(1 for _ in open('/content/data/ocr_rec/train.txt'))
STEPS = -(-N_TRAIN // BATCH)
# Checkpoints go to Drive, so a disconnect cannot lose them.
FREEZE = True   # True: backbone frozen, only neck and heads train (the option we are testing)
OUT_DIR = '/content/drive/MyDrive/smartclear_ocr/runs/' + ('nrc_rec_frozen' if FREEZE else 'nrc_rec')
TRAIN_SCRIPT = '/content/train_frozen.py' if FREEZE else 'tools/train.py'
print('train crops', N_TRAIN, '| steps per epoch', STEPS)

cfg['Global'].update({
    'use_gpu': True, 'distributed': False, 'epoch_num': EPOCHS,
    'save_model_dir': OUT_DIR, 'save_epoch_step': 5,
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
    code(WRITE_WRAPPER),
    code("""
import subprocess
def run_logged(cmd, log, append=False):
    # Run a PaddleOCR command, keep its full output in `log`, and stop with the tail on failure.
    # Stream progress into the notebook as it happens (epoch, loss, validation scores, errors).
    keep = ('epoch:', 'cur metric', 'best metric', 'Error', 'Traceback', 'Exception')
    with open(log, 'a' if append else 'w') as f:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, errors='replace')
        for line in p.stdout:
            f.write(line)
            if any(k in line for k in keep):
                print(line.rstrip()[:220], flush=True)
        p.wait()
    if p.returncode != 0:
        print('FAILED with exit code', p.returncode, '- last lines of', log)
        print(open(log, errors='ignore').read()[-4000:])
        raise SystemExit(p.returncode)
    print('finished OK, log saved to', log)

# Smoke test: one epoch (about a minute). Catches setup problems before the long run.
run_logged([PY, TRAIN_SCRIPT, '-c', '/content/nrc_rec.yml',
            '-o', 'Global.epoch_num=1', 'Global.save_model_dir=/content/output/smoke',
            'Global.eval_batch_step=[0,100000]'], '/content/smoke.log')

# Full training. The log is the file the curves cell reads.
# If the runtime disconnected earlier, resume from the latest checkpoint on Drive
# (saved every 5 epochs) and keep appending to the same log.
import os
latest = OUT_DIR + '/latest'
if os.path.exists(latest + '.pdparams'):
    print('resuming from', latest)
    run_logged([PY, TRAIN_SCRIPT, '-c', '/content/nrc_rec.yml', '-o', 'Global.checkpoints=' + latest],
               '/content/train.log', append=True)
else:
    print('starting from the pretrained model')
    run_logged([PY, TRAIN_SCRIPT, '-c', '/content/nrc_rec.yml'], '/content/train.log')
"""),
    md("## 5. Evaluate on validation and test (exact-match accuracy)"),
    code("""
import subprocess
best = OUT_DIR + '/best_accuracy'
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
!{PY_EXPORT} tools/export_model.py -c /content/nrc_rec.yml -o Global.pretrained_model={best} \\
  Global.save_inference_dir=/content/inference/nrc_rec
!/content/py312_export/bin/paddle2onnx --model_dir /content/inference/nrc_rec \\
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
# PaddleOCR builds the list as blank + dictionary + a space, appended unconditionally,
# so the model has len(dictionary) + 2 outputs (97 here).
CHARS = ['blank'] + dict_chars + [' ']
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
for f in os.listdir(OUT_DIR):
    if f.startswith('best_accuracy') or f.startswith('latest'):
        shutil.copy(os.path.join(OUT_DIR, f), dest + '/checkpoint')
print('saved to', dest)
"""),
]


KAGGLE_INTRO = """
# NRC text recognition: fine-tune PP-OCRv4 (English), Kaggle version

Same steps as the Colab notebook, adapted for Kaggle:
- The data comes from the attached dataset **smartclear ocr data** (`/kaggle/input/smartclear-ocr-data`).
- Everything is written to `/kaggle/working`, which Kaggle keeps as the run's output.
- Run it with **Save Version > Save & Run All (Commit)**. It keeps running if you close the browser.

Settings before you run: Accelerator = GPU T4 x1, Internet = On.
Only synthetic data is used here.
"""

KAGGLE_DATA = """
# The data is the zip attached from the Kaggle dataset.
import os, zipfile
src = '/kaggle/input/smartclear-ocr-data/ocr_rec.zip'
assert os.path.exists(src), 'Attach the dataset first: Add Input > smartclear ocr data'
zipfile.ZipFile(src).extractall('/kaggle/working/data')
print(sorted(os.listdir('/kaggle/working/data/ocr_rec')))
"""

KAGGLE_BUNDLE = """
import datetime, shutil, os
dest = '/kaggle/working/model_bundle'
os.makedirs(dest + '/checkpoint', exist_ok=True)
for f in ['/kaggle/working/train.log', '/kaggle/working/nrc_rec.yml', '/kaggle/working/nrc_rec_onnx.zip']:
    if os.path.exists(f):
        shutil.copy(f, dest)
shutil.copytree('/kaggle/working/results', dest + '/results', dirs_exist_ok=True)
shutil.copytree('/kaggle/working/inference', dest + '/inference', dirs_exist_ok=True)
for f in os.listdir(OUT_DIR):
    if f.startswith('best_accuracy') or f.startswith('latest'):
        shutil.copy(os.path.join(OUT_DIR, f), dest + '/checkpoint')
print('model bundle saved to', dest)
"""


def to_kaggle(cells):
    """Turn the Colab cells into Kaggle cells: no Drive, no Colab downloads, /kaggle/working paths."""
    out = [md(KAGGLE_INTRO)]
    for c in cells:
        src = ''.join(c["source"])
        if c["cell_type"] == "markdown":
            text = ''.join(c["source"])
            if text.startswith("# NRC text recognition"):
                continue  # replaced by the Kaggle intro
            text = (text.replace("Google Drive", "Kaggle")
                        .replace("Drive folder `smartclear_ocr`", "attached Kaggle dataset")
                        .replace("Drive", "Kaggle"))
            out.append(md(text))
            continue
        if "drive.mount" in src:
            out.append(code(KAGGLE_DATA))
            continue
        if "datetime.datetime.now()" in src:
            out.append(code(KAGGLE_BUNDLE))
            continue
        lines = [l for l in src.splitlines() if "google.colab" not in l and "files.download" not in l]
        text = "\n".join(lines)
        text = text.replace("/content/drive/MyDrive/smartclear_ocr/runs/nrc_rec", "/kaggle/working/runs/nrc_rec")
        text = text.replace("/content/", "/kaggle/working/")
        out.append(code(text))
    return out


def write_nb(cells, path, colab: bool) -> None:
    nb = {
        "cells": cells,
        "metadata": {"accelerator": "GPU", "colab": {"provenance": []} if colab else {},
                     "kernelspec": {"display_name": "Python 3", "name": "python3"}},
        "nbformat": 4, "nbformat_minor": 0,
    }
    path.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", path)


def main() -> None:
    write_nb(CELLS, HERE / "nrc_rec_finetune.ipynb", colab=True)
    write_nb(to_kaggle(CELLS), HERE / "nrc_rec_finetune_kaggle.ipynb", colab=False)


if __name__ == "__main__":
    main()
