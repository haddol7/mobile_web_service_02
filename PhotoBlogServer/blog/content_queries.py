"""Shared ORM predicates for the web view and Android-facing JSON search."""
from django.db.models import Exists, OuterRef, Q
from .content_rules import normalize
from .models import PhotoTextLine


def filter_content(posts, *, theme="", tag="", terms=(), author=None):
    if theme == "unclassified":
        posts = posts.filter(Q(content__isnull=True) | Q(content__theme__isnull=True))
    elif theme:
        posts = posts.filter(content__theme=theme)
    if tag:
        posts = posts.filter(content__tags__normalized=normalize(tag))
    if author is not None:
        posts = posts.filter(author=author)
    for term in terms:
        matches = PhotoTextLine.objects.filter(content__post_id=OuterRef("pk")).filter(
            Q(norm_text__contains=term) | Q(compact_text__contains=term.replace(" ", "")))
        posts = posts.filter(Exists(matches))
    return posts


def matching_line_ids(lines, terms):
    """Choose the fewest relevant OCR lines covering all query terms."""
    if not terms:
        return []
    candidates = []
    for line in lines:
        normalized = normalize(line["text"])
        compact = normalized.replace(" ", "")
        hits = {term for term in terms if term in normalized or term.replace(" ", "") in compact}
        if hits:
            candidates.append((line["line_id"], hits))
    required = set(terms)
    complete = [line_id for line_id, hits in candidates if hits == required]
    if complete:
        return complete
    # A query may span two OCR lines. Cover every term without highlighting
    # additional lines merely because they repeat a common word.
    remaining = set(required)
    selected = []
    while remaining:
        best = max(candidates, key=lambda item: len(item[1] & remaining), default=None)
        if best is None or not best[1] & remaining:
            return []
        selected.append(best[0])
        remaining -= best[1]
    return [line_id for line_id, _ in candidates if line_id in selected]
