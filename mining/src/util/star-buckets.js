// Generates [lo, hi] star buckets to escape the GitHub Search API 1000-result cap.
// Strategy: tighter buckets where repo density is highest (lower star counts).
// Buckets are inclusive on both ends and use GitHub's `stars:LO..HI` query syntax.
// The top bucket is open-ended (`stars:>=N`).

export function defaultStarBuckets(minStars = 1000) {
  const out = [];
  // Dense: 1000 -> 5000 in steps of 100.
  for (let s = Math.max(minStars, 1000); s < 5000; s += 100) {
    out.push([s, s + 99]);
  }
  // Medium: 5000 -> 10000 in steps of 500.
  for (let s = 5000; s < 10000; s += 500) {
    out.push([s, s + 499]);
  }
  // Sparse: 10000 -> 50000 in steps of 5000.
  for (let s = 10000; s < 50000; s += 5000) {
    out.push([s, s + 4999]);
  }
  // Very sparse: 50000 -> 200000 in steps of 25000.
  for (let s = 50000; s < 200000; s += 25000) {
    out.push([s, s + 24999]);
  }
  // Open top.
  out.push([200000, null]);
  return out;
}

export function bucketToQuery([lo, hi]) {
  if (hi === null) return `stars:>=${lo}`;
  return `stars:${lo}..${hi}`;
}

// Halves a bucket when its first-page total_count exceeds 1000.
// Open-ended buckets cannot be halved by this helper; widen the threshold instead.
export function halveBucket([lo, hi]) {
  if (hi === null || hi <= lo) return null;
  const mid = Math.floor((lo + hi) / 2);
  return [
    [lo, mid],
    [mid + 1, hi],
  ];
}
