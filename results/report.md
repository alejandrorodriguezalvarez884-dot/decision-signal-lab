# Results

Generated 2026-10-04T11:01:15+00:00. Model(s): pplx-decider-v1-27b.
Sample (earnings releases with prices): {'design': 1529}.
Primary: `react_anon__nvr` → `fwd_abn_20`.

## design — exploratory (questions may have been tuned here)

Events: 1529

| signal | weeks | mean weekly IC | t (NW) | p | pooled IC [95% CI] | Q5−Q1 [95% CI] | p perm |
|---|---|---|---|---|---|---|---|
| `react_anon__nvr` | 80 | -0.053 | -1.60 | 0.113 | -0.041 [-0.098, 0.015] | -0.91% [-1.93%, 0.14%] | 0.137 |
| `react_anon__reversal_signal` | 80 | -0.055 | -1.39 | 0.169 | -0.031 [-0.084, 0.020] | -0.14% [-1.16%, 0.85%] | 0.116 |
| `react_anon__underappreciated_longterm` | 80 | -0.087 | -3.10 | 0.003 | -0.068 [-0.117, -0.015] | -0.72% [-1.70%, 0.26%] | 0.013 |
| `text_anon__mismatch` | 80 | -0.058 | -1.34 | 0.183 | -0.068 [-0.123, -0.010] | -1.10% [-2.29%, 0.11%] | 0.108 |
| `text_anon__naive_mismatch` | 80 | -0.027 | -0.65 | 0.519 | -0.023 [-0.087, 0.040] | -0.33% [-1.60%, 0.91%] | 0.452 |
| `text_anon__composite` | 80 | -0.048 | -1.08 | 0.285 | -0.056 [-0.112, -0.000] | -0.99% [-2.11%, 0.19%] | 0.178 |
| `base__continuation` | 80 | 0.061 | 2.35 | 0.021 | 0.035 [-0.010, 0.082] | 0.73% [-0.16%, 1.64%] | 0.087 |
| `base__reversal` | 80 | -0.061 | -2.35 | 0.021 | -0.035 [-0.082, 0.010] | -0.73% [-1.64%, 0.16%] | 0.087 |
| `base__lm_tone` | 80 | -0.014 | -0.32 | 0.752 | -0.029 [-0.077, 0.018] | -0.22% [-1.13%, 0.68%] | 0.742 |
| `base__lm_mismatch` | 80 | -0.015 | -0.34 | 0.734 | -0.030 [-0.080, 0.016] | -0.13% [-1.04%, 0.75%] | 0.714 |
| `base__momentum` | 80 | 0.018 | 0.37 | 0.715 | 0.049 [-0.022, 0.124] | 1.52% [0.11%, 2.92%] | 0.630 |

**Primary signal by horizon** (mean weekly IC, t):  h=1: -0.020 (-0.55), h=5: -0.063 (-1.40), h=20: -0.053 (-1.60), h=60: 0.053 (1.95)

**Incremental regression** (target winsorized, per-SD coefficient, week-clustered): coef 0.65%, t 1.97, p 0.049, n 1529, controls ['r0_z', 'momentum', 'log_dollar_vol', 'base__lm_tone', 'text_anon__composite']

**Secondary signals, Holm-adjusted p:** `react_anon__underappreciated_longterm` 0.013, `react_anon__reversal_signal` 0.676, `text_anon__mismatch` 0.676, `text_anon__composite` 0.676, `text_anon__naive_mismatch` 0.676

**Contamination checks** (mean weekly IC on the primary target):
- `react_raw__nvr`: -0.263 (t -2.51)
- `react_anon__nvr`: -0.053 (t -1.60)
- `text_raw__composite`: -0.277 (t -2.53)
- `text_anon__composite`: -0.048 (t -1.08)
- `probe__outperform_next_month`: 0.055 (t 2.31)
- `react_anon__nvr__on_raw_sample`: -0.254 (t -2.28)
- `text_anon__composite__on_raw_sample`: -0.212 (t -1.80)
- `probe__outperform_next_quarter_vs_fwd60`: -0.010 (t -0.26)

## Does the model use the reaction?

Same masked text, three made-up reactions (n=291). Mean P(better)−P(worse): cf_strong_neg 0.499, cf_flat 0.232, cf_strong_pos -0.158. Monotone in the expected direction: 100%. Essentially unchanged: 0%.
