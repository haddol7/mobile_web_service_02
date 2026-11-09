"""Draw stored detector coordinates on display copies; never modify source media."""
from functools import lru_cache
from io import BytesIO
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BODY = "#38bdf8"
CANDIDATE = "#fbbf24"
CONFIRMED = "#34d399"
UNKNOWN = "#cbd5e1"
FONT = Path(__file__).resolve().parent / "fonts" / "PretendardVariable.ttf"


@lru_cache(maxsize=12)
def font(size):
    return ImageFont.truetype(str(FONT), size=size)


def scaled_box(box, source_size, target_size):
    if not isinstance(box, (list, tuple)) or len(box) != 4 or len(source_size) != 2:
        return None
    try:
        width, height = map(float, source_size)
        values = list(map(float, box))
        if not all(math.isfinite(v) for v in (width, height, *values)) or min(width, height) <= 0:
            return None
        tw, th = target_size
        x1, y1, x2, y2 = values
        if x2 <= x1 or y2 <= y1:
            return None
        result = (max(0, min(tw - 1, round(x1 * tw / width))),
                  max(0, min(th - 1, round(y1 * th / height))),
                  max(0, min(tw - 1, round(x2 * tw / width))),
                  max(0, min(th - 1, round(y2 * th / height))))
        return result if result[2] > result[0] and result[3] > result[1] else None
    except (TypeError, ValueError, OverflowError):
        return None


def render_overlay(image, source_size, observations, unassigned_faces):
    image = image.convert("RGB")
    draw = ImageDraw.Draw(image)
    text_font = font(max(12, min(24, round(image.width / 42))))
    stroke = max(2, round(image.width / 350))
    labels = []
    count = 0

    def rectangle(box, color, label):
        nonlocal count
        coordinates = scaled_box(box, source_size, image.size)
        if coordinates is None:
            return
        draw.rectangle(coordinates, outline=color, width=stroke)
        labels.append((coordinates, color, label))
        count += 1

    for observation in observations:
        track = observation.track
        rectangle(observation.bbox, BODY, f"#{track.track_id}")
        if not observation.face_bbox:
            continue
        if track.confirmed_id:
            state = "정답 확인" if track.review_basis == "dataset" else "확인"
            label = f"{track.confirmed.display_name[:18]} {state}"
            color = CONFIRMED
        elif track.reviewed_at is None and observation.candidate_id:
            label = f"{observation.candidate.display_name[:18]} 후보"
            if observation.similarity is not None:
                label += f" {observation.similarity:.2f}"
            color = CANDIDATE
        else:
            label, color = "얼굴 미확인", UNKNOWN
        rectangle(observation.face_bbox, color, label)
    for face in unassigned_faces:
        # An unlinked face does not inherit the identity of a nearby body.
        rectangle(face.get("bbox"), UNKNOWN, "얼굴 미확인")

    occupied = []
    face_boxes = [box for box, color, _ in labels if color != BODY]
    for box, color, text in sorted(labels, key=lambda item: item[1] != BODY):
        # Prefer free space around a detection rather than covering another face or label.
        while len(text) > 2 and draw.textbbox((0, 0), text, font=text_font)[2] > image.width - 8:
            text = text[:-2] + "…"
        bounds = draw.textbbox((0, 0), text, font=text_font)
        width, height = bounds[2] + 8, bounds[3] - bounds[1] + 8
        choices = [(box[0], box[1] - height), (box[0], box[3] + 3),
                   (box[2] - width, box[1] - height), (box[2] + 4, box[1]),
                   (box[0] - width - 4, box[1]), (box[0], box[1] + stroke)]
        def overlap(first, second):
            return max(0, min(first[2], second[2]) - max(first[0], second[0])) * max(0, min(first[3], second[3]) - max(first[1], second[1]))
        candidates = []
        for left, top in choices:
            left = max(0, min(left, image.width - width))
            top = max(0, min(top, image.height - height))
            rect = (left, top, left + width, top + height)
            penalty = sum(overlap(rect, previous) for previous in occupied) * 4 + sum(overlap(rect, face) for face in face_boxes) * 2
            candidates.append((penalty, rect))
        chosen = min(candidates, key=lambda choice: choice[0])[1]
        occupied.append(chosen)
        x, y = chosen[:2]
        draw.rounded_rectangle((x, y, min(image.width - 1, x + width), min(image.height - 1, y + height)), radius=3, fill="#10252d")
        draw.text((x + 4, y + 4 - bounds[1]), text, font=text_font, fill=color)
    return image, count


def annotated_image(frame):
    observations = list(frame.observations.select_related("track__confirmed", "candidate"))
    with frame.image.open("rb") as source, Image.open(source) as original:
        image, count = render_overlay(original, frame.image_size, observations, frame.unassigned_faces)
        output = BytesIO()
        image.save(output, "JPEG", quality=90)
    return output.getvalue(), count
