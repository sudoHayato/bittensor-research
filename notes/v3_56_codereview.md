# SN56 -- Gradients (G.O.D) -- Deep Dive v3

## Resumo
SN56 e um subnet de fine-tuning competitivo baseado em torneios semanais. Miners submetem repositorios open-source de treino (AutoML scripts) que os validators executam na propria infraestrutura deles (H100s). Nao existe mining tradicional com GPU do miner -- o miner precisa apenas de uma maquina de desenvolvimento e um GitHub repo. O sistema de pesos e tournament-based com decay temporal, burn mechanism, e exponential decline mapping para distribuicao de rewards.

## Codigo (validator/reward)

### Scoring (validator/evaluation/scoring.py)
- **Winner-take-most**: Apenas o 1o lugar recebe `FIRST_PLACE_SCORE = 3`. Todos os outros recebem 0.
- **Bottom 25% penalty**: Quando ha mais de 8 miners validos (`MIN_IDEAL_NUM_MINERS_IN_POOL = 8`), os 25% piores recebem `SCORE_PENALTY = -1`.
- **Failed submissions**: Tambem recebem penalty de -1 quando existem submissoes validas.
- **GRPO/Environment tasks**: Higher score is better (ranking invertido).
- **Duplicate detection**: Repos duplicados sao detectados e agrupados por loss identico.

### Tournament Weight System (validator/core/weight_setting.py)
- Pesos divididos em 3 categorias de torneio: TEXT (base=0.15, max=0.48), IMAGE (base=0.10, max=0.32), ENVIRONMENT (base=0.10, max=0.20).
- `burn_weight = 1.0 - text - image - environment` -- peso nao distribuido vai para burn.
- **Exponential decline mapping**: Winners recebem peso exponencialmente maior (base=0.3 decay). 1o lugar ~77%, 2o ~23%, 3o ~7% etc (normalizado).
- **Innovation incentive**: Champions que vencem por margem >5% (`EMISSION_MULTIPLIER_THRESHOLD`) recebem emission boost ate o max weight do tipo.
- **Time-based decay**: 0.33%/dia (`EMISSION_DAILY_TIME_DECAY_RATE`) -- champion perde boost ao longo do tempo.
- **Participation weight**: 0.0001 por participante ativo (minimo para nao ser deregistrado).

### Tournament Structure (validator/tournament/)
- Torneios semanais: Text/Image quinta-feira 14h UTC, Environment segunda-feira 14h UTC.
- Structure: Group rounds (32 miners/grupo) -> Knockout -> Boss round (challenger vs champion).
- Progressive threshold: Champion precisa ser batido por margem progressivamente menor (10% inicial, decay 0.8x por vitoria consecutiva, minimo 3%).
- Participation fee: 0.2 TAO (text/environment), 0.15 TAO (image) -- fees sao burned.

## Red Flags Adversariais

### trust_remote_code=True -- RISCO MEDIO
- Presente em multiplos locais: `core/config/base.yml`, `core/config/base_grpo.yml`, `core/config/base_environment.yml`, `validator/evaluation/eval_environment.py`, `validator/tasks/task_prep.py` (para HF datasets), `validator/utils/multi_datasets.py`.
- Contexto: Usado no carregamento de datasets do HuggingFace e tokenizers. Para datasets de terceiros (`load_dataset(..., trust_remote_code=True)`) existe risco de execucao de codigo malicioso no dataset. Para task_prep.py ha uma protecao parcial: `trust_remote_code=False` para arquivos JSON locais, mas `True` para datasets do HF.
- Mitigacao parcial: Os datasets sao curados pelo content service da Gradients (`content.gradients.io`).

### Auto-updater sem verificacao de assinatura -- RISCO BAIXO-MEDIO
- `utils/run_validator_auto_update.py`: Faz `git reset --hard` para o commit remoto sem nenhuma verificacao criptografica (GPG signature, commit hash pinning, etc).
- Qualquer comprometimento do repositorio GitHub permitiria injecao de codigo no validator.
- O mesmo para `utils/run_auditor_autoupdate.py`.

### EMISSION_BURN_HOTKEY hardcoded -- NOTA (nao e red flag)
- `5GU4Xkd3dCGTU3s8VLcHGc5wsD5M8XyxDca5yDQhYm1mVXFu` -- este e o endereco de burn do Bittensor, usado como placeholder para o champion defensor. Uso legitimo e bem documentado no codigo.

### Nenhuma encontrada:
- Softmax temperature manipulation: Nao encontrada. Temperature usada apenas para geracao de texto sintetico (0.6) e imagens (0.8).
- Lambda manipulation antes de set_weights: Nao encontrada.
- Hardcoded UIDs favorecendo miners especificos: Nao encontrado.
- Normalizacao que favorece UIDs especificos: Nao encontrada. Weights somam a 1.0 com verificacao explicita.
- Kill switches (min_alpha_amount): Nao encontrados.

## Hardware Requirements

**Miners NAO precisam de GPU para torneios.** O modelo de SN56 e unico:
- Miners submetem repositorios GitHub com scripts de treino
- Validators executam esses scripts na propria infraestrutura (H100s, A100s)
- Miner precisa apenas: maquina de desenvolvimento, GitHub repo, servidor leve para o endpoint FastAPI

**Custo real do miner:**
- Servidor minimo para rodar o miner endpoint (FastAPI): ~$5-10/mes
- Taxa de participacao por torneio: 0.2 TAO (~$64 a $320/TAO)
- Desenvolvimento de scripts AutoML: tempo/expertise (sem custo de hardware)

**Infraestrutura do Validator (para referencia):**
- Text tasks: 1-8x H100 (conforme tamanho do modelo)
- Image tasks: 1x A100
- Container: 135GB RAM/GPU, 24 cores/GPU, rede isolada

## ECONOMIA REAL
- Top 1 receita mensal real: $373,937
- Top 10 receita mensal mediana real: ~$37,394 (estimativa: top10 share ~8.7% baseado em gini 0.667 e distribuicao exponencial)
- Miner mediano receita mensal real: $11,117
- Break-even Vast.ai ($180/mes): 0.5 dias (miner NAO precisa de GPU -- custo real e ~$10/mes + fees de torneio)
- Break-even Hetzner (EUR184/mes): N/A (nao precisa de servidor dedicado)

**Nota sobre break-even:** O modelo economico de SN56 e fundamentalmente diferente. O custo do miner nao e hardware, e sim:
1. Fee de participacao: ~0.2 TAO/torneio (~$64 a cada 5-7 dias = ~$274-384/mes em fees)
2. Tempo de desenvolvimento de scripts AutoML competitivos
3. Servidor minimo para endpoint: ~$5-10/mes

**Break-even real com custo total (~$350/mes em fees + servidor):**
- Com receita mediana ($11,117/mes): ~0.9 dias
- Com receita do percentil 25 (estimativa ~$2,000/mes): ~5.3 dias

## VEREDICTO ECONOMICO: VIABLE

SN56 tem um modelo economico unico e favoravel: miners nao precisam de GPU, apenas expertise em AutoML e um pequeno investimento em fees de torneio (~$350/mes). Mesmo o miner mediano tem receita de $11,117/mes, tornando o ROI excelente. O principal barrier-to-entry nao e capital, e sim competencia tecnica em fine-tuning/AutoML. Gini de 0.667 indica concentracao significativa no topo, mas mesmo o mediano e altamente lucrativo. Codigo limpo sem red flags adversariais significativas.
