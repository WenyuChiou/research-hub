"""Three illustrative cancellation cases; run with Python to print measured JSON."""

import json
import math
import platform
import sys


def measure():
    cases = [
        [1e16, 1, -1e16],
        [1e16, -1e16, 1],
        [1e16, 1, 1, -1e16],
    ]
    observations = []
    for index, values in enumerate(cases, start=1):
        naive = 0.0
        for value in values:
            naive += value
        observations.append({
            "case_id": f"case-{index}",
            "inputs": values,
            "exact_integer_sum": sum(int(value) for value in values),
            "results": {
                "naive_loop": naive,
                "math_fsum": math.fsum(values),
                "builtin_sum": sum(values),
            },
        })
    return {
        "schema_version": 1,
        "label": "DEMO: measured floating-point cancellation examples",
        "runtime": {
            "python": sys.version,
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "methods": {
            "naive_loop": "Start at 0.0; add each input with += in the listed order.",
            "math_fsum": "Call math.fsum(values).",
            "builtin_sum": "Call sum(values) in the recorded Python runtime.",
            "exact_integer_sum": "Sum integer conversions; every listed input is an exactly represented integer.",
        },
        "cases": observations,
        "limitation": (
            "Only these three cases and this runtime were measured. "
            "No timing, performance ranking, universal accuracy claim, or literature verification is provided."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(measure(), indent=2, sort_keys=True, allow_nan=False))
