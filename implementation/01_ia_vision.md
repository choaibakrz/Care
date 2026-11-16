# Job 1: AI vision engineer

**Mission:** the robot looks at a shelf or a table and says which clinic tools and supplies are there, where, and how sure it is. You train and serve the neural networks that do this.

You own `implementation/model_service/` and one new file, `briques/b05_yeux/branchements/service_http.py`. You do not touch the gardien, the prise or the brain. Vision never commands the robot. It only reports what it sees, to the gardien (people) and the brain (objects).

Read first: [architecture.md](architecture.md) (contract C1), `briques/b05_yeux/GUIDE.md`, `briques/b05_yeux/prise_yeux.py` (the `Branchement` and `Objet` types), `briques/b05_yeux/branchements/mediapipe_objets.py` (an example plug-in), `briques/b05_yeux/MESURES.md`, `briques/clinique/faux_dossier/reserve.yaml` (the five items already in the clinic).

## The gap you fill

The current eyes only know 80 generic COCO objects (`bottle`, `cup`, `person`). They cannot tell a neck cushion from a big cushion, and know no clinic tools. `DECISIONS.md` lists "named objects and people: to be proposed". That is you.

## What you build

### P0. Mock first (first hour)
- [ ] FastAPI app `model_service/app.py` with `GET /v1/health`, `POST /v1/detect`, `GET /v1/classes`, returning fixed boxes from a JSON file. Job 2 builds against this immediately.
- [ ] `classes.yaml`: the list of class keys with names in fr, de, en, it, zh (same style as `commun/monde.yaml`) and a `version`. Agree the list with jobs 2 and 3 before you train anything.
  Start with the 5 reserve items (big cushion, neck cushion, blanket, water bottle, exercise sheet) plus about 7 common clinic tools. Candidates: stethoscope, thermometer, scissors, bandage roll, syringe (training dummy), blood-pressure cuff, glove box, tray. Hiba confirms.
- [ ] `models.yaml`: which model answers which endpoint. The robot never names a model.

### P0. Multi-object detector (the main deliverable)
Detect several tools in one image with boxes and labels.
- [ ] **Data.** Photograph the real objects: 40 to 60 images per class, varied backgrounds, lighting, distances, partly hidden, several objects per image. Add camera frames from the simulation (job 2) for the robot's point of view. Use public datasets only if the licence is compatible. Record every source in `LICENCES.md`.
- [ ] **Labelling.** CVAT or Label Studio, run locally. To go faster, pre-label with a zero-shot detector (OWL-ViT or OWLv2, Grounding DINO; check licence and size first) and correct by hand.
- [ ] **Split by session, not by image.** Photos from the same shooting session go entirely to train or entirely to test. Otherwise your numbers lie.
- [ ] **Fine-tune** a small pretrained detector. Pick one with an open licence:
  - torchvision SSDlite or Faster R-CNN MobileNetV3 (BSD)
  - RT-DETR (Apache-2.0)
  - YOLOX (Apache-2.0)
  - re-train the MediaPipe EfficientDet-Lite0 already used here (Apache-2.0)

  **Avoid Ultralytics YOLO** unless Hiba accepts AGPL-3.0 (`LICENCES.md` rule).
- [ ] **Export to ONNX** and run with onnxruntime (CoreML provider on the Mac). Keep PyTorch for training only.
- [ ] **Budget:** under 1 GB of memory, aiming for under 200 ms per image on the iMac M4. Apertus 8B and speech share the same 16 GB. Measure and write the real numbers down.

### P1. Crop classifier for look-alikes
Detection is bad at telling near-identical things apart (big cushion vs neck cushion, the exact case the brain asks a question about).
- [ ] A small image classifier (MobileNetV3, EfficientNet-B0, or a frozen CLIP or DINOv2 encoder with a linear head) run on each detected box.
- [ ] **Open-set rule:** under a confidence threshold the answer is `unknown`, never a forced guess. `unknown` feeds the existing "I'm not sure" path (`b08_doute`), which asks a human.
- [ ] Few-shot add: a new tool must be addable from about 20 photos by retraining only the classifier, without touching the detector.

### P1. Wire into the robot
- [ ] `branchements/service_http.py`: a `Branchement` (same interface as `mediapipe_objets.py`) that sends the frame to `POST /v1/detect` and returns `Objet` items (`etiquette`, `nom`, `boite`, `confiance`, `source`). Unreachable service means the branch reports itself absent and the others continue, as the existing design already does.
- [ ] Add the plug-in to `reglages.yaml` (`yeux.branchements`). Eyes switched off must change nothing.

### P2. Extras (only if the rest is solid)
- [ ] Shelf counting: several of the same item in one image, returned as separate boxes (job 2 turns them into `inventory.seen`).
- [ ] `POST /v1/transcribe` and `POST /v1/translate`: thin HTTP wrappers over `b04` and `clinique/interprete.py`. Model code stays where it is.
- [ ] Image quality guard: blurred or dark frames return a `low_quality` flag instead of confident nonsense.

## Evaluation (this is half of the job)

Write `model_service/MESURES.md`, following the style of the other `MESURES.md` files. Include the machine each number was measured on.

| Measure | Why |
| --- | --- |
| mAP@0.5 and recall per class | Which tools are weak |
| Confusion matrix | Which look-alikes fail |
| False positives on empty shelves and on random objects | A robot that "sees" a scalpel that is not there is worse than one that misses it |
| `unknown` rate on objects not in the class list | Tests the open-set rule |
| Latency and memory, cold and warm | Fits next to Apertus |
| Behaviour with the simulated frames vs real photos | Sim-to-real gap, stated honestly |

Mark anything not run on the real robot camera as **not tested**.

## Interfaces

| You give | To | When |
| --- | --- | --- |
| C1 mock service and `classes.yaml` | Jobs 2 and 3 | M0 |
| A first real detector, even weak | Job 2 | before M2 |
| Class list with names in 5 languages | Job 2 (maps to `monde.yaml`), job 3 (inventory items) | M0 |

| You need | From | When |
| --- | --- | --- |
| Simulated camera frames | Job 2 | as early as possible |
| Real photos and a camera at the venue | the whole team | Saturday |

## Privacy

Images are processed in memory and never written to disk by default. A `--debug-save` flag may keep frames for training, off by default, with a visible console warning. Never log image content. Keep training photos out of the git repository (add the folder to `.gitignore`, like `modeles/`).

## Done when

- `POST /v1/detect` on a photo with three known tools returns three correct labelled boxes, from the robot, over the local network, with the internet off.
- `MESURES.md` has per-class numbers and the latency measured on a Mac.
- A tool not in the class list comes back `unknown`, not a wrong name.
- `python3 lancer.py tests briques/b05_yeux` still passes with your plug-in on and off.
