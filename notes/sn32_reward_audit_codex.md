# SN32 reward audit (`fc647ce`, PR #87 context)

## 1. Como `rewards_tensor` é construído antes do softmax

No código real, `rewards_tensor` vem directamente de `get_rewards(...)` em [detection/validator/forward.py](~/bittensor-research/repos/sn32/llm-detection/detection/validator/forward.py:194), e `get_rewards(...)` devolve `torch.FloatTensor(rewards)` em [detection/validator/reward.py](~/bittensor-research/repos/sn32/llm-detection/detection/validator/reward.py:150).

Esses `rewards` são scores por miner, não uma distribuição normalizada. Em [detection/validator/reward.py](~/bittensor-research/repos/sn32/llm-detection/detection/validator/reward.py:45), cada score é a média de:
- `fp_score = 1 - fp / len(y_pred)`
- `f1_score`
- `ap_score`

Depois esse score é multiplicado por `penalty` (`0` ou `1`) em [detection/validator/reward.py](~/bittensor-research/repos/sn32/llm-detection/detection/validator/reward.py:137). Também há `0` directo para miners sem stake suficiente, com comprimentos inválidos, ou em excepção em [reward.py:114-117](~/bittensor-research/repos/sn32/llm-detection/detection/validator/reward.py:114) e [reward.py:144-148](~/bittensor-research/repos/sn32/llm-detection/detection/validator/reward.py:144).

Range esperado pelo código:
- mínimo real: `0`
- máximo real: `1`
- antes do softmax: scores brutos bounded em `[0,1]`, não normalizados para somar 1

As 20 linhas anteriores ao `softmax` são:

```python
   189      check_ids = np.array(sorted(check_ids))
   190
   191      all_responses, check_responses, version_responses, final_labels = await get_all_responses(
   192          self, axons, queries, check_ids, self.config.neuron.timeout)
   193
   194      rewards, metrics = get_rewards(self,
   195                                     labels=final_labels,
   196                                     responses=all_responses,
   197                                     miner_uids=miner_uids.tolist(),
   198                                     check_responses=check_responses,
   199                                     version_responses=version_responses,
   200                                     check_ids=check_ids,
   201                                     out_of_domain_ids=out_of_domain_ids,
   202                                     update_out_of_domain=True)
   203      bt.logging.info("Miner uids: {}".format(miner_uids))
   204      bt.logging.info("Rewards: {}".format(rewards))
   205      bt.logging.info("Metrics: {}".format(metrics))
   206
   207      rewards_tensor = torch.tensor(rewards)
   208
   209      m = torch.nn.Softmax()
   210      rewards_tensor = m(rewards_tensor * 100)
```

## 2. Destino de `rewards_tensor` depois do softmax

Depois do `softmax`, o tensor:
1. é apenas logado;
2. é expandido com zeros para todos os `uids` não amostrados nesse passo;
3. é passado a `self.update_scores(rewards_tensor, uids_tensor)` em [forward.py:223](~/bittensor-research/repos/sn32/llm-detection/detection/validator/forward.py:223);
4. não vai directamente para `set_weights()`.

`update_scores()` em [detection/base/validator.py:353-382](~/bittensor-research/repos/sn32/llm-detection/detection/base/validator.py:353) faz `scatter` e depois EMA:
`self.scores = real_alpha * scattered_rewards + (1 - real_alpha) * self.scores`

Só mais tarde `set_weights()` em [detection/base/validator.py:242-299](~/bittensor-research/repos/sn32/llm-detection/detection/base/validator.py:242) transforma `self.scores` em pesos on-chain. Aí há nova normalização:
`raw_weights = torch.nn.functional.normalize(self.scores, p=1, dim=0)` em [validator.py:257](~/bittensor-research/repos/sn32/llm-detection/detection/base/validator.py:257),
seguida de `process_weights_for_netuid(...)` e finalmente `self.subtensor.set_weights(...)`.

As linhas seguintes ao `softmax`: o ficheiro termina 19 linhas depois; seguem todas.

```python
   211
   212      bt.logging.info("Normalized rewards: {}".format(rewards_tensor))
   213      uids_tensor = torch.tensor(miner_uids)
   214
   215      not_available_uids = []
   216      for uid in range(self.metagraph.n.item()):
   217          if uid not in uids_tensor:
   218              not_available_uids.append(uid)
   219      uids_tensor = torch.concatenate([uids_tensor, torch.tensor(not_available_uids)])
   220      rewards_tensor = torch.concatenate([rewards_tensor, torch.zeros(len(not_available_uids))])
   221      bt.logging.info('Found {} unavailable uids, set zero to them: {}'.format(len(not_available_uids), not_available_uids))
   222
   223      self.update_scores(rewards_tensor, uids_tensor)
   224      self.log_step(miner_uids, metrics, rewards)
   225
   226      request_end = time.time()
   227      if request_end - request_start < EPOCH_MIN_TIME:
   228          bt.logging.info(f"Finished too fast, sleeping for {EPOCH_MIN_TIME - (request_end - request_start)} seconds")
   229          time.sleep(EPOCH_MIN_TIME - (request_end - request_start))
```

Resposta directa:
- `rewards_tensor` não é passado directamente a `set_weights`
- não é agregado com outras métricas depois do softmax
- é agregado com histórico via EMA em `update_scores`
- há normalização posterior em `set_weights()`, mas sobre `self.scores`, não sobre os rewards brutos do passo

## 3. Efeito numérico real de `softmax(x*100)`

