=== SUBNET 114 — SOMA ===
Tipo: MCP Server Competition (Context Compression)
Status: active (registered 2026-01-13, ~3 months live)
Registration cost: 0.05 TAO
Hardware minimo realista: 4 CPU / 16 GB RAM / 200 GB SSD (validator); miner needs only upload a Python script to platform
Custo Hetzner equivalente: ~25 EUR/mes (CX31 for validator; miner has zero hardware cost — code runs on SOMA's sandboxed platform)
Tarefa: Miners write Python compression algorithms that shrink text while preserving Q&A answerability.
  Algorithms are uploaded to a centralized platform (platform.thesoma.ai), executed in sandboxed Docker, and scored by validators via OpenRouter LLM.
Competitividade: top1=19.90 TAO/dia, top10_avg=3.50 TAO/dia, mediana=0.00 TAO/dia, Gini=0.987, 44/256 UIDs on-chain with emission > 0 (36 miners + 9 validators, but only 2 UIDs receive meaningful incentive: UID 0=79.9%, UID 114=20.0%; remaining 34 miners receive ~0.0015% each as screener weight)
Distribuicao on-chain vs off-chain: match — no external leaderboard found; scoring is opaque via centralized platform DB
Receita por miner mediano: 0.000 TAO/dia (0 EUR/mes at TAO=$300)
Break-even: INFINITE — median miners earn nothing
Immunity period: 5000 blocks (~16.7 hours)
Risco deregistration: HIGH — 212/256 UIDs have zero emission; immunity is only 5000 blocks; anyone not winning the weekly competition earns nothing and risks deregistration
Discord/Docs quality: MED — Discord: https://discord.com/invite/durr4Sg6sM — docs cover setup but no technical depth on scoring algorithm or weight distribution formula
Burn capture detectado: YES ~80% — incentive_burn=0.7992; UID 0 (owner hotkey 5H1nRfbCbDGh3t17) receives 79.9% of all subnet incentive. The platform code in get_best_miners() routes ALL unclaimed weight to UID 0 as "burn". The TopMiner DB table controls who gets weight — this is entirely platform-controlled with no on-chain verifiability.
Centralizacao (backends, multisig, sudo): CRITICAL — the platform (platform.thesoma.ai) is the single point of control: it decides which miners qualify, computes scores, determines weight allocation, and tells validators what weights to set. Validators are essentially relay nodes — they fetch scoring tasks from the platform, run LLM evaluation, report back, then ask the platform "who are the best miners?" and blindly set those weights on-chain. The platform's DB (TopMiner table, BurnRequest table) has absolute control over emission distribution.
Off-chain scoring: opaque — scoring happens via OpenRouter LLM calls on compressed text Q&A, but the platform controls task assignment, miner selection (screener ranking), and final weight calculation. No external leaderboard confirmed; no wandb or huggingface tracking.
Red flags numerados:
  1. EXTREME CENTRALIZATION: Validators do NOT independently compute weights. They call platform_url/validator/get_best_miners and blindly set whatever the platform returns. The platform DB (TopMiner table) has absolute authority over weight distribution. This is a centralized service with blockchain characteristics, not a decentralized subnet.
  2. 80% BURN CAPTURE BY OWNER: UID 0 (owner hotkey) receives 79.9% of all incentive. The platform routes all "unclaimed" weight to UID 0. With screener_weight_per_miner=0.00002 and only ~34 screener miners, the remaining ~99.93% of weight goes to TopMiner entries and UID 0 burn. This is effectively a self-enrichment mechanism.
  3. OPAQUE WEIGHT CALCULATION: The get_best_miners() endpoint queries a TopMiner DB table (with ss58, weight, starts_at, ends_at fields) that is not populated by any auditable on-chain logic. Platform operators can insert arbitrary hotkeys with arbitrary weights into this table at any time. There is zero transparency about how TopMiner entries are determined.
  4. AUTO-UPDATER WITH git reset --hard: run_validator.sh (line 213) performs `git reset --hard origin/main` — any code pushed to the repo is automatically deployed to all validators without consent. Combined with the SOMA-shared dependency (also force-reinstalled), this gives the team arbitrary code execution on all validator machines.
  5. MINER CODE EXECUTION ON PLATFORM: Miners upload Python code that runs in sandboxed Docker containers on the platform's infrastructure. While the sandbox has good isolation (network=none, read_only, cap_drop=ALL, 2GB mem limit), the platform fully controls execution — miners have no way to verify their code runs fairly or that results aren't manipulated.
  6. WINNER-TAKES-ALL ECONOMICS: Only 1-2 miners receive meaningful emission per weekly cycle. UID 0 gets ~80%, one competition winner (currently UID 114) gets ~20%. The ~34 "screener" miners split ~0.07% total. 220+ registered miners get exactly 0.
  7. NO COMMIT-REVEAL: commit_reveal_weights_enabled=false — validators set weights in plain text, making the system vulnerable to weight copying (though irrelevant since validators don't compute weights independently anyway).
Sample snippets criticos:
  1. Platform controls all weights (validator/validator.py:268-294):
     ```python
     best_miners_response = await self.get_best_miners()
     if not best_miners_response or not best_miners_response.miners:
         await self.weight_setter.set_weights(
             np.array([0], dtype=np.int64), np.array([1.0], dtype=np.float32))
         return
     uids = np.array([m.uid for m in best_miners_response.miners], dtype=np.int64)
     weights = np.array([m.weight for m in best_miners_response.miners], dtype=np.float32)
     await self.weight_setter.set_weights(uids, weights)
     ```
  2. All unclaimed weight goes to UID 0 (platform validator.py:1850-1852):
     ```python
     burn = max(0.0, 1.0 - screener_used - top_miners_assigned)
     if burn > 0.0:
         miners_by_uid[0] = miners_by_uid.get(0, 0.0) + burn
     ```
  3. Auto-updater with hard reset (run_validator.sh:213):
     ```bash
     if git reset --hard "$UPSTREAM_BRANCH"; then
         log "Repository synchronized to $(git rev-parse --short HEAD)."
     ```
Veredicto: SKIP — Subnet is a centralized platform disguised as a decentralized competition. ~80% of emission goes to the owner UID. Validators are pure relays with no independent weight computation. The TopMiner DB table gives platform operators unchecked control over emission distribution. Median miner earns zero. Auto-updater gives team arbitrary code execution on validator machines. Not viable for independent mining or validation.

---
Review date: 2026-04-11
Repo: https://github.com/DendriteHQ/SOMA (commit bd6948d)
Discord: https://discord.com/invite/durr4Sg6sM
Website: https://thesoma.ai
Taostats: https://taostats.io/subnets/114/chart
