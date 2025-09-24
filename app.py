#!/usr/bin/env python3
import argparse, csv, json, os, sys, time
from typing import List, Dict
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Only process these file types
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

# Default location of your images folder (in WSL/Ubuntu path form)
DEFAULT_LOCAL_FOLDER = "/mnt/c/Users/ryana/OneDrive/Desktop/images"

def make_session(profile: str, region: str):
    """Create a boto3 Session tied to your CLI profile and region."""
    try:
        return boto3.Session(profile_name=profile, region_name=region)
    except (NoCredentialsError, ClientError) as e:
        print(f"[!] AWS credentials/profile error: {e}")
        sys.exit(1)

def ensure_bucket(s3_client, bucket: str, region: str):
    """Create bucket if it doesn’t exist (safe to re-run)."""
    try:
        if region == "us-east-1":
            s3_client.create_bucket(Bucket=bucket)
        else:
            s3_client.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        print(f"[+] Created bucket: {bucket}")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            print(f"[*] Bucket exists/owned: {bucket}")
        else:
            print(f"[!] Could not create bucket: {e}")
            sys.exit(1)

def upload_folder_to_s3(s3_client, folder: str, bucket: str, prefix: str = "images/"):
    """Upload all jpg/png from local folder to S3."""
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        print(f"[!] Not a folder: {folder}")
        sys.exit(1)

    uploaded = 0
    for root, _, files in os.walk(folder):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in IMAGE_EXTS:
                continue
            full = os.path.join(root, f)
            key = os.path.join(prefix, os.path.relpath(full, folder)).replace("\\", "/")
            s3_client.upload_file(full, bucket, key)
            uploaded += 1
            print(f"[+] Uploaded: s3://{bucket}/{key}")
    if uploaded == 0:
        print("[!] No images found to upload (jpg/png).")
        sys.exit(1)
    print(f"[✓] Uploaded {uploaded} images.")

def list_s3_images(s3_client, bucket: str, prefix: str = "images/") -> List[str]:
    """List images already stored in S3 under the given prefix."""
    keys = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            ext = os.path.splitext(key)[1].lower()
            if ext in IMAGE_EXTS:
                keys.append(key)
    if not keys:
        print("[!] No images in S3 with supported extensions.")
        sys.exit(1)
    print(f"[✓] Found {len(keys)} images in s3://{bucket}/{prefix}")
    return keys

def detect_labels_for_s3_object(rekog_client, bucket: str, key: str,
                                max_labels: int = 10, min_conf: float = 70.0) -> Dict:
    """Call Rekognition DetectLabels on one image in S3."""
    resp = rekog_client.detect_labels(
        Image={"S3Object": {"Bucket": bucket, "Name": key}},
        MaxLabels=max_labels,
        MinConfidence=min_conf
    )
    return {
        "image": f"s3://{bucket}/{key}",
        "labels": [
            {
                "name": lab["Name"],
                "confidence": round(float(lab["Confidence"]), 2),
                "parents": [p["Name"] for p in lab.get("Parents", [])]
            }
            for lab in resp.get("Labels", [])
        ]
    }

def bulk_detect_and_save(rekog_client, bucket: str, keys: List[str],
                         out_dir: str = "out",
                         max_labels: int = 10, min_conf: float = 70.0):
    """Loop all images, detect labels, save JSON + CSV."""
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "labels.json")
    csv_path = os.path.join(out_dir, "labels.csv")

    results = []
    with open(csv_path, "w", newline="", encoding="utf-8") as fcsv:
        writer = csv.writer(fcsv)
        writer.writerow(["image", "label", "confidence", "parents"])
        for i, key in enumerate(keys, 1):
            try:
                res = detect_labels_for_s3_object(rekog_client, bucket, key, max_labels, min_conf)
                results.append(res)
                for lab in res["labels"]:
                    writer.writerow([
                        res["image"], lab["name"], lab["confidence"], ";".join(lab["parents"])
                    ])
                print(f"[{i}/{len(keys)}] Labeled: {key}")
                time.sleep(0.1)
            except ClientError as e:
                print(f"[!] Rekognition failed for {key}: {e}")

    with open(json_path, "w", encoding="utf-8") as fjson:
        json.dump(results, fjson, indent=2)
    print(f"[✓] Saved JSON: {json_path}")
    print(f"[✓] Saved CSV : {csv_path}")
    return json_path, csv_path

def generate_html_report(json_path: str, out_html: str = "out/report.html"):
    """Generate a simple HTML report from the JSON results."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for item in data:
        img = item["image"]
        for lab in item["labels"]:
            rows.append(
                f"<tr><td>{img}</td><td>{lab['name']}</td><td>{lab['confidence']}</td><td>{', '.join(lab['parents'])}</td></tr>"
            )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Rekognition Labels Report</title>
<style>
body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; padding:20px }}
table {{ border-collapse: collapse; width: 100% }}
th, td {{ border: 1px solid #ddd; padding: 8px; }}
th {{ background: #f2f2f2; text-align:left }}
code {{ background:#f6f8fa; padding:2px 4px; border-radius:4px }}
</style></head>
<body>
<h1>Amazon Rekognition Labels Report</h1>
<p>Generated from <code>{os.path.basename(json_path)}</code></p>
<table>
  <thead><tr><th>Image</th><th>Label</th><th>Confidence</th><th>Parents</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
</body></html>"""
    os.makedirs(os.path.dirname(out_html), exist_ok=True)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[✓] Saved HTML: {out_html}")
    return out_html

def main():
    p = argparse.ArgumentParser(description="Image Labels Generator (S3 + Rekognition)")
    p.add_argument("--profile", default="rekog-lab")
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--bucket", required=True)
    p.add_argument("--local-folder", default=DEFAULT_LOCAL_FOLDER)
    p.add_argument("--prefix", default="images/")
    p.add_argument("--max-labels", type=int, default=10)
    p.add_argument("--min-confidence", type=float, default=70.0)
    a = p.parse_args()

    sess = make_session(a.profile, a.region)
    s3c = sess.client("s3")
    rekog = sess.client("rekognition")

    ensure_bucket(s3c, a.bucket, a.region)

    if a.local_folder:
        upload_folder_to_s3(s3c, a.local_folder, a.bucket, a.prefix)

    keys = list_s3_images(s3c, a.bucket, a.prefix)
    json_path, _ = bulk_detect_and_save(
        rekog, a.bucket, keys, out_dir="out",
        max_labels=a.max_labels, min_conf=a.min_confidence
    )
    generate_html_report(json_path, out_html="out/report.html")
    print("\n[Done] Check the 'out/' folder for CSV, JSON, and HTML report.")

if __name__ == "__main__":
    main()
