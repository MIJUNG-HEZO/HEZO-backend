#!/bin/bash
set -e

REGION="ap-northeast-2"
CLUSTER="hezo-cluster"
SERVICE="hezo-backend-svc"

# ALB 타겟 그룹 헬스체크 설정
TG_ARN=$(aws elbv2 describe-target-groups \
  --query 'TargetGroups[?contains(TargetGroupName, `backend`)].TargetGroupArn' \
  --output text --region $REGION)

aws elbv2 modify-target-group \
  --target-group-arn $TG_ARN \
  --health-check-path /api/v1/health \
  --health-check-interval-seconds 15 \
  --health-check-timeout-seconds 5 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --region $REGION

echo "헬스체크 설정 완료: /api/v1/health, 3회 실패 시 태스크 교체 (cluster=$CLUSTER service=$SERVICE)"
