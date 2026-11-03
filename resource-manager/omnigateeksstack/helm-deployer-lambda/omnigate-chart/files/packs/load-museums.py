"""Puts the museum directory CSV into the all-packs demo's S3-compatible bucket (SeaweedFS), then exits. Safe to re-run."""
import os, time, urllib.error, urllib.request

s3 = os.environ["S3_ENDPOINT"]
bucket = os.environ["S3_BUCKET"]


def put(path, data=b""):
    req = urllib.request.Request(s3 + path, data=data, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        if e.code == 409:  # the bucket is already there from an earlier run
            return e.code
        raise


for _ in range(90):
    try:
        urllib.request.urlopen(s3 + "/", timeout=3)
        break
    except urllib.error.HTTPError:
        break  # any HTTP answer means the server is up
    except Exception:
        time.sleep(2)
print("bucket %s:" % bucket, put("/" + bucket))
print("museums.csv:", put("/%s/museums.csv" % bucket, open("/load/si_museums.csv", "rb").read()))
