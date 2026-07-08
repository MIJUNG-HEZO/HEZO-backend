#!/bin/bash
set -e

REGION="ap-northeast-2"
CLUSTER="hezo-cluster"
SERVICE="hezo-backend-svc"
ALB_NAME="hezo-studio-alb"

# Auto Scaling 대상 등록
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id "service/$CLUSTER/$SERVICE" \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 1 \
  --max-capacity 10 \
  --region $REGION

# 스케일 아웃: ALBRequestCountPerTarget >= 200
ALB_ARN=$(aws elbv2 describe-load-balancers \
  --names $ALB_NAME \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text --region $REGION)

# 타겟 그룹은 이름 매칭이 아니라 서비스에 실제 연결된 것을 직접 조회한다
# (이 계정에 hezo-backend-tg / hezo-backend-tg-prod 2개가 이름 매칭돼
#  contains(TargetGroupName, `backend`) 방식은 실패한다 — Task 3-B에서 실제로 재현된 버그)
TG_ARN=$(aws ecs describe-services \
  --cluster "$CLUSTER" --services "$SERVICE" \
  --query 'services[0].loadBalancers[0].targetGroupArn' \
  --output text --region $REGION)

if [ -z "$TG_ARN" ] || [ "$TG_ARN" = "None" ]; then
  echo "ERROR: $SERVICE 서비스에 연결된 타겟 그룹을 찾지 못함" >&2
  exit 1
fi

ALB_SUFFIX=$(echo $ALB_ARN | sed 's|.*loadbalancer/||')
TG_SUFFIX=$(echo $TG_ARN | sed 's|.*targetgroup/||')

aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id "service/$CLUSTER/$SERVICE" \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name hezo-backend-scale-out \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 200,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ALBRequestCountPerTarget",
      "ResourceLabel": "'"$ALB_SUFFIX/targetgroup/$TG_SUFFIX"'"
    },
    "ScaleOutCooldown": 60,
    "ScaleInCooldown": 600
  }' \
  --region $REGION

echo "✅ ECS Auto Scaling 설정 완료 (min:1 max:5, 트리거: 태스크당 200 RPS)"
