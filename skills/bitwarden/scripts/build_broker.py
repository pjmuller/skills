"""Compile the broker with the reviewed PSL snapshot sealed into its code signature."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def build(output, flags):
    rules = [line.encode("idna").decode("ascii") for line in
             (ROOT / "public_suffix_list.dat").read_text().splitlines() if line and not line.startswith("//")]
    # A separate generated source keeps the readable security core short. No runtime data dependency.
    with tempfile.TemporaryDirectory(prefix="bw-build-") as directory:
        directory = Path(directory)
        main = directory / "main.swift"
        main.write_bytes((ROOT / "broker.swift").read_bytes())
        data = directory / "suffixes.swift"
        data.write_text('let publicSuffixRules = Set(' + json.dumps("\n".join(rules))
                        + '.split(separator: "\\n").map(String.init))\n')
        subprocess.run(["xcrun", "swiftc", str(main), str(data), "-o", output, *flags], check=True)


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2:])
