"""falseref PATH [PATH ...] [-o report.csv]"""

import argparse
import logging

from .pipeline import check_path
from .report import summary, to_frame, write_csv


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="falseref",
        description="Check the reference lists of submissions (PDF, DOC, DOCX, or a zip of them).",
    )
    parser.add_argument("paths", nargs="+", help="documents or zip files to check")
    parser.add_argument("-o", "--output", default="reference_report.csv", help="CSV to write (default: %(default)s)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    reports = [r for path in args.paths for r in check_path(path)]
    write_csv(to_frame(reports), args.output)
    print(summary(reports))
    print(f"\nreport written to {args.output}")


if __name__ == "__main__":
    main()
