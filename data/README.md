# Dataset Setup – SW401 PageRank Project

## 1. Dataset Information

This project uses the SNAP LiveJournal Social Network dataset.

**Official dataset page:**  
https://snap.stanford.edu/data/soc-LiveJournal1.html

**Download:**  
https://snap.stanford.edu/data/soc-LiveJournal1.txt.gz

### Original Dataset Statistics

| Property | Value |
|---|---:|
| Nodes | 4,847,571 |
| Edges | 68,993,773 |
| Graph type | Directed |

The original dataset is not included in this repository because of its large size. Each team member must download and prepare it locally.

## 2. Required Directory Structure

After completing the setup, the local data directory should look like this:

```text
data/
├── raw/
│   └── soc-LiveJournal1.txt
├── processed/
│   └── livejournal_clean.txt
└── samples/
    ├── livejournal_100MB.txt
    └── livejournal_500MB.txt
```

The dataset files are excluded from GitHub.

## 3. Download and Extract the Dataset

Run these commands from the project root:

```bash
mkdir -p data/raw
mkdir -p data/processed
mkdir -p data/samples

wget -P data/raw \
https://snap.stanford.edu/data/soc-LiveJournal1.txt.gz
```

Extract the downloaded archive:

```bash
gzip -dk data/raw/soc-LiveJournal1.txt.gz
```

The extracted file must be located at:

`data/raw/soc-LiveJournal1.txt`

## 4. Verify the Download

Check the beginning of the file:

```bash
head -10 data/raw/soc-LiveJournal1.txt
```

Verify its SHA-256 checksum:

```bash
sha256sum data/raw/soc-LiveJournal1.txt
```

Expected checksum:

```text
4bfdd9975179fbf180619b99989bc9f4a25e9371a6c8c853f1c5c611240c071b
```

## 5. Run the Preprocessing Script

From the project root, execute:

```bash
python3 preprocessing/preprocess.py
```

The script automatically performs the following operations:

1. Reads the original dataset.
2. Skips blank lines and comment lines.
3. Validates edge records.
4. Generates the cleaned dataset.
5. Creates the 100 MB sample.
6. Creates the 500 MB sample.

Generated files:

- `data/processed/livejournal_clean.txt`
- `data/samples/livejournal_100MB.txt`
- `data/samples/livejournal_500MB.txt`

No separate sample-generation command is necessary.

## 6. Expected Preprocessing Results

The original preprocessing run produced:

| Dataset | Edges | Size |
|---|---:|---:|
| Cleaned dataset | 68,993,773 | 1,011,604,076 bytes |
| 100 MB sample | 8,015,157 | 104,857,589 bytes |
| 500 MB sample | 37,672,977 | 524,287,992 bytes |

Invalid records: 0.

These values are reference results from the original run. Your results should be compared against them.

## 7. Important Notes for Team Members

- Do not upload the original dataset, cleaned dataset, or samples to GitHub.
- Use the same original dataset and preprocessing script.
- Run the preprocessing script from the project root.
- Do not manually modify the original dataset.
- Preserve the direction of graph edges.
- The samples are prefixes of the cleaned edge list, not randomly selected edges. This limitation should be considered when analyzing experimental results.

---

**Course:** SW401 – Parallel and Distributed Systems  
**Project:** PageRank on LiveJournal