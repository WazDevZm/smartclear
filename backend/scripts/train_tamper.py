"""Train the field-level tamper detector on synthetic data.

Training data
  * real samples:      every (document, field) of the synthetic NRC set, labelled from data/facilitator_ground_truth.csv
  * synthetic forgeries: genuine fields altered by smartclear.synth (4 techniques)
  * benign augments:   genuine fields with JPEG/noise/brightness changes (label 0)

Evaluation is honest about the data: 5-fold cross-validation grouped by DOCUMENT.
Synthetic forgeries are generated only from the training-fold documents, and metrics
are computed only on the REAL held-out samples (incl. the real tampered cards).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import joblib  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402

from smartclear.config import GROUND_TRUTH_CSV, MODELS_DIR, STORAGE_DIR, TAMPER_MODEL_PATH  # noqa: E402
from smartclear.forensics import FEATURE_NAMES, FIELDS, compute_features, crop_box, vectorize  # noqa: E402
from smartclear.synth import TECHNIQUES, benign_augment, tamper  # noqa: E402

CACHE = STORAGE_DIR / "cache" / "docs"
SYN_PER_FIELD = 3       # forgeries per genuine field (per technique sampled at random)
AUG_PER_FIELD = 2       # benign augments per genuine field


def load():
    gt = {r["doc_id"]: r for r in csv.DictReader(open(GROUND_TRUTH_CSV))}
    docs = []
    for doc_id, g in sorted(gt.items()):
        js = CACHE / f"{doc_id}.json"
        if not js.exists():
            continue
        rec = json.loads(js.read_text())
        img = cv2.imread(str(CACHE / f"{doc_id}.png"))
        docs.append((doc_id, g, rec, img))
    return docs


def padded(box, img, pad=12):
    x0, y0, x1, y1 = box
    H, W = img.shape[:2]
    return [max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)]


def real_samples(docs):
    X, y, groups, meta = [], [], [], []
    for doc_id, g, rec, img in docs:
        for f in FIELDS:
            box = rec["forensic_boxes"].get(f)
            if not box:
                continue
            X.append(vectorize(compute_features(crop_box(img, box), f)))
            y.append(int(g["tampered_field"] == f))
            groups.append(doc_id)
            meta.append((doc_id, f))
    return np.array(X), np.array(y), np.array(groups), meta


def synthetic_samples(docs, seed):
    rng = np.random.default_rng(seed)
    X, y = [], []
    for doc_id, g, rec, img in docs:
        vals = {k: v["value"] for k, v in rec["extraction"]["fields"].items()}
        for f in FIELDS:
            box = rec["forensic_boxes"].get(f)
            if not box or g["tampered_field"] == f:
                continue
            pb = padded(box, img)
            for _ in range(SYN_PER_FIELD):
                tech = TECHNIQUES[int(rng.integers(len(TECHNIQUES)))]
                t_img = tamper(img, box, f, vals.get(f), tech, rng)
                region = t_img.copy()
                x0, y0, x1, y1 = pb
                region[y0:y1, x0:x1] = benign_augment(t_img[y0:y1, x0:x1], rng) if rng.random() < 0.6 \
                    else t_img[y0:y1, x0:x1]
                X.append(vectorize(compute_features(crop_box(region, box), f)))
                y.append(1)
            for _ in range(AUG_PER_FIELD):
                region = img.copy()
                x0, y0, x1, y1 = pb
                region[y0:y1, x0:x1] = benign_augment(img[y0:y1, x0:x1], rng)
                X.append(vectorize(compute_features(crop_box(region, box), f)))
                y.append(0)
    return np.array(X), np.array(y)


def make_model():
    return RandomForestClassifier(n_estimators=400, min_samples_leaf=2, class_weight="balanced_subsample",
                                  random_state=7, n_jobs=-1)


def main():
    docs = load()
    print(f"documents: {len(docs)}")
    Xr, yr, gr, meta = real_samples(docs)
    print(f"real field samples: {len(yr)} ({yr.sum()} tampered)")

    # ---- Cross-validation: synthetic from train folds only, score on real held-out
    oof = np.zeros(len(yr))
    oof_syn_only = np.zeros(len(yr))
    gkf = GroupKFold(n_splits=5)
    doc_index = {d[0]: d for d in docs}
    for k, (tr, te) in enumerate(gkf.split(Xr, yr, gr)):
        tr_docs = [doc_index[d] for d in sorted(set(gr[tr]))]
        Xs, ys = synthetic_samples(tr_docs, seed=100 + k)
        m = make_model().fit(np.vstack([Xs, Xr[tr]]), np.concatenate([ys, yr[tr]]))
        oof[te] = m.predict_proba(Xr[te])[:, 1]
        m2 = make_model().fit(np.vstack([Xs, Xr[tr][yr[tr] == 0]]), np.concatenate([ys, yr[tr][yr[tr] == 0]]))
        oof_syn_only[te] = m2.predict_proba(Xr[te])[:, 1]
        print(f"  fold {k + 1}: {len(ys)} synthetic samples")

    def report(p, name):
        pred = (p >= 0.5).astype(int)
        r = {
            "roc_auc": round(float(roc_auc_score(yr, p)), 4),
            "average_precision": round(float(average_precision_score(yr, p)), 4),
            "precision@0.5": round(float(precision_score(yr, pred, zero_division=0)), 4),
            "recall@0.5": round(float(recall_score(yr, pred, zero_division=0)), 4),
            "false_positives@0.5": int(((pred == 1) & (yr == 0)).sum()),
            "missed@0.5": [f"{meta[i][0]}:{meta[i][1]}" for i in np.where((pred == 0) & (yr == 1))[0]],
        }
        print(name, json.dumps(r, indent=1))
        return r

    cv_full = report(oof, "CV (synthetic + real train folds) on real held-out:")
    cv_syn = report(oof_syn_only, "CV (synthetic forgeries only, no real tamper examples) on real held-out:")

    # ---- Final model on everything
    Xs, ys = synthetic_samples(docs, seed=1)
    model = make_model().fit(np.vstack([Xs, Xr]), np.concatenate([ys, yr]))
    imp = sorted(zip(FEATURE_NAMES, model.feature_importances_), key=lambda z: -z[1])
    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump({"model": model, "features": FEATURE_NAMES,
                 "medians": dict(zip(FEATURE_NAMES, np.median(Xr[yr == 0], axis=0).tolist())),
                 "iqr": dict(zip(FEATURE_NAMES, (np.percentile(Xr[yr == 0], 75, axis=0) -
                                                 np.percentile(Xr[yr == 0], 25, axis=0)).tolist()))},
                TAMPER_MODEL_PATH)
    metrics = {"n_documents": len(docs), "n_real_samples": int(len(yr)), "n_real_tampered": int(yr.sum()),
               "n_synthetic_samples_final": int(len(ys)), "cv_synthetic_plus_real": cv_full,
               "cv_synthetic_only": cv_syn, "feature_importance": [[n, round(float(v), 4)] for n, v in imp[:12]],
               "oof_scores": {f"{d}:{f}": round(float(s), 4) for (d, f), s in zip(meta, oof)}}
    (MODELS_DIR / "tamper_metrics.json").write_text(json.dumps(metrics, indent=2))
    print("saved", TAMPER_MODEL_PATH)
    print("top features:", imp[:8])


if __name__ == "__main__":
    main()
