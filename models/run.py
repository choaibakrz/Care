"""Load a trained checkpoint and detect medical equipment in an image.

From another project:

    from run import load_model, detect

    model = load_model("runs/freeze10-3/weights/best.pt")
    for d in detect(model, "photo.jpg"):          # also accepts a PIL image or an OpenCV (BGR) array
        print(d["name"], d["confidence"], d["box"])

From the command line (prints JSON):

    uv run python run.py photo.jpg --weights runs/freeze10-3/weights/best.pt
    uv run python run.py photo.jpg --weights best.pt --conf 0.4 --save out.jpg
"""

import argparse
import json

from ultralytics import YOLO


def load_model(weights):
    """Load a checkpoint. The .pt file carries its own architecture and class names."""
    return YOLO(weights)


def detect(model, image, conf=0.25, imgsz=640, save=None):
    """Detect objects in one image.

    image: file path, PIL image, or numpy array in OpenCV BGR order.
    save:  optional path; writes the image with boxes drawn on it.

    Returns a list of dicts, most confident first:
        name        class name, e.g. "scalpel"
        class_id    class index in the model
        confidence  0-1
        box         [x1, y1, x2, y2] in pixels of the input image
        center      [x, y] in pixels, handy for a robot pick point
    """
    result = model.predict(image, conf=conf, imgsz=imgsz, verbose=False)[0]
    if save:
        result.save(save)
    detections = []
    for (x1, y1, x2, y2), score, cls in zip(
        result.boxes.xyxy.tolist(), result.boxes.conf.tolist(), result.boxes.cls.int().tolist()
    ):
        detections.append({
            "name": result.names[cls],
            "class_id": cls,
            "confidence": round(score, 4),
            "box": [round(v, 1) for v in (x1, y1, x2, y2)],
            "center": [round((x1 + x2) / 2, 1), round((y1 + y2) / 2, 1)],
        })
    return sorted(detections, key=lambda d: -d["confidence"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help="image file to run on")
    ap.add_argument("--weights", required=True, help="trained .pt checkpoint")
    ap.add_argument("--conf", type=float, default=0.25, help="confidence threshold")
    ap.add_argument("--imgsz", type=int, default=640, help="size the model sees; match the training size")
    ap.add_argument("--save", default=None, help="write the image with boxes drawn to this path")
    args = ap.parse_args()

    detections = detect(load_model(args.weights), args.image, args.conf, args.imgsz, args.save)
    print(json.dumps(detections, indent=2))


if __name__ == "__main__":
    main()
