"""
Creates the minimum infrastructure needed for the RAG chatbot POC:
  1. S3 bucket with sample FinOps document
  2. OpenSearch Serverless collection (VECTOR type)
  3. Security + network + data access policies
  4. Vector index
  5. IAM role for Bedrock Knowledge Base
  6. Bedrock Knowledge Base + S3 data source + initial ingestion

⚠️  COST WARNING:
  OpenSearch Serverless starts billing the moment the collection is ACTIVE.
  Minimum charge is 2 OCUs = $0.48/hr even if you make zero queries.
  Run cleanup.py as soon as testing is done.

Prints the KB_ID at the end — paste it into:
  export BEDROCK_KB_ID=<id>
before running use_cases/rag_chatbot.py
"""

import boto3, json, time, uuid, subprocess, sys
sys.path.insert(0, "..")
from config import REGION, ACCOUNT_ID, boto_tags, bedrock_tags, EMBED_MODEL

UNIQUE_ID      = str(uuid.uuid4())[:8]
BUCKET_NAME    = f"bedrock-metrics-poc-{UNIQUE_ID}"
COLL_NAME      = f"bm-poc-vectors-{UNIQUE_ID}"
INDEX_NAME     = "bedrock-poc-index"
KB_NAME        = "bedrock-metrics-poc-kb"
KB_ROLE_NAME   = f"BedrockMetricsPoCKBRole-{UNIQUE_ID}"

s3      = boto3.client("s3",                   region_name=REGION)
oss     = boto3.client("opensearchserverless", region_name=REGION)
bedrock = boto3.client("bedrock-agent",        region_name=REGION)
iam     = boto3.client("iam")

SAMPLE_DOC = """
# Bedrock FinOps Reference

## Pricing Models
- On-Demand: pay per token, no commitment, best for variable workloads
- Batch Inference: 50% discount, async processing, best for bulk jobs
- Provisioned Throughput: hourly rate, guaranteed capacity, best above break-even

## Cost Drivers
1. Input token count (prompt + context window)
2. Output token count (generated response)
3. OpenSearch Serverless OCU-hours (RAG vector store)
4. S3 storage and requests (document store)

## Optimization Tips
- Use Claude Haiku over Sonnet when response quality allows
- Limit RAG chunk count to reduce context window size
- Delete OpenSearch collection when not in use
- Use Batch Inference for offline summarization jobs

## Decommission Checklist
All resources tagged AutoDelete=yes must be destroyed:
- Bedrock Knowledge Base and data source
- OpenSearch Serverless collection and all policies
- S3 bucket and objects
- IAM role and inline policies
Run cleanup.py to automate this.
"""

# ── Step 1: S3 ─────────────────────────────────────────────
print("Step 1: Creating S3 bucket...")
s3.create_bucket(Bucket=BUCKET_NAME)
s3.put_bucket_tagging(Bucket=BUCKET_NAME,
                      Tagging={"TagSet": boto_tags({"Phase": "rag"})})
s3.put_object(Bucket=BUCKET_NAME, Key="docs/finops-reference.txt",
              Body=SAMPLE_DOC.encode())
print(f"  ✓ {BUCKET_NAME}")

# ── Step 2: OpenSearch Serverless ──────────────────────────
print("\nStep 2: Creating OpenSearch Serverless collection...")
print("  ⚠️  Billing starts when collection becomes ACTIVE (~5 min)")

oss.create_security_policy(
    name=f"enc-{UNIQUE_ID}", type="encryption",
    policy=json.dumps({
        "Rules": [{"Resource": [f"collection/{COLL_NAME}"], "ResourceType": "collection"}],
        "AWSOwnedKey": True
    })
)
oss.create_security_policy(
    name=f"net-{UNIQUE_ID}", type="network",
    policy=json.dumps([{
        "Rules": [{"Resource": [f"collection/{COLL_NAME}"], "ResourceType": "collection"}],
        "AllowFromPublic": True
    }])
)

coll_resp   = oss.create_collection(name=COLL_NAME, type="VECTORSEARCH",
                                     tags=bedrock_tags({"Phase": "rag"}))
coll_id     = coll_resp["createCollectionDetail"]["id"]
coll_arn    = coll_resp["createCollectionDetail"]["arn"]

print("  Waiting for collection to become ACTIVE (~5 min)...")
while True:
    status = oss.batch_get_collection(ids=[coll_id])["collectionDetails"][0]["status"]
    print(f"  Status: {status}")
    if status == "ACTIVE":
        break
    time.sleep(30)

coll_endpoint = oss.batch_get_collection(ids=[coll_id])["collectionDetails"][0]["collectionEndpoint"]
print(f"  ✓ {COLL_NAME}")

# ── Step 3: IAM Role ───────────────────────────────────────
print("\nStep 3: Creating IAM role...")
try:
    role = iam.create_role(
        RoleName=KB_ROLE_NAME,
        AssumeRolePolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Principal": {"Service": "bedrock.amazonaws.com"},
                           "Action": "sts:AssumeRole"}]
        }),
        Tags=boto_tags({"Phase": "rag"})
    )
    role_arn = role["Role"]["Arn"]
    iam.put_role_policy(
        RoleName=KB_ROLE_NAME, PolicyName="BedrockMetricsPoCKBPolicy",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"],
                 "Resource": [f"arn:aws:s3:::{BUCKET_NAME}", f"arn:aws:s3:::{BUCKET_NAME}/*"]},
                {"Effect": "Allow", "Action": ["aoss:APIAccessAll"], "Resource": coll_arn},
                {"Effect": "Allow", "Action": ["bedrock:InvokeModel"], "Resource": "*"},
            ]
        })
    )
    print(f"  ✓ {KB_ROLE_NAME}")
