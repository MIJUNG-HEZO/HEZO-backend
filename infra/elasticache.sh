#!/bin/bash
set -e

REGION="ap-northeast-2"
CLUSTER_ID="hezo-redis"
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=exam-vpc" \
  --query 'Vpcs[0].VpcId' --output text --region $REGION)

# 보안 그룹 생성 (ECS → Redis 6379)
SG_ID=$(aws ec2 create-security-group \
  --group-name hezo-redis-sg \
  --description "HEZO Redis access" \
  --vpc-id $VPC_ID \
  --region $REGION \
  --query 'GroupId' --output text)

# ECS 태스크가 실제로 쓰는 보안 그룹에서 Redis 접근 허용
# (플랜 원문은 "hezo-backend-sg"를 가정했으나 실제 계정의 이름은 "hezo-app-sg"다 —
#  ECS 태스크의 실제 ENI에 붙은 보안 그룹을 직접 조회해 확인함)
ECS_SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=hezo-app-sg" \
  --query 'SecurityGroups[0].GroupId' --output text --region $REGION)

if [ -z "$ECS_SG_ID" ] || [ "$ECS_SG_ID" = "None" ]; then
  echo "ERROR: ECS 보안그룹(hezo-app-sg)을 찾지 못함" >&2
  exit 1
fi

aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp --port 6379 \
  --source-group $ECS_SG_ID \
  --region $REGION

# 서브넷 그룹 생성
# (플랜 원문은 "private-was*"를 가정했으나 실제 계정의 이름은 "exam-vpc-pri-was-sub*"다)
SUBNET_IDS=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:Name,Values=exam-vpc-pri-was-sub*" \
  --query 'Subnets[].SubnetId' --output text --region $REGION)

if [ -z "$SUBNET_IDS" ]; then
  echo "ERROR: private-was 서브넷을 찾지 못함" >&2
  exit 1
fi

aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name hezo-redis-subnet \
  --cache-subnet-group-description "HEZO Redis subnet" \
  --subnet-ids $SUBNET_IDS \
  --region $REGION 2>/dev/null || true

# ElastiCache 클러스터 생성
aws elasticache create-cache-cluster \
  --cache-cluster-id $CLUSTER_ID \
  --cache-node-type cache.t3.micro \
  --engine redis \
  --num-cache-nodes 1 \
  --cache-subnet-group-name hezo-redis-subnet \
  --security-group-ids $SG_ID \
  --region $REGION

echo "⏳ ElastiCache 생성 중 (약 5분)..."
aws elasticache wait cache-cluster-available \
  --cache-cluster-id $CLUSTER_ID --region $REGION

ENDPOINT=$(aws elasticache describe-cache-clusters \
  --cache-cluster-id $CLUSTER_ID \
  --show-cache-node-info \
  --query 'CacheClusters[0].CacheNodes[0].Endpoint.Address' \
  --output text --region $REGION)

REDIS_URL="redis://$ENDPOINT:6379/0"
aws ssm put-parameter --name "/hezo/studio/REDIS_URL" \
  --value "$REDIS_URL" --type SecureString --overwrite --region $REGION
aws ssm put-parameter --name "/hezo/studio/REDIS_ENABLED" \
  --value "true" --type String --overwrite --region $REGION

echo "✅ ElastiCache 엔드포인트: $ENDPOINT"
echo "✅ SSM /hezo/studio/REDIS_URL 저장 완료"
