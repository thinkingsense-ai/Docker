"""Puts the museum directory CSV into the demo's S3-compatible bucket (SeaweedFS), then exits. Safe to re-run."""
import time, urllib.error, urllib.request

s3 = "http://s3:9000"


def put(path, data=b""):
    req = urllib.request.Request(s3 + path, data=data, method="PUT")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


for _ in range(60):
    try:
        urllib.request.urlopen(s3 + "/", timeout=3)
        break
    except urllib.error.HTTPError:
        break  # any HTTP answer means the server is up
    except Exception:
        time.sleep(2)
print("bucket si-poc:", put("/si-poc"))
print("museums.csv:", put("/si-poc/museums.csv", open("/si-data/si_museums.csv", "rb").read()))
