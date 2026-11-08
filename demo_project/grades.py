"""Grading rules for the course."""


def average(scores):
    """Mean of a list of scores."""
    return sum(scores) / len(scores)


def letter_grade(score):
    """90 and up is an A, 80 and up is a B, 70 and up is a C, 60 and up is a D."""
    if score > 90:
        return "A"
    if score > 80:
        return "B"
    if score > 70:
        return "C"
    if score > 60:
        return "D"
    return "F"
