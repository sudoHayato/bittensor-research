# SN12 — Compute Horde — Deep Dive v3

## Resumo

Compute Horde e um subnet de GPU compute descentralizado que transforma GPUs nao confiaveis de miners em recursos de computacao confiaveis. Miners fornecem GPUs (principalmente A6000), validators enviam jobs organicos e sinteticos, e os scores sao baseados em "executor seconds" de jobs pagos com um sistema de allowance por bloco. A arquitetura e complexa: Django + Celery + PostgreSQL no validator, com um servico externo "Pylon" para setting de weights. O top1 miner recebe 97.5% das emissoes — uma concentracao extrema que se explica pela estrutura do scoring baseado em volume de jobs organicos processados.

## Codigo (validator/reward)

### Fluxo de Scoring

1. **`set_scores()`** (scoring/tasks.py): Celery task principal. Obtem bloco atual, verifica janela de commit-reveal (intervalo 722 blocos), calcula scores via `_score_cycles()`.

2. **`_score_cycles()`**: Determina ciclo atual e anterior (722 blocos cada), chama `DefaultScoringEngine.calculate_scores_for_cycles()`.

3. **`DefaultScoringEngine`** (scoring/engine.py):
   - Chama `calculate_allowance_paid_job_scores()` para obter scores por executor class
   - Aplica pesos por executor class (`DYNAMIC_EXECUTOR_CLASS_WEIGHTS`): **spin_up-4min.gpu-24gb=98, always_on.llm.a6000=1, always_on.test=0, always_on.cpu.8c.16gb=1** — a classe GPU de 24GB domina com 98% do peso
   - Normaliza scores por executor class (divide pelo total, multiplica pelo peso)
   - Aplica "dancing" — agrupamento por coldkey e distribuicao para main hotkey (80% share)

4. **`calculate_allowance_paid_job_scores()`** (scoring/calculations.py):
   - Score = **executor_seconds_cost** de jobs organicos terminados no ciclo
   - Usa sistema de allowance por bloco para validar que jobs foram "pagos"
   - Usa `InMemorySpendingBookkeeper` para detectar double-spend entre blocos
   - Score e proporcional ao volume de compute entregue

5. **`normalize_batch_scores()`**: Converte hotkey->score para uid->weight, aplica `process_weights()` do bittensor.

6. **`apply_dancing_burners()`**: **MECANISMO CRITICO** — aplica "burn incentive" a enderecos especificos:
   - `DYNAMIC_BURN_TARGET_SS58ADDRESSES`: lista de hotkeys que recebem uma fracao de TODAS as emissoes
   - `DYNAMIC_BURN_RATE`: fracao (0-1) de incentivos redirecionados
   - `DYNAMIC_BURN_PARTITION`: como dividir entre multiplos burners
   - Defaults: ambos 0.0, mas podem ser alterados via constance (database config)

7. **Pylon Service**: Weights sao enviados via servico externo `PylonClient` que faz `put_weights()` — um intermediario entre o validator e o subtensor.

### Mecanismo de Allowance

O sistema de allowance e sofisticado:
- Cada bloco gera "allowance" proporcional a stake do validator e executors do miner
- Jobs organicos consomem allowance
- Score = executor_seconds de jobs pagos validamente
- Prevents double-spending e spending de blocos invalidos/expirados

## Red Flags Adversariais

### FLAG CRITICA: Burn Mechanism com Constance Database Config
- **`apply_dancing_burners()`** pode redirecionar ate 100% das emissoes para enderecos especificos
- Os valores `DYNAMIC_BURN_RATE` e `DYNAMIC_BURN_TARGET_SS58ADDRESSES` sao controlados via **constance** (database backend)
- Qualquer pessoa com acesso ao Django admin pode alterar estes valores em runtime
- Default e 0.0, mas se alterado remotamente poderia redirecionar emissoes
- **Risco**: O subnet owner pode remotamente redirecionar emissoes sem alterar codigo

### FLAG: Pylon External Service
- Weights sao enviados via `PylonClient` — um servico externo proprietario
- O validator nao faz `set_weights()` diretamente no subtensor
- Isto adiciona um ponto de controle/falha centralizado
- `PYLON_ADDRESS`, `PYLON_IDENTITY_NAME`, `PYLON_IDENTITY_TOKEN` sao configs do environment

### FLAG: Constance Remote Config
- Praticamente TODOS os parametros de scoring sao dinamicos via constance:
  - `DYNAMIC_EXECUTOR_CLASS_WEIGHTS` — pode mudar quais GPUs contam
  - `DYNAMIC_BURN_RATE` — pode redirecionar emissoes
  - `DYNAMIC_DANCING_BONUS` — bonus para quem muda hotkeys
  - `MAIN_HOTKEY_SHARE` — distribuicao intra-coldkey
  - `SERVING` — pode desligar o validator completamente
- Isto significa que o comportamento do validator pode mudar sem update de codigo

### FLAG: Executor Class Weights Hardcoded Default
- `spin_up-4min.gpu-24gb=98` — 98% do peso total vai para uma unica classe de executor
- Isto concentra rewards em quem opera esta classe especifica

