# Medical supply recognition for a storage-sorting robot — design

Date: 2026-11-14 · Status: draft for approval · Stack: PyTorch, Ultralytics YOLO26, small pretrained encoders

## 1. Intent

A robot looks at a drawer or shelf (top-down camera), finds every medical item in it, says what each item is, and sends it to the right storage place. Items are often sealed boxes or sterile packs, so appearance alone is not always enough: later stages read the label text or barcode.

The vision part must be a **separate, swappable service**: the robot sends an image and receives structured results. No robot code depends on a specific model.

This document covers the vision models, how to fine-tune them on the two datasets found so far, and the code structure. It does not cover robot control, the app, or the admin panel.

## 2. Goals, non-goals, anti-goals

**Goals**
- Detect all items in a drawer image, including overlapping ones, with high recall.
- Name each item, or say "unknown" instead of guessing.
- Give the robot a position and an orientation per item, plus the drawer scale in mm.
- Fine-tune on both datasets with a repeatable, config-driven pipeline.
- Add a new product with a few reference photos and no retraining of the detector.

**Non-goals (for now)**
- Reading label text or barcodes (a later "second look" stage; the interface is reserved).
- Training on patient data or anything with faces.
- Real-time performance on the robot's own computer (assume a laptop/server GPU or CPU).

**Anti-goals** (failures even if the metrics look fine)
- Confidently wrong labels on look-alike products (for example syringe sizes).
- A model that only works on the exact drawer it was trained on.
- Silent data errors: wrong class mapping, corrupt images, leakage between train and test.

## 3. What is known about the datasets, and what is not

| | Hospital Consumables | BioSafety PPE Detection |
|---|---|---|
| Source | Roboflow Universe, `skripsie-ghhbu/hospital-consumables` | Roboflow Universe, `defect-detection-ttidk/biosafety-ppe-detection-u2ha2` |
| License | CC BY 4.0 (from the page) | CC BY 4.0 and object detection (from a search listing; page not readable) |
| Classes | 7: bandage, box-of-gloves, box-of-masks, dressing-tray, square, syringe, triangle | **Unverified** |
| Image count, task type (boxes or polygons), capture setup | Not shown on the page | Unknown |

The `browse` views of both datasets block automated access, so image content could not be inspected. Everything below that depends on image content is marked **to confirm after export**.

Two inferences, both to verify:
- `square` and `triangle` in Hospital Consumables are probably fiducial/marker shapes, like the square markers in the example drawer image. If so, this dataset comes from a drawer-like setup close to the target.
- BioSafety PPE very likely shows PPE worn on people in labs. That is far from "items stored in a drawer", so its value is limited to teaching general PPE appearance.

## 4. Approaches considered

| Approach | Idea | Trade-off |
|---|---|---|
| **A. Merged label space, staged fine-tuning (chosen)** | Map both datasets onto one taxonomy, train one detector in phases (warm-up on PPE, main fit on drawer data, with replay), plus a separate embedding recognizer | One model to deploy; needs a careful class mapping; forgetting handled by replay |
| B. One YOLO per dataset | Two detectors, run both | Simple to train; doubles inference; no shared learning; conflicting detections to resolve |
| C. Pure sequential fine-tuning | Fine-tune on dataset 1, then on dataset 2 | Simplest; forgets dataset 1 classes that dataset 2 lacks |
| D. One YOLO with all fine classes, no recognizer | Detector does everything | Fine for 7–15 classes; cannot add products without retraining; weak on look-alikes |

**Chosen: A.** D remains the baseline that A must beat (section 8).

**Stack calls** (mine, changeable): PyTorch end to end; Ultralytics YOLO26 for detection (AGPL-3.0 unless a commercial license is bought; fine for a hackathon, revisit for a product; RF-DETR under Apache 2.0 is the swap-in candidate behind the same interface); DINOv3 ViT-S/16 as the recognizer encoder (SigLIP 2 ViT-B as the alternative); OpenCV ArUco for markers.

## 5. Architecture

```
drawer image
  │
  ▼
[1] Detector (YOLO26, detect or seg)  → boxes + coarse group + score
  │        groups: marker | pack | box | tray | ppe
  ├─ markers ─► MarkerReader (OpenCV ArUco, else detector boxes) → drawer pose, mm per pixel
  ▼
[2] Refiner (optional): SAM prompted by each box → mask → min-area rectangle → angle, clean crop
  ▼
[3] Recognizer: crop → DINOv3 embedding → cosine kNN against gallery (+ optional linear head)
        → fine label | "unknown" (similarity below calibrated threshold)
  ▼
[4] Result assembly: label, confidence, box, angle, size in mm, status
  ▼
service boundary: image in → JSON out
```

Decisions inside it:
- **Axis-aligned boxes first.** The Roboflow exports are most likely axis-aligned boxes (to confirm). They cannot be turned into correct oriented boxes automatically. So stage 1 is a normal YOLO26 detector, and orientation comes from the mask refiner. If the exports contain polygons, train `yolo26s-seg` and skip the refiner's SAM step. If you later label your own drawer photos with oriented boxes, `yolo26s-obb` replaces the pair.
- **Coarse groups in the detector, fine labels in the recognizer.** Detecting "a pack" is easy to learn and transfers across datasets; naming it is the recognizer's job.
- **Detector overlap:** raise the NMS IoU (about 0.6–0.7) or use the NMS-free mode; items legitimately overlap.
- **Recall over precision:** a missed item is worse than a spurious box that stage 3 rejects as "unknown".
- **Scale:** markers give mm per pixel; length and width in mm are extra features that separate look-alike products.

## 6. Label mapping (the part most likely to go wrong)

