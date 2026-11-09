"""Conservative ground-truth checks for public research demonstrations."""


def ground_truth_identity(box,people):
    left,top,right,bottom=box
    matches=[person["identity"] for person in people
             if all(left<=x<=right and top<=y<=bottom for x,y in person["eyes"])]
    return matches[0] if len(matches)==1 else None


def dataset_track_identity(matches,candidate):
    # An ID switch in one body track cannot be hidden by choosing its best frame.
    identities={value for value in matches if value is not None}
    if len(identities)!=1 or sum(value is not None for value in matches)<2:
        return None
    expected=next(iter(identities))
    return expected if candidate=="chokepoint-"+expected else None
