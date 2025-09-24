# Rekog Labeler

A Python project that uses **Amazon Rekognition** and **Amazon S3** to automatically detect labels in images.
This tool uploads local images to S3, calls Rekognition’s `DetectLabels` API, and generates reports in **JSON**, **CSV**, and **HTML** formats.

---

## Features
- Uploads images from your PC to an S3 bucket.
- Calls Amazon Rekognition to detect objects, scenes, and concepts.
- Outputs results in:
  - `out/labels.json`
  - `out/labels.csv`
  - `out/report.html`
- Supports `.jpg`, `.jpeg`, `.png`, `.jfif`.

---

## Requirements
- Python 3.10+ 
- AWS CLI configured with a profile (`rekog-lab`) 
- AWS account with:
  - `AmazonS3FullAccess`
  - `AmazonRekognitionFullAccess`

Install Python dependencies:
```bash
pip install -r requirements.txt
