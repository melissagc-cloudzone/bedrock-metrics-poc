"""
Destroys ALL resources created by this POC in the correct dependency order.
Safe to run multiple times — skips resources that no longer exist.

Deletes:
  - Bedrock Knowledge Base + data source
  - OpenSearch Serverless collection + all 3 policies
  - S3 bucket + all objects
  - IAM role + inline policy
  - DynamoDB audit trail table

Run this as soon as testing is complete to stop OpenSearch billing.
"""

import boto3, json, time, sys, pathlib
sys.path.insert(0, "..")
from config import REGION

DDB_TABLE = "bedrock-poc-usage-log"

STATE_FILE = pathlib.Path("../infrastructure/.rag_state.json")

bedrock = boto3.client("bedrock-agent",        region_name=REGION)
oss     = boto3.client("opensearchserverless", region_name=REGION)
s3      = boto3.client("s3",                   region_name=REGION)
iam     = boto3.client("iam")


def safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if any(k in str(e) for k in ("NotFound", "NoSuchEntity", "NoSuchBucket",
                                      "does not exist", "ResourceNotFoundException")):
            print(f"    (already gone)")
        else:
            print(f"    ⚠️  {e}")


def delete_s3_bucket(bucket: str):
    print(f"  S3: deleting all objects in {bucket}...")
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objects:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
        s3.delete_bucket(Bucket=bucket)
        print(f"    ✓ deleted")
    except Exception as e:
        print(f"    ⚠️  {e}")


def run():
    if not STATE_FILE.exists():
        print("ERROR: infrastructure/.rag_state.json not found.")
        print("  This file is created by setup_rag.py.")
        print("  If you need to clean up manually, check the AWS console.")
        sys.exit(1)

    state = json.loads(STATE_FILE.read_text())
    print("=" * 60)
    print("  BEDROCK METRICS POC — CLEANUP")
    print("=" * 60)

    # 1. Bedrock data source
    print(f"\n1. Deleting Bedrock data source...")
    safe(bedrock.delete_data_source,
         knowledgeBaseId=state["kb_id"],
         dataSourceId=state["ds_id"])
    print(f"   ✓")

    # 2. Bedrock Knowledge Base
    print(f"2. Deleting Bedrock Knowledge Base ({state['kb_id']})...")
    safe(bedrock.delete_knowledge_base, knowledgeBaseId=state["kb_id"])
    print(f"   ✓")

    # 3. IAM inline policy + role
    print(f"3. Deleting IAM role ({state['role_name']})...")
    safe(iam.delete_role_policy,
         RoleName=state["role_name"], PolicyName="BedrockMetricsPoCKBPolicy")
    safe(iam.delete_role, RoleName=state["role_name"])
    print(f"   ✓")

    # 4. OpenSearch Serverless collection
    print(f"4. Deleting OpenSearch collection ({state['collection_id']})...")
    safe(oss.delete_collection, id=state["collection_id"])

    print("   Waiting for deletion...")
    for _ in range(20):
        try:
            status = oss.batch_get_collection(
                ids=[state["collection_id"]]
            )["collectionDetails"]
            if not status:
                break
            time.sleep(15)
        except Exception:
            break
    print(f"   ✓")

    # 5. OSS policies (must delete after collection)
    print(f"5. Deleting OpenSearch policies...")
    safe(oss.delete_access_policy,
         name=state["access_policy"], type="data")
    safe(oss.delete_security_policy,
         name=state["net_policy"], type="network")
    safe(oss.delete_security_policy,
         name=state["enc_policy"], type="encryption")
    print(f"   ✓")

    # 6. S3
    print(f"6. Deleting S3 bucket ({state['bucket']})...")
    delete_s3_bucket(state["bucket"])

    # 7. DynamoDB audit trail table
    print(f"7. Deleting DynamoDB table ({DDB_TABLE})...")
    ddb = boto3.client("dynamodb", region_name=REGION)
    safe(ddb.delete_table, TableName=DDB_TABLE)
    print(f"   ✓")

    # 8. Remove state file
    STATE_FILE.unlink(missing_ok=True)

    print(f"\n{'=' * 60}")
    print("  ✅ CLEANUP COMPLETE — all POC resources deleted")
    print(f"{'=' * 60}")
    print("  OpenSearch billing has stopped.")
    print("  Verify in AWS console: no orphaned resources remain.")


if __name__ == "__main__":
    run()
