#!/bin/bash
set -e

REGION="ap-northeast-2"
NAMESPACE="HEZO/Performance"
SNS_EMAIL="${1:-your@email.com}"

# SNS 토픽 생성 (이미 존재하면 동일 ARN 반환 — 멱등)
TOPIC_ARN=$(aws sns create-topic --name hezo-slo-alerts --region $REGION \
  --query 'TopicArn' --output text)

echo "📬 SNS 토픽: $TOPIC_ARN"

aws sns subscribe --topic-arn $TOPIC_ARN --protocol email \
  --notification-endpoint $SNS_EMAIL --region $REGION

# P99 SLO 알람 (500ms 초과 3분(3 x 60s) 지속 시 알림 — Task 12 FIS stopCondition이 이 알람 ARN을 직접 참조)
aws cloudwatch put-metric-alarm \
  --alarm-name "hezo-p99-slo-breach" \
  --alarm-description "P99 응답시간 SLO 위반 (>500ms)" \
  --namespace "$NAMESPACE" \
  --metric-name "P99Latency" \
  --statistic Maximum \
  --period 60 \
  --evaluation-periods 3 \
  --threshold 500 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions "$TOPIC_ARN" \
  --region $REGION

echo "✅ 알람 생성: hezo-p99-slo-breach"
echo "📧 SNS 구독 확인 이메일을 $SNS_EMAIL 에서 승인하세요"
