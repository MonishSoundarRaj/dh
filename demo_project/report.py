"""Print each student's average and letter grade:  python3 report.py"""
from grades import average, letter_grade
from loader import load_scores


def build_report(path):
    lines = []
    for name, scores in load_scores(path).items():
        avg = average(scores)
        lines.append(f"{name}: {avg:.1f} ({letter_grade(avg)})")
    return lines


if __name__ == "__main__":
    print("\n".join(build_report("roster.csv")))
