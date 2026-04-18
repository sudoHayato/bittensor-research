=== SUBNET 83 — CliqueAI ===
Tipo: Computational optimization (NP-hard Maximum Clique problem solving)
Status: active (registered 2025-03-29, version 0.0.12, 16 commits, steady emission growth over 30d)
Registration cost: 0.007276 TAO (neuron), 261.36 TAO (subnet creation)
Hardware minimo realista: CPU-only (GPU optional for GNN model). 4 cores, 16GB RAM, 10GB SSD. The min_compute.yml claims GPU recommended (A100) but code default uses networkx CPU algorithm. torch + torch-geometric in requirements but only for optional GNN solver.
Custo Hetzner equivalente: ~8 EUR/mes (CX31-OK)
Tarefa: Miners solve Maximum Clique Problem on graphs (290-700 nodes). Validator fetches problems from centralized backend (lambda.toptensor.ai), sends to miners, scores by optimality + diversity, uses EMA for weights.
Competitividade: top1=46.42 TAO/dia, top10=5.74 TAO/dia, mediana=0.0088 TAO/dia, Gini=0.9623, 200/200 miners activos (note: on-chain says max 256, active_miners=247 but neuron API returned 200)
Distribuicao on-chain vs off-chain: W&B dashboard exists (https://wandb.ai/toptensor-ai/CliqueAI/table) but is not publicly readable (JS-only render). All scoring is done by validator code locally. No external leaderboard with individual miner rankings found. Scoring logic is transparent in code but centralized problem source is opaque.
Receita por miner mediano: 0.0088 TAO/dia (0.26 TAO/mes = ~79 EUR/mes at TAO=$300)
Break-even: 3.0 dias (based on median emission)
Immunity period: 5000 blocks (~16.7 hours)
Risco deregistration: MED — Immunity period is 5000 blocks (short). Gini of 0.9623 means extreme concentration. If miner can't solve cliques competitively, rewards drop fast. However, reg cost is trivially low (0.007 TAO).
Discord/Docs quality: MED — No dedicated Discord found (only general Bittensor). Docs are decent (mechanism.md explains scoring math clearly). GitHub has 16 commits, all via squash-merge PRs.
Burn capture detectado: YES ~93.5% — CRITICAL RED FLAG. In set_weights():
  weights[0] = (1.0 - LAMBDA_WEIGHTS) * sum(normalized)
  This assigns UID 0 a weight of 93.5% (1 - 0.065 = 0.935) of total normalized scores. UID 0 is the subnet owner's hotkey (registration default). All other miners share only 6.5% of weights. This is THE primary burn capture mechanism.
Centralizacao: HIGH — (1) UID 0 gets ~93.5% of weight, (2) problem source is a centralized backend at lambda.toptensor.ai under team control, (3) miner selection biased toward miners who stake on the owner's validator via stake_on_owner_validator bonus, (4) Gini 0.9623 confirms extreme centralization.
Off-chain scoring: opaque — Problems come from centralized HTTP backend (lambda.toptensor.ai). The scoring algorithm itself is transparent (in clique_scoring.py), but problem selection and problem uniqueness ("each problem appears at most once") depend entirely on the backend server which is not open-source.
Red flags:
  1. CRITICAL BURN CAPTURE: weights[0] = (1.0 - LAMBDA_WEIGHTS) * sum(normalized) gives UID 0 ~93.5% of all weight. This is a textbook owner self-enrichment pattern. The LAMBDA_WEIGHTS constant (0.065) means only 6.5% of emission goes to actual miners.
  2. STAKE-ON-OWNER BIAS: Miner selection probability is boosted by staking alpha on the owner's validator (stakes_on_owner_validator). This creates a pay-to-play dynamic where the team extracts staking fees while offering higher problem frequency.
  3. CENTRALIZED PROBLEM SOURCE: All graph problems come from http://lambda.toptensor.ai/graph/lambda — a single centralized server. The backend is not open source. If it goes down, the subnet stops. The team controls which problems exist and could theoretically craft problems that favor specific solvers.
  4. AUTO-UPDATER with git pull: The autoupdate mechanism (common/utils/autoupdate.py) runs "git pull" from origin/main. A compromised repo could push malicious code that auto-deploys to all miners/validators with autoupdate enabled (default=1).
  5. UNENCRYPTED HTTP: LAMBDA_URL = "http://lambda.toptensor.ai" uses plain HTTP, not HTTPS. Problem data and validator hotkeys are sent in cleartext, enabling MITM attacks.
Sample snippets:

1. Burn capture in set_weights (common/base/validator.py:250-272):
```python
LAMBDA_WEIGHTS = 0.065
normalized = (self.scores - min_val) / range_val
weights = LAMBDA_WEIGHTS * normalized
weights[0] = (1.0 - LAMBDA_WEIGHTS) * sum(normalized)
```

2. Stake-on-owner bias in miner selection (CliqueAI/selection/miner_selector.py:47-50):
```python
s_m = [
    self.snapshot.alpha_stakes[uid]
    + self.snapshot.stakes_on_owner_validator[uid]
    for uid in self.miner_uids
]
```

3. Unencrypted centralized backend (common/base/consts.py:1):
```python
LAMBDA_URL = "http://lambda.toptensor.ai"
```

Veredicto: SKIP — Extreme burn capture (93.5% to UID 0) makes this subnet economically unviable for independent miners. The centralized problem backend and stake-on-owner bias compound the issue.