Assumo `156` miners, logo:
- top `1%` = `ceil(1.56) = 2` miners
- top `10%` = `ceil(15.6) = 16` miners
- mediana = peso de um miner mediano

### Cenário A: top miners muito próximos (`< 0.05`)
Escolha plausível dentro do range real `[0,1]`:
- top 16 scores: `0.95, 0.9475, 0.945, ... , 0.9125` (spread total `0.0375`)
- restantes 140 miners: `0.70`

Softmax usa `e^(100x)`. Factorizando por `e^95`:

- denominador `Z = Σ_{k=0..15} e^(-0.25k) + 140e^(-25)`
- `Σ_{k=0..15} e^(-0.25k) ≈ 4.438625`
- `140e^(-25) ≈ 1.94e-9`
- logo `Z ≈ 4.438625002`

Pesos:
- top1: `1 / Z ≈ 0.225326 = 22.53%`
- top2: `e^-0.25 / Z ≈ 0.175484 = 17.55%`
- top 1% (2 miners): `(1 + e^-0.25) / Z ≈ 0.400810 = 40.08%`
- top 10% (16 miners): `Σ_{k=0..15} e^(-0.25k) / Z ≈ 0.9999999996 = ~100%`
- mediana: `e^-25 / Z ≈ 3.13e-12 = 0.000000000313%`

Leitura: mesmo com diferenças abaixo de `0.05`, o `*100` concentra praticamente todo o peso nos melhores `16`; o miner mediano fica economicamente nulo.

### Cenário B: top miners moderadamente diferentes (`~0.1`)
Escolha plausível:
- top1 `0.95`
- top2 `0.85`
- top3-top16 `0.75`
- restantes 140 miners `0.65`

Factorizando por `e^95`:

- `Z = 1 + e^-10 + 14e^-20 + 140e^-30`
- `e^-10 ≈ 4.53999e-5`
- `14e^-20 ≈ 2.88648e-8`
- `140e^-30 ≈ 1.31008e-11`
- logo `Z ≈ 1.000045427`

Pesos:
- top1: `1 / Z ≈ 0.999954573 = 99.995457%`
- top2: `e^-10 / Z ≈ 0.000045398 = 0.004540%`
- top 1% (2 miners): `(1 + e^-10) / Z ≈ 0.999999971 = 99.999997%`
- top 10% (16 miners): `(1 + e^-10 + 14e^-20) / Z ≈ 0.999999999987 = ~100%`
- mediana: `e^-30 / Z ≈ 9.36e-14 = 0.00000000000936%`

Leitura: com diferença de `~0.1`, o top1 fica essencialmente winner-take-all no próprio passo.

### Cenário C: distribuição uniforme entre 156 miners
Todos os scores iguais, por exemplo `x_i = 0.5`.

Então:
- `softmax(100 * 0.5)` = `softmax(50, 50, ..., 50)`
- todos os exponenciais são iguais
- cada peso = `1/156 ≈ 0.006410256 = 0.6410%`

Pesos:
- top 1% (2 miners): `2/156 ≈ 1.2821%`
- top 10% (16 miners): `16/156 ≈ 10.2564%`
- mediana: `1/156 ≈ 0.6410%`

Leitura: só há distribuição “saudável” quando os scores são exactamente iguais; qualquer diferença é amplificada por `e^(100Δ)`.

## 4. Justificação no resto do código / histórico / blame

No código actual, não encontrei documentação inline a justificar `100`:
- `forward.py` não comenta o racional
- `reward.py` não comenta o racional
- resto de `detection/validator/*` também não traz explicação para esse coeficiente

Histórico relevante:
- `72a68963` (`2024-06-19`): `move softmax into forward.py`
- `4b055c8c` (`2024-08-21`): `set scale coeff to 100`
- merge correspondente: `d36fdea` = `Merge pull request #35 from It-s-AI/v3.1` com título `Set scale coeff to 100`

`git blame` do bloco actual em [forward.py](~/bittensor-research/repos/sn32/llm-detection/detection/validator/forward.py:207):
- linha `209` (`m = torch.nn.Softmax()`): `72a68963` de `2024-06-19`
- linha `210` (`rewards_tensor = m(rewards_tensor * 100)`): `4b055c8c` de `2024-08-21`

Diffs relevantes:
- antes, em `be6eb20` (`2024-05-29`), o projecto usava `softmax(scores * 4)` em `detection/base/validator.py`
- depois, em `72a68963`, o `softmax(*4)` foi movido para `forward.py`
- depois, em `4b055c8c`, o coeficiente foi alterado de `4` para `100`

O commit auditado `fc647ce` (`2026-03-17`, PR #87) não altera esta lógica. É só:
- `Merge pull request #87 from It-s-AI/sergak0-patch-3`
- `Update FAQ.md`

Também o `git log -p detection/validator/forward.py | head -200` mostra que as alterações recentes em 2025-2026 mexem em:
- `not_available_uids`
- `stake gating`
- tipagem / retries / timing

Não há alteração recente ao `*100` nesse trecho.

## Veredicto final

**O softmax temperature=100 cria captura económica winner-take-all? PARCIAL.**

No passo individual do validator, sim: com diferenças de score de apenas `0.1`, o top1 recebe `99.995%` do peso do batch, e mesmo com diferenças abaixo de `0.05` o peso colapsa quase todo para o topo amostrado. Não é winner-take-all “directo” on-chain no mesmo instante porque ainda passa por EMA em `update_scores()` e só depois por normalização em `set_weights()`, mas a transformação local do batch é claramente extremamente concentradora.

