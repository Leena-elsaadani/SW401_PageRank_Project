
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = PROJECT_DIR / "data/raw/soc-LiveJournal1.txt"
OUTPUT_FILE = PROJECT_DIR / "data/processed/livejournal_clean.txt"
SAMPLES_DIR = PROJECT_DIR / "data/samples"


def preprocess():
    edge_count = 0
    invalid_count = 0

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(INPUT_FILE, "r") as source, \
         open(OUTPUT_FILE, "w") as destination:

        for line in source:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split()

            if len(parts) != 2:
                invalid_count += 1
                continue

            try:
                source_node = int(parts[0])
                destination_node = int(parts[1])
            except ValueError:
                invalid_count += 1
                continue

            destination.write(f"{source_node} {destination_node}\n")
            edge_count += 1

    print("Preprocessing completed!")
    print(f"Valid edges: {edge_count:,}")
    print(f"Invalid records: {invalid_count:,}")
    print(f"Output size: {OUTPUT_FILE.stat().st_size:,} bytes")


def create_sample(target_mb, sample_name):
    target_bytes = target_mb * 1024 * 1024
    sample_path = SAMPLES_DIR / sample_name

    written_bytes = 0
    edge_count = 0

    with open(OUTPUT_FILE, "r") as source, \
         open(sample_path, "w") as destination:

        for line in source:
            line_bytes = len(line.encode("utf-8"))

            if written_bytes + line_bytes > target_bytes:
                break

            destination.write(line)
            written_bytes += line_bytes
            edge_count += 1

    print(f"\nCreated {sample_name}")
    print(f"Edges: {edge_count:,}")
    print(f"Size: {written_bytes:,} bytes")


if __name__ == "__main__":
    preprocess()

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    create_sample(100, "livejournal_100MB.txt")
    create_sample(500, "livejournal_500MB.txt")