One file, `config/taxonomy.yaml`, maps every source class to `(group, fine_label)`. Worn PPE and stored boxes get **different** fine labels so the recognizer never learns "glove = person's hand".

```yaml
hospital_consumables:
  bandage:        {group: pack,   fine: bandage}
  syringe:        {group: pack,   fine: syringe}
  box-of-gloves:  {group: box,    fine: gloves_box}
  box-of-masks:   {group: box,    fine: masks_box}
  dressing-tray:  {group: tray,   fine: dressing_tray}
  square:         {group: marker, fine: marker_square}
  triangle:       {group: marker, fine: marker_triangle}
biosafety_ppe:        # fill in after export; names below are placeholders
  mask:      {group: ppe, fine: mask_worn}
  gloves:    {group: ppe, fine: gloves_worn}
  goggles:   {group: ppe, fine: goggles_worn}
```

The merge script fails loudly if any source class is missing from the mapping, or if a mapped class does not exist in the dataset's `data.yaml`.

## 7. Fine-tuning plan per dataset

Hyperparameters are starting points to tune, not results.

**Phase 0, baseline.** COCO-pretrained `yolo26s.pt` evaluated on the Hospital Consumables validation split without training. This is the floor.

**Phase 1, BioSafety PPE (warm-up, optional).** Purpose: teach general PPE appearance. Group `ppe`. 30–50 epochs, `freeze=10`, `imgsz=640`, standard augmentation. Keep only if the ablation in section 8 shows it helps Phase 2; otherwise skip it, because the domain gap is large.

**Phase 2, Hospital Consumables (main fit).** The closest dataset to the target.
- Train on Hospital Consumables plus a 20–30% replay sample of BioSafety, so PPE groups are not forgotten.
- All layers unfrozen, `lr0` about 0.001 with cosine decay, 100–150 epochs, `imgsz=960` (small items), early stopping on validation recall.
- Augmentation for top-down drawers: `degrees=180`, `flipud=0.5`, `fliplr=0.5`, mosaic on and switched off for the last epochs (`close_mosaic`), `copy_paste` on, `mixup` off, light HSV only (colour is a signal on vials and labels).

**Phase 3, own drawer photos (later).** Same recipe at a lower learning rate. This is where oriented boxes or masks get introduced.

**Recognizer (separate from the detector).**
1. Crop every ground-truth box from both datasets (with random jitter on the box, to mimic detector error), mask out neighbours when masks exist.
2. Build a gallery: DINOv3 embeddings of training crops, tagged with source dataset. No training needed; this is the baseline.
3. Optional: a cosine linear head, 10–20 epochs on frozen features; then unfreeze the last two blocks at a very low learning rate with ArcFace or supervised-contrastive loss.
4. Calibrate the "unknown" threshold by leaving one class out at a time and measuring how often it is rejected.

## 8. Evaluation and checks

- **No leakage.** Roboflow splits often contain near-identical frames. Cluster images by perceptual hash and re-split by cluster; report both the original and the clean split.
- **Detector:** mAP50-95, recall at IoU 0.5, per-drawer item-count accuracy, per-dataset reporting, confusion matrix by group.
- **Recognizer:** top-1 on known classes, rejection rate on held-out classes, AUROC for known vs unknown, and a **head-to-head against the detector's own fine-class head on the same crops**. If the detector alone wins, the recognizer waits until there are more products than the detector can handle.
- **Ablations:** with vs without Phase 1; with vs without replay; 640 vs 960 input.
- **Failure review:** save the 50 worst crops after each run and look at them.

## 9. Code structure (OOP, defensive)

```
medsort/
  config/        taxonomy.yaml, detector.yaml, recognizer.yaml   (validated with pydantic)
  data/          RoboflowExport (load + validate), DatasetMerger, LeakageChecker
  detection/     Detector (ABC), YoloDetector, MaskRefiner
  recognition/   Embedder (ABC), DinoEmbedder, GalleryIndex, UnknownRejector
  markers/       MarkerReader
  training/      PhaseTrainer (template method) → DetectorPhase, RecognizerPhase
  service/       thin HTTP/CLI wrapper: image in, JSON out
  errors.py      PipelineError → DataError, ConfigError, DetectionError, RecognitionError
  tests/
```

Error handling rules:
- Validate every export before training: missing label files, class ids out of range, boxes outside the image, corrupt or empty images, duplicate files across splits. Raise a `DataError` that names the file.
- Fail fast on config errors; never fall back silently to another model or class mapping.
- Seeds, library versions and the git commit are written next to every checkpoint.
- Structured logging; each inference result carries a `status` (`ok`, `unknown`, `low_confidence`, `error`).
- Unit tests for the merger, the mapping validation and the gallery rejection logic run without a GPU.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Dataset class names or formats differ from assumptions | `RoboflowExport` reads `data.yaml`; mapping validated before any training |
| BioSafety PPE (worn) does not help stored-item detection | Phase 1 is optional and ablated |
| Overlap hurts recall | NMS tuning or NMS-free mode; mask refiner; recall-first early stopping |
| Roboflow data is small or from one drawer | Own drawer photos in Phase 3; copy-paste and rotation augmentation |
| Look-alike products | Size in mm as a feature; later text/barcode second look |
| AGPL-3.0 on Ultralytics in a product | Swap detector to RF-DETR (Apache 2.0) behind `Detector` |
| CC BY 4.0 requires attribution | `ATTRIBUTION.md` lists both datasets and authors |

## 11. Left to the builder

- Exact export format and per-class counts after downloading (Roboflow API key or manual zip).
- Final `imgsz` and batch size for the available GPU.
- Whether to use detect or seg once the export format is known.
- The wire format of the service boundary (HTTP or a local queue).