except Exception as e:
    print(f"\n  ✗ IAM CreateRole denied (PowerUserAccess restriction): {e}")
    print("  Cleaning up OpenSearch and S3 to stop billing...")
    import subprocess as _sp
    _sp.run(["python", "infrastructure/cleanup_partial.py",
             coll_id, BUCKET_NAME, UNIQUE_ID], check=False)
    print("  RAG use case skipped. Chatbot + DynamoDB metrics are already captured.")
    raise SystemExit(0)

# ── Step 3b: OSS data access policy ───────────────────────
print("\nStep 3b: Creating OpenSearch data access policy...")
oss.create_access_policy(
    name=f"access-{UNIQUE_ID}", type="data",
    policy=json.dumps([{
        "Rules": [{"Resource": [f"index/{COLL_NAME}/*"],
                   "Permission": ["aoss:CreateIndex", "aoss:DeleteIndex",
                                  "aoss:UpdateIndex", "aoss:DescribeIndex",
                                  "aoss:ReadDocument", "aoss:WriteDocument"],
                   "ResourceType": "index"}],
        "Principal": [role_arn, f"arn:aws:iam::{ACCOUNT_ID}:root"],
    }])
)
time.sleep(15)   # wait for IAM + policy propagation
print("  ✓ access policy created")

# ── Step 3c: Vector index ─────────────────────────────────
print("\nStep 3c: Creating vector index...")
subprocess.run(
    [sys.executable, "-m", "pip", "install", "opensearch-py",
     "requests-aws4auth", "--quiet", "--break-system-packages"],
    check=True
)
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

creds  = boto3.Session().get_credentials()
auth   = AWS4Auth(creds.access_key, creds.secret_key, REGION, "aoss",
                  session_token=creds.token)
host   = coll_endpoint.replace("https://", "")
oss_cl = OpenSearch(hosts=[{"host": host, "port": 443}],
                    http_auth=auth, use_ssl=True, verify_certs=True,
                    connection_class=RequestsHttpConnection)

oss_cl.indices.create(INDEX_NAME, body={
    "settings": {"index.knn": True},
    "mappings": {"properties": {
        "embedding": {"type": "knn_vector", "dimension": 1024},
        "text":      {"type": "text"},
        "metadata":  {"type": "text"},
    }}
})
print(f"  ✓ index {INDEX_NAME}")

# ── Step 4: Knowledge Base ────────────────────────────────
print("\nStep 4: Creating Bedrock Knowledge Base...")
kb = bedrock.create_knowledge_base(
    name=KB_NAME,
    description="Bedrock Metrics POC — RAG use case",
    roleArn=role_arn,
    knowledgeBaseConfiguration={
        "type": "VECTOR",
        "vectorKnowledgeBaseConfiguration": {
            "embeddingModelArn": f"arn:aws:bedrock:{REGION}::foundation-model/{EMBED_MODEL}"
        }
    },
    storageConfiguration={
        "type": "OPENSEARCH_SERVERLESS",
        "opensearchServerlessConfiguration": {
            "collectionArn": coll_arn,
            "vectorIndexName": INDEX_NAME,
            "fieldMapping": {"vectorField": "embedding",
                              "textField": "text", "metadataField": "metadata"}
        }
    },
    tags={k: v for k, v in {**{"Phase": "rag"}, **{"Project": "bedrock-metrics-poc",
                                                     "Owner": "melissa",
                                                     "Environment": "playground",
                                                     "AutoDelete": "yes"}}.items()}
)
kb_id = kb["knowledgeBase"]["knowledgeBaseId"]
print(f"  ✓ KB created: {kb_id}")

# ── Step 5: Data source + ingestion ──────────────────────
print("\nStep 5: Connecting S3 and starting ingestion...")
ds = bedrock.create_data_source(
    knowledgeBaseId=kb_id, name="poc-s3-docs",
    dataSourceConfiguration={
        "type": "S3",
        "s3Configuration": {"bucketArn": f"arn:aws:s3:::{BUCKET_NAME}"}
    }
)
ds_id = ds["dataSource"]["dataSourceId"]

job   = bedrock.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
job_id = job["ingestionJob"]["ingestionJobId"]

while True:
    status = bedrock.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id,
                                       ingestionJobId=job_id)["ingestionJob"]["status"]
    print(f"  Ingestion: {status}")
    if status in ("COMPLETE", "FAILED"):
        break
    time.sleep(10)

print(f"  ✓ Ingestion {status}")

# ── Save IDs for cleanup ───────────────────────────────────
import pathlib
state = {
    "unique_id":    UNIQUE_ID,
    "bucket":       BUCKET_NAME,
    "collection_id": coll_id,
    "collection_arn": coll_arn,
    "kb_id":        kb_id,
    "ds_id":        ds_id,
    "role_name":    KB_ROLE_NAME,
    "enc_policy":   f"enc-{UNIQUE_ID}",
    "net_policy":   f"net-{UNIQUE_ID}",
    "access_policy": f"access-{UNIQUE_ID}",
}
pathlib.Path("../infrastructure/.rag_state.json").write_text(
    json.dumps(state, indent=2)
)

print(f"\n{'=' * 60}")
print("  ✅ RAG SETUP COMPLETE")
print(f"{'=' * 60}")
print(f"  KB ID: {kb_id}")
print(f"\n  Run before rag_chatbot.py:")
print(f"  export BEDROCK_KB_ID={kb_id}")
print(f"\n  ⚠️  OpenSearch is now billing (~$0.48/hr minimum)")
print(f"  Run cleanup.py as soon as testing is done.")
print(f"  State saved to infrastructure/.rag_state.json")
