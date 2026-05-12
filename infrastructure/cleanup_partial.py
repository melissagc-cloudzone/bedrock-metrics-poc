"""
Emergency cleanup — deletes OpenSearch + S3 when setup_rag.py fails
mid-way (e.g. IAM denied after OpenSearch is already ACTIVE and billing).

Usage: python infrastructure/cleanup_partial.py <collection_id> <bucket_name> <unique_id>
Also safe to call directly from CloudShell if the script crashed:

  python infrastructure/cleanup_partial.py \\
    $(aws opensearchserverless list-collections \\
      --query "collectionSummaries[0].id" --output text) \\
    bedrock-metrics-poc-<uid> <uid>
"""

import boto3, sys, time

REGION = "us-east-1"
oss = boto3.client("opensearchserverless", region_name=REGION)
s3  = boto3.client("s3",                   region_name=REGION)


def run(coll_id: str, bucket: str, uid: str):
    print(f"  Emergency cleanup: coll={coll_id}  bucket={bucket}  uid={uid}")

    # Delete OpenSearch collection
    try:
        oss.delete_collection(id=coll_id)
        print(f"  Deleting collection {coll_id} (waiting)...")
        for _ in range(20):
            details = oss.batch_get_collection(ids=[coll_id]).get("collectionDetails", [])
            if not details:
                break
            time.sleep(15)
        print("  ✓ Collection deleted")
    except Exception as e:
        print(f"  Collection: {e}")

    # Delete OSS policies
    for name, kind in [(f"enc-{uid}", "encryption"), (f"net-{uid}", "network"),
                       (f"access-{uid}", "data")]:
        try:
            oss.delete_security_policy(name=name, type=kind) if kind != "data" \
                else oss.delete_access_policy(name=name, type=kind)
            print(f"  ✓ Policy {name} deleted")
        except Exception:
            pass

    # Empty and delete S3 bucket
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": objs})
        s3.delete_bucket(Bucket=bucket)
        print(f"  ✓ S3 bucket {bucket} deleted")
    except Exception as e:
        print(f"  S3: {e}")

    print("  OpenSearch billing stopped.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python cleanup_partial.py <collection_id> <bucket_name> <unique_id>")
        sys.exit(1)
    run(sys.argv[1], sys.argv[2], sys.argv[3])
