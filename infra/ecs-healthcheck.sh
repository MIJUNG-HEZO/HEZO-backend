#!/bin/bash
set -e

REGION="ap-northeast-2"
CLUSTER="hezo-cluster"
SERVICE="hezo-backend-svc"

# ALB 타겟 그룹 헬스체크 설정
# ECS 서비스에 실제로 연결된 타겟 그룹을 조회 (이름에 "backend"가 들어간 타겟 그룹이
# 여러 개 존재할 수 있어 describe-target-groups의 이름 매칭만으로는 여러 ARN이 반환될 수 있음)
TG_ARN=$(aws ecs describe-services \
  --cluster "$CLUSTER" --services "$SERVICE" \
  --query 'services[0].loadBalancers[0].targetGroupArn' \
  --output text --region $REGION)

if [ -z "$TG_ARN" ] || [ "$TG_ARN" = "None" ]; then
  echo "ERROR: $SERVICE 서비스에 연결된 타겟 그룹을 찾지 못함" >&2
  exit 1
fi

aws elbv2 modify-target-group \
  --target-group-arn $TG_ARN \
  --health-check-path /api/v1/health \
  --health-check-interval-seconds 15 \
  --health-check-timeout-seconds 5 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --region $REGION

echo "헬스체크 설정 완료: /api/v1/health, 3회 실패 시 태스크 교체 (cluster=$CLUSTER service=$SERVICE)"
