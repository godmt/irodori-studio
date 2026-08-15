export function getTrainingVramWarning({
  method,
  device,
  precision,
  totalVramGb,
  recommendedVramGb,
}) {
  if (!String(device).toLowerCase().startsWith("cuda")) return null;

  const total = Number(totalVramGb);
  const methodRecommendations = recommendedVramGb?.[method] || {};
  const recommended = Number(methodRecommendations[precision] ?? methodRecommendations.bf16);
  const nominalTotal = Math.round(total);
  if (!Number.isFinite(total) || !Number.isFinite(recommended) || nominalTotal >= recommended) {
    return null;
  }

  return {
    method,
    totalVramGb: total,
    recommendedVramGb: recommended,
  };
}
