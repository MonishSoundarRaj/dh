"""Read the class roster: one row per student, one column per assignment."""
import csv


def load_scores(path):
    """Return {name: [score, ...]} in file order. Scores can have decimals, like 92.5."""
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    scores = {}
    for name, *values in rows[1:]:  # skip the header row
        scores[name] = [int(value) for value in values]
    return scores