### NAO ENCONTRADO (positivo):
- Sem softmax com temperatura alta
- Sem trust_remote_code=True
- Sem hardcoded UIDs no scoring
- Sem auto-updater que executa codigo remoto
- Sem subprocess/eval/exec no codigo de producao (apenas testes)
- Sem kill switch explicito (SERVING flag existe mas e local)

## Porque Top1 = 97.5%?

A concentracao extrema (97.5% para um unico miner) explica-se por multiplos fatores:

1. **Score = Volume de Jobs Organicos**: O scoring e baseado em `executor_seconds_cost` de jobs organicos. Quem processa mais jobs organicos, ganha mais. Se apenas um miner tem capacidade/confiabilidade para processar o volume de jobs, ele domina.

2. **Apenas 6 miners scoring**: Com tao poucos miners, e facil para um com mais GPUs ou melhor uptime dominar.

3. **Allowance System**: O sistema de allowance por bloco cria barreiras de entrada. Novos miners precisam estar registrados e ter allowance calculada para comecar a receber jobs.

4. **Executor Class Concentration**: Com 98% do peso em `spin_up-4min.gpu-24gb`, quem tem mais GPUs desta classe domina.

5. **Burn Mechanism Potential**: Se `DYNAMIC_BURN_RATE > 0` estiver ativo na database constance (nao verificavel pelo codigo), pode estar redirecionando emissoes.

6. **Organic Job Routing**: O sistema de routing (`routing/default.py`) pode favorecer miners mais confiaveis, criando um ciclo: quem recebe mais jobs, ganha mais score, recebe mais jobs.

**Em resumo**: E um subnet onde "the rich get richer" — o scoring baseado em volume de jobs organicos naturalmente concentra rewards em quem ja tem mais capacidade.

## Hardware Requirements

- **Miner**: GPU A6000 (48GB VRAM) ou equivalente 24GB+ para classe `spin_up-4min.gpu-24gb`
- **Validator**: Maquina non-GPU standard + "Trusted Miner" com A6000 para cross-validation
- **Software**: Django, Celery, PostgreSQL, Redis, Docker
- **Custo estimado miner**: A6000 no Vast.ai ~$0.40-0.60/h = ~$300-450/mes
- **Nota**: RTX 4090 (24GB) pode funcionar para classe gpu-24gb mas A6000 e o standard

**hardware_heavy**: Moderado — requer GPU A6000 ou similar, nao RTX 4090

## ECONOMIA REAL

Dados fornecidos:
- emission_tao_day: 36.26 TAO
- TAO_USD: $320
- miners_scoring: 6

Calculos:
- Emissao diaria total: 36.26 * $320 = **$11,603/dia** = **$348,096/mes**
- Top 1 receita mensal: **$339,441** (97.5% share) = ~$11,315/dia
- Top 10 mediana: **$1,737/mes** (dado fornecido)
- Miner mediano: **$1,737/mes** = ~$58/dia

Break-even com custo Vast.ai ($180/mes RTX 4090):
- Miner mediano: $1,737/mes - $180 = $1,557 lucro = **VIABLE em 1 dia** (se conseguir entrar)
- MAS: precisa de A6000, nao RTX 4090. A6000 ~$300-450/mes no Vast.ai

Break-even com A6000 Vast.ai (~$400/mes):
- Miner mediano: $1,737 - $400 = $1,337 lucro = **VIABLE em ~7 dias**

Break-even Hetzner (EUR184/mes, sem GPU dedicada):
- Nao aplicavel — Hetzner nao oferece A6000s no modelo standard

POREM: A economia real e EXTREMAMENTE enganadora:
- Top1 leva 97.5% = $339,441/mes
- Os outros 5 miners dividem 2.5% = $8,655 total = ~$1,731/miner
- Mediana real dos "outros": ~$1,737/mes
- **Entrar como novo miner e quase impossivel** de competir com o top1

## VEREDICTO ECONOMICO: MARGINAL / IMPOSSIBLE para novos entrantes

**Justificacao**:
- O subnet funciona, tem produto real (GPU compute para outros subnets)
- O codigo e sofisticado e bem estruturado
- MAS a concentracao de 97.5% num unico miner e um sinal de alerta EXTREMO
- O mecanismo de burn via constance config e um risco de governanca
- O Pylon service como intermediario para weights e centralizacao
- Para um novo miner: precisaria de multiplas A6000s, conseguir routing de jobs organicos, e competir com o operador dominante que ja tem infraestrutura e routing favoravel
- **O "rich get richer" loop torna este subnet praticamente um monopolio**
- Viavel economicamente apenas se voce JA e o top miner ou tem relacao com os subnet owners para receber jobs organicos
- Para novos entrantes independentes: **IMPOSSIBLE** competir com o monopolista actual

### Riscos Adicionais:
1. Constance database configs podem ser alterados sem deploy
2. Burn mechanism pode redirecionar emissoes para enderecos do subnet owner
3. Pylon service e um single point of control para weight setting
4. Com apenas 6 miners scoring, barreiras de entrada sao altas